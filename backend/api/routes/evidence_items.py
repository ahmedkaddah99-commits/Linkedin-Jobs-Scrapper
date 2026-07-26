"""Evidence item API routes (CP-016).

Replaces the legacy /career-memory endpoints with a unified evidence-item CRUD
and lifecycle API. Evidence items are the single source of truth for candidate
claims, sourced from verified texts and managed through a consistent lifecycle:
needs_review → reviewed → confirmed/rejected/merged/conflict.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any
from uuid import uuid4

from backend.api.routes.registry import ApiRouteContext, RouteRegistry
from backend.capabilities.candidate_evidence import (
    CandidateEvidence,
    build_evidence_summary,
    clear_legacy_career_memory,
    deduplicate_evidence,
    detect_and_apply_conflicts,
    extract_evidence_from_verified_sources,
    generate_evidence_outputs,
    get_confirmed_evidence,
    has_legacy_career_memory,
    migrate_and_deduplicate,
    migrate_legacy_facts_to_evidence,
    regenerate_evidence_output,
    run_evidence_pipeline,
)
from backend.domain.candidate_evidence import (
    EVIDENCE_STATUS_CONFIRMED,
    EVIDENCE_STATUS_CONFLICT,
    EVIDENCE_STATUS_MERGED,
    EVIDENCE_STATUS_NEEDS_REVIEW,
    EVIDENCE_STATUS_REJECTED,
    EVIDENCE_STATUS_REVIEWED,
)



def register_routes(registry: RouteRegistry) -> None:
    # Fixed lifecycle routes must precede the generic
    # /evidence-items/{evidence_id} prefix.
    registry.exact("GET", ("evidence-items", "next-review"), _handle_next_review,
                    auth_required=True, name="evidence_items.next_review")
    registry.exact("GET", ("evidence-items", "readiness"), _handle_readiness,
                    auth_required=True, name="evidence_items.readiness")
    registry.exact("GET", ("evidence-items", "ready-actions"), _handle_ready_actions,
                    auth_required=True, name="evidence_items.ready_actions")
    registry.exact("GET", ("evidence-items", "journey-state"), _handle_journey_state,
                    auth_required=True, name="evidence_items.journey_state")

    registry.exact("POST", ("evidence-items", "review-action"), _handle_review_action,
                    auth_required=True, name="evidence_items.review_action")
    registry.exact("POST", ("evidence-items", "clear-spikes"), _handle_clear_spikes,
                    auth_required=True, name="evidence_items.clear_spikes")
    registry.exact("POST", ("evidence-items", "confirm-inspect"), _handle_confirm_inspect,
                    auth_required=True, name="evidence_items.confirm_inspect")
    registry.exact("POST", ("evidence-items", "answer-enrich"), _handle_answer_enrich,
                    auth_required=True, name="evidence_items.answer_enrich")
    registry.exact("POST", ("evidence-items", "skip-question"), _handle_skip_question,
                    auth_required=True, name="evidence_items.skip_question")

    registry.prefix("GET", ("evidence-items",), _handle_get, auth_required=True, name="evidence_items.get")
    registry.prefix("POST", ("evidence-items",), _handle_post, auth_required=True, name="evidence_items.post")
    registry.prefix("PUT", ("evidence-items",), _handle_put, auth_required=True, name="evidence_items.put")



def _evidence_store(context: ApiRouteContext):
    """Resolve the evidence store from the application."""
    store = getattr(context.application.repositories, "evidence_store", None)
    if store is None:
        # Fallback: in-memory store on user metadata
        return _metadata_evidence_store(context)
    return store


def _metadata_evidence_store(context: ApiRouteContext):
    """Use user.metadata as a lightweight evidence store (fallback)."""
    user, _ = context.require_identity()
    metadata = dict(user.metadata or {})
    evidence_list: list[dict[str, Any]] = list(metadata.get("candidate_evidence") or [])
    return _MetadataEvidenceAdapter(evidence_list, user, context.application)


def _persist_user(context: ApiRouteContext, user) -> None:
    """Persist lifecycle mutations before any response is returned."""
    context.application.repositories.auth_repository.upsert_user(user)


class _MetadataEvidenceAdapter:
    """Adapter that stores evidence in user.metadata for simple persistence."""

    def __init__(self, evidence_list: list[dict[str, Any]], user, application):
        self._list = evidence_list
        self._user = user
        self._app = application

    def _persist(self) -> None:
        metadata = dict(self._user.metadata or {})
        metadata["candidate_evidence"] = list(self._list)
        self._user.metadata = metadata
        from datetime import datetime, timezone
        self._user.updated_at = datetime.now(timezone.utc).isoformat()
        self._app.repositories.auth_repository.upsert_user(self._user)

    def list_all(self) -> list[dict[str, Any]]:
        return list(self._list)

    def get_by_id(self, evidence_id: str) -> dict[str, Any] | None:
        for ev in self._list:
            if ev.get("evidence_id") == evidence_id:
                return dict(ev)
        return None

    def upsert(self, evidence: CandidateEvidence) -> None:
        existing_idx = next(
            (i for i, ev in enumerate(self._list) if ev.get("evidence_id") == evidence.evidence_id),
            None,
        )
        if existing_idx is not None:
            self._list[existing_idx] = evidence.to_dict()
        else:
            self._list.append(evidence.to_dict())
        self._persist()

    def upsert_many(self, items: list[CandidateEvidence]) -> None:
        by_id = {ev.get("evidence_id"): i for i, ev in enumerate(self._list)}
        for item in items:
            d = item.to_dict()
            eid = d["evidence_id"]
            if eid in by_id:
                self._list[by_id[eid]] = d
            else:
                self._list.append(d)
                by_id[eid] = len(self._list) - 1
        self._persist()




def _handle_put(context: ApiRouteContext) -> bool | None:
    """Handle manual evidence update (CP-032R)."""
    segments = list(context.segments)
    payload = context.read_json_body()

    if len(segments) == 2 and segments[0] == "evidence-items":
        evidence_id = segments[1]
        store = _evidence_store(context)
        item = store.get_by_id(evidence_id)
        if item is None:
            context.send_error(HTTPStatus.NOT_FOUND, "evidence_not_found",
                               f"Evidence item '{evidence_id}' not found.")
            return True
        ev = CandidateEvidence.from_dict(item)
        if "text" in payload:
            ev.text = str(payload["text"] or "").strip()
        if "evidence_type" in payload:
            ev.evidence_type = str(payload["evidence_type"] or ev.evidence_type)
        if "certainty" in payload:
            ev.certainty = str(payload["certainty"] or ev.certainty)
        if "inferred_employer" in payload:
            ev.inferred_employer = str(payload["inferred_employer"] or "").strip()
        if "inferred_role" in payload:
            ev.inferred_role = str(payload["inferred_role"] or "").strip()
        if "experience_mapping" in payload:
            ev.experience_mapping = dict(payload["experience_mapping"] or {})
        from backend.domain.models import utc_now_iso
        ev.updated_at = utc_now_iso()
        store.upsert(ev)
        context.send_json(ev.to_dict(), status=HTTPStatus.OK)
        return True

    return False


def _handle_get(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)

    if segments == ["evidence-items"]:
        store = _evidence_store(context)
        items = store.list_all()
        context.send_json({"evidence": items, "total": len(items)}, status=HTTPStatus.OK)
        return True

    if segments == ["evidence-items", "outputs"]:
        user, _ = context.require_identity()
        metadata = dict(user.metadata or {})
        outputs = list(metadata.get("evidence_outputs") or [])
        context.send_json({"outputs": outputs, "total": len(outputs)}, status=HTTPStatus.OK)
        return True

    if len(segments) >= 2 and segments[0] == "evidence-items":
        evidence_id = segments[1]
        if len(segments) == 3 and segments[2] == "summary":
            store = _evidence_store(context)
            all_items = store.list_all()
            evidence_objs = [CandidateEvidence.from_dict(ev) for ev in all_items]
            summary = build_evidence_summary(evidence_objs)
            context.send_json(summary, status=HTTPStatus.OK)
            return True

        store = _evidence_store(context)
        item = store.get_by_id(evidence_id)
        if item is None:
            context.send_error(HTTPStatus.NOT_FOUND, "evidence_not_found",
                               f"Evidence item '{evidence_id}' not found.")
            return True
        context.send_json(item, status=HTTPStatus.OK)
        return True

    return False


def _handle_post(context: ApiRouteContext) -> bool | None:
    application = context.application
    segments = list(context.segments)
    payload = context.read_json_body()

    if segments == ["evidence-items", "extract"]:
        profile_id = str(payload.get("profile_id") or "")
        verified_texts = list(payload.get("verified_texts") or [])
        if not profile_id or not verified_texts:
            context.send_error(HTTPStatus.UNPROCESSABLE_ENTITY,
                               "validation_error", "profile_id and verified_texts are required.")
            return True
        evidence = extract_evidence_from_verified_sources(profile_id, verified_texts)
        store = _evidence_store(context)
        store.upsert_many(evidence)
        context.send_json(
            {"evidence": [ev.to_dict() for ev in evidence], "total": len(evidence)},
            status=HTTPStatus.CREATED,
        )
        return True

    if segments == ["evidence-items", "pipeline"]:
        profile_id = str(payload.get("profile_id") or "")
        verified_texts = list(payload.get("verified_texts") or [])
        dedupe_threshold = float(payload.get("dedupe_threshold") or 0.75)
        if not profile_id or not verified_texts:
            context.send_error(HTTPStatus.UNPROCESSABLE_ENTITY,
                               "validation_error", "profile_id and verified_texts are required.")
            return True
        result = run_evidence_pipeline(profile_id, verified_texts, dedupe_threshold=dedupe_threshold)
        store = _evidence_store(context)
        evidence_objs = [CandidateEvidence.from_dict(ev) for ev in result["evidence"]]
        store.upsert_many(evidence_objs)
        context.send_json(result, status=HTTPStatus.CREATED)
        return True

    if segments == ["evidence-items", "migrate"]:
        user, _ = context.require_identity()
        profile_id = str(payload.get("profile_id") or "")
        if not has_legacy_career_memory(user.metadata):
            context.send_json({"migrated": 0, "skipped": 0,
                               "message": "No legacy career memory data found."},
                              status=HTTPStatus.OK)
            return True
        # Load existing canonical evidence for content-hash dedup
        store = _evidence_store(context)
        all_items = store.list_all()
        existing_evidence = [CandidateEvidence.from_dict(ev) for ev in all_items]
        # Idempotent migration with deduplication
        result = migrate_and_deduplicate(
            profile_id=profile_id,
            user_metadata=user.metadata,
            existing_evidence=existing_evidence,
        )
        cleaned = clear_legacy_career_memory(user.metadata)
        user.metadata = cleaned
        from datetime import datetime, timezone
        user.updated_at = datetime.now(timezone.utc).isoformat()
        application.repositories.auth_repository.upsert_user(user)
        # Persist only new (non-duplicate) items
        new_evidence = [CandidateEvidence.from_dict(ev) for ev in result["evidence"]]
        store.upsert_many(new_evidence)
        context.send_json(result, status=HTTPStatus.CREATED)
        return True

    if segments == ["evidence-items", "deduplicate"]:
        store = _evidence_store(context)
        all_items = store.list_all()
        evidence_objs = [CandidateEvidence.from_dict(ev) for ev in all_items]
        threshold = float(payload.get("threshold") or 0.75)
        result = deduplicate_evidence(evidence_objs, threshold=threshold)
        store.upsert_many(evidence_objs)
        context.send_json(result, status=HTTPStatus.OK)
        return True

    if segments == ["evidence-items", "generate"]:
        store = _evidence_store(context)
        all_items = store.list_all()
        evidence_objs = [CandidateEvidence.from_dict(ev) for ev in all_items]
        mode = str(payload.get("mode") or "standard")
        try:
            output = generate_evidence_outputs(evidence_objs, mode=mode)
        except ValueError as exc:
            context.send_error(HTTPStatus.UNPROCESSABLE_ENTITY,
                               "generation_error", str(exc))
            return True
        user, _ = context.require_identity()
        metadata = dict(user.metadata or {})
        outputs = list(metadata.get("evidence_outputs") or [])
        outputs.append(output)
        metadata["evidence_outputs"] = outputs
        user.metadata = metadata
        from datetime import datetime, timezone
        user.updated_at = datetime.now(timezone.utc).isoformat()
        application.repositories.auth_repository.upsert_user(user)
        context.send_json(output, status=HTTPStatus.CREATED)
        return True

    if len(segments) == 4 and segments[:2] == ["evidence-items", "outputs"] and segments[3] == "regenerate":
        output_id = segments[2]
        user, _ = context.require_identity()
        metadata = dict(user.metadata or {})
        outputs = list(metadata.get("evidence_outputs") or [])
        existing = next((o for o in outputs if o.get("output_id") == output_id), None)
        if existing is None:
            context.send_error(HTTPStatus.NOT_FOUND, "output_not_found",
                               f"Output '{output_id}' not found.")
            return True
        store = _evidence_store(context)
        all_items = store.list_all()
        evidence_objs = [CandidateEvidence.from_dict(ev) for ev in all_items]
        action = str(payload.get("action") or "standard")
        new_output = regenerate_evidence_output(
            existing,
            evidence_objs,
            action=action,
            cv_bullet=str(payload.get("cv_bullet") or ""),
            cover_letter=str(payload.get("cover_letter") or ""),
        )
        outputs = [o if o.get("output_id") != output_id else new_output for o in outputs]
        metadata["evidence_outputs"] = outputs
        user.metadata = metadata
        from datetime import datetime, timezone
        user.updated_at = datetime.now(timezone.utc).isoformat()
        application.repositories.auth_repository.upsert_user(user)
        context.send_json(new_output, status=HTTPStatus.OK)
        return True

    if len(segments) == 3 and segments[0] == "evidence-items" and segments[2] == "status":
        evidence_id = segments[1]
        store = _evidence_store(context)
        item = store.get_by_id(evidence_id)
        if item is None:
            context.send_error(HTTPStatus.NOT_FOUND, "evidence_not_found",
                               f"Evidence item '{evidence_id}' not found.")
            return True
        ev = CandidateEvidence.from_dict(item)
        new_status = str(payload.get("status") or "")
        if new_status == EVIDENCE_STATUS_REVIEWED:
            ev.mark_reviewed()
        elif new_status == EVIDENCE_STATUS_CONFIRMED:
            ev.confirm()
        elif new_status == EVIDENCE_STATUS_REJECTED:
            ev.reject()
        else:
            context.send_error(HTTPStatus.UNPROCESSABLE_ENTITY,
                               "validation_error", f"Invalid status: {new_status}")
            return True
        store.upsert(ev)
        context.send_json(ev.to_dict(), status=HTTPStatus.OK)
        return True

    # CP-043R: Process sources through Gemini and extract evidence
    # Enhanced: idempotency, persistent state, real file bytes lookup.
    if segments == ["evidence-items", "process-sources"]:
        user, _ = context.require_identity()
        asset_ids = list(payload.get("source_ids") or payload.get("asset_ids") or [])
        profile_id = str(payload.get("profile_id") or "")
        sources_data = list(payload.get("sources") or [])

        if not sources_data and not asset_ids:
            context.send_error(HTTPStatus.UNPROCESSABLE_ENTITY,
                               "validation_error", "source_ids or sources with file data required.")
            return True

        import base64
        from datetime import datetime, timezone
        from backend.capabilities.source_processing.pipeline import (
            process_sources_and_extract_evidence, build_source_processing_state,
        )

        metadata = dict(user.metadata or {})

        # Skip only evidence created by the current structured extractor. Older
        # sentence-split batches must be reprocessed instead of trapping users.
        from backend.capabilities.source_processing.pipeline import STRUCTURED_EXTRACTION_VERSION

        store = _metadata_evidence_store(context)
        evidence_objs_existing = [CandidateEvidence.from_dict(ev) for ev in store.list_all()]
        existing_source_ids = {
            str(getattr(ev, "source_id", "") or "").strip()
            for ev in evidence_objs_existing
            if getattr(ev, "source_id", "")
            and (ev.metadata or {}).get("extraction_version") == STRUCTURED_EXTRACTION_VERSION
        }
        all_requested_ids = set(asset_ids) | {str(s.get("asset_id") or "") for s in sources_data}
        all_requested_ids.discard("")
        if all_requested_ids and all_requested_ids.issubset(existing_source_ids):
            idem_state = build_source_processing_state({
                "status": "completed",
                "sources": [{"asset_id": aid, "status": "extracted", "extracted_count": 1}
                            for aid in all_requested_ids],
                "summary": {"total_sources": len(all_requested_ids)},
                "batch_id": "idem_" + str(len(all_requested_ids)),
            })
            idem_state["state"] = "completed"
            idem_state["retry_allowed"] = False
            context.send_json({
                "batch_id": "idem_" + str(len(all_requested_ids)),
                "status": "completed", "sources": [],
                "evidence": [], "summary": {"total_sources": len(all_requested_ids)},
                "state": idem_state, "_idempotent": True,
            }, status=HTTPStatus.OK)
            return True

        # Build source entries (real bytes verification)
        sources_to_process: list[dict[str, Any]] = []
        for src in sources_data:
            asset_id = str(src.get("asset_id") or src.get("source_id") or "")
            file_name = str(src.get("file_name") or src.get("display_name") or "")
            file_bytes_b64 = str(src.get("file_bytes") or src.get("data") or "")

            file_bytes = b""
            if file_bytes_b64:
                try:
                    file_bytes = base64.b64decode(file_bytes_b64)
                except Exception:
                    pass

            # Never accept filename as fake content
            if asset_id and file_bytes and len(file_bytes) > 10:
                if file_bytes != file_name.encode("utf-8"):
                    sources_to_process.append({
                        "asset_id": asset_id, "file_name": file_name, "file_bytes": file_bytes,
                    })

        # For bare asset_ids, find actual file bytes from document storage
        candidate_assets = list(metadata.get("candidate_assets") or [])
        processed_ids = {s["asset_id"] for s in sources_to_process}
        for aid in asset_ids:
            if aid in processed_ids:
                continue
            asset = next((a for a in candidate_assets if str(a.get("asset_id") or "") == aid), None)
            if not asset:
                continue
            asset_meta = dict(asset.get("metadata") or {})
            file_payload = dict(asset.get("file") or {})
            file_name = str(asset.get("display_name") or asset.get("file_name") or aid)
            file_bytes = b""

            # Try object storage
            object_key = str(file_payload.get("object_key") or "").strip()
            if object_key:
                try:
                    obj_storage = getattr(context.application, "object_storage", None)
                    if obj_storage and obj_storage.exists(object_key):
                        file_bytes = obj_storage.get(object_key)
                except Exception:
                    pass

            # Try local file path
            if not file_bytes:
                raw_path = str(file_payload.get("path") or asset.get("path") or "").strip()
                if raw_path:
                    p = Path(raw_path)
                    if p.is_file():
                        try:
                            file_bytes = p.read_bytes()
                        except Exception:
                            pass

            # Fall back to stored extracted text
            if not file_bytes:
                source_text = str(asset_meta.get("source_text") or asset_meta.get("text") or "")
                if source_text and len(source_text) > 20:
                    file_bytes = source_text.encode("utf-8")

            if file_bytes:
                sources_to_process.append({
                    "asset_id": aid, "file_name": file_name, "file_bytes": file_bytes,
                })
                processed_ids.add(aid)

        if not sources_to_process:
            context.send_error(HTTPStatus.UNPROCESSABLE_ENTITY,
                               "validation_error", "No processable sources found.")
            return True

        # CP-043R: Persist processing state before pipeline
        metadata["_evidence_processing_state"] = {
            "state": "processing", "batch_id": "", "started_at": datetime.now(timezone.utc).isoformat(),
            "source_count": len(sources_to_process),
        }
        user.metadata = metadata
        user.updated_at = datetime.now(timezone.utc).isoformat()
        context.application.repositories.auth_repository.upsert_user(user)

        result = process_sources_and_extract_evidence(
            sources_to_process, profile_id=profile_id,
        )

        state = build_source_processing_state(result)

        # A processing batch is the canonical journey unit. Archive the prior
        # batch and atomically replace active evidence/experiences so stale
        # fragments never appear beside the new extraction.
        metadata_final = dict(user.metadata or {})
        previous_evidence = list(metadata_final.get("candidate_evidence") or [])
        if result.get("evidence"):
            if previous_evidence:
                archives = list(metadata_final.get("candidate_evidence_archives") or [])
                archives.append({
                    "batch_id": str(metadata_final.get("_active_evidence_batch_id") or "legacy"),
                    "archived_at": datetime.now(timezone.utc).isoformat(),
                    "evidence": previous_evidence,
                })
                metadata_final["candidate_evidence_archives"] = archives[-2:]
            metadata_final["candidate_evidence"] = list(result["evidence"])
            metadata_final["work_experiences"] = list(result.get("experiences") or [])
            metadata_final["_active_evidence_batch_id"] = result["batch_id"]
            metadata_final["evidence_review_cursor"] = 0
            metadata_final["evidence_question_history"] = []
        metadata_final["_evidence_processing_state"] = {
            "state": result["status"], "batch_id": result["batch_id"],
            "started_at": result.get("started_at"), "completed_at": result.get("completed_at"),
            "source_count": result["summary"]["total_sources"],
            "extracted_count": result["summary"]["extracted"],
            "error": state.get("error", ""),
        }
        user.metadata = metadata_final
        user.updated_at = datetime.now(timezone.utc).isoformat()
        _persist_user(context, user)

        from backend.evidence.review_service import get_journey_state

        context.send_json({
            "batch_id": result["batch_id"], "status": result["status"],
            "sources": result["sources"], "evidence": result["evidence"],
            "experiences": result.get("experiences") or [],
            "summary": result["summary"], "state": state,
            "journey": get_journey_state(user),
        }, status=HTTPStatus.OK if result["status"] == "completed" else HTTPStatus.ACCEPTED)
        return True



# ── CP-040R: Evidence review handlers ──────────────────────────────────


def _handle_next_review(context: ApiRouteContext) -> bool | None:
    """Get the next evidence item awaiting review with suggested mapping."""
    segments = list(context.segments)

    if segments == ["evidence-items", "next-review"]:
        user, _ = context.require_identity()
        from backend.evidence.review_service import get_next_review_item
        result = get_next_review_item(user)
        context.send_json(result, status=HTTPStatus.OK)
        return True

    return False


def _handle_review_action(context: ApiRouteContext) -> bool | None:
    """Apply a review action: confirm, reject, or edit an evidence item."""
    segments = list(context.segments)
    payload = context.read_json_body()

    if segments == ["evidence-items", "review-action"]:
        user, _ = context.require_identity()
        evidence_id = str(payload.get("evidence_id") or "")

        if not evidence_id:
            context.send_error(HTTPStatus.UNPROCESSABLE_ENTITY,
                               "validation_error", "evidence_id is required.")
            return True

        action = str(payload.get("action") or "")

        from backend.evidence.review_service import (
            confirm_evidence,
            edit_evidence,
            reject_evidence,
        )

        try:
            if action == "confirm":
                mapping = payload.get("mapping") if payload.get("mapping") else None
                edited_text = payload.get("edited_text")
                result = confirm_evidence(user, evidence_id,
                                          mapping=mapping,
                                          edited_text=edited_text)
            elif action == "reject":
                result = reject_evidence(user, evidence_id)
            elif action == "edit":
                updates = {
                    k: v for k, v in payload.items()
                    if k not in ("evidence_id", "action")
                }
                result = edit_evidence(user, evidence_id, updates)
            else:
                context.send_error(HTTPStatus.UNPROCESSABLE_ENTITY,
                                   "validation_error",
                                   f"Invalid action: {action}. Use confirm, reject, or edit.")
                return True

            _persist_user(context, user)
            from backend.evidence.review_service import get_journey_state
            journey = get_journey_state(user)
            context.send_json({**journey, **result}, status=HTTPStatus.OK)
        except KeyError as exc:
            context.send_error(HTTPStatus.NOT_FOUND,
                               "evidence_not_found", str(exc))
        return True

    return False


def _handle_readiness(context: ApiRouteContext) -> bool | None:
    """Compute canonical readiness from evidence records."""
    segments = list(context.segments)

    if segments == ["evidence-items", "readiness"]:
        user, _ = context.require_identity()
        from backend.evidence.review_service import compute_canonical_readiness
        result = compute_canonical_readiness(user)
        context.send_json(result, status=HTTPStatus.OK)
        return True

    return False


def _handle_clear_spikes(context: ApiRouteContext) -> bool | None:
    """Remove legacy memory-spike counters and migrate data."""
    segments = list(context.segments)

    if segments == ["evidence-items", "clear-spikes"]:
        user, _ = context.require_identity()
        from backend.evidence.review_service import remove_legacy_memory_spike
        result = remove_legacy_memory_spike(user)
        context.send_json(result, status=HTTPStatus.OK)
        return True

    return False


# ── CP-041R: Integrated confirm + question + enrich handlers ───────────


def _handle_confirm_inspect(context: ApiRouteContext) -> bool | None:
    """CP-041R: Confirm evidence and inspect for highest-value missing-detail question."""
    segments = list(context.segments)
    payload = context.read_json_body()

    if segments == ["evidence-items", "confirm-inspect"]:
        user, _ = context.require_identity()
        evidence_id = str(payload.get("evidence_id") or "")

        if not evidence_id:
            context.send_error(HTTPStatus.UNPROCESSABLE_ENTITY,
                               "validation_error", "evidence_id is required.")
            return True

        mapping = payload.get("mapping") if payload.get("mapping") else None
        edited_text = payload.get("edited_text")

        try:
            from backend.evidence.review_service import confirm_with_inspect
            result = confirm_with_inspect(
                user, evidence_id, mapping=mapping, edited_text=edited_text
            )
            _persist_user(context, user)
            from backend.evidence.review_service import get_journey_state
            journey = get_journey_state(user)
            context.send_json({**journey, **{
                key: value for key, value in result.items()
                if key in ("action", "evidence")
            }}, status=HTTPStatus.OK)
        except KeyError as exc:
            context.send_error(HTTPStatus.NOT_FOUND,
                               "evidence_not_found", str(exc))
        return True

    return False


def _handle_answer_enrich(context: ApiRouteContext) -> bool | None:
    """CP-041R: Answer a question and enrich the evidence record."""
    segments = list(context.segments)
    payload = context.read_json_body()

    if segments == ["evidence-items", "answer-enrich"]:
        user, _ = context.require_identity()
        question_id = str(payload.get("question_id") or "")
        answer_text = str(payload.get("answer_text") or payload.get("text") or "")
        evidence_id = str(payload.get("evidence_id") or "")

        if not question_id or not answer_text:
            context.send_error(HTTPStatus.UNPROCESSABLE_ENTITY,
                               "validation_error", "question_id and answer_text are required.")
            return True

        try:
            from backend.evidence.review_service import answer_enrich_evidence
            result = answer_enrich_evidence(
                user, question_id, answer_text, evidence_id=evidence_id or None
            )
            _persist_user(context, user)
            from backend.evidence.review_service import get_journey_state
            journey = get_journey_state(user)
            context.send_json({**journey, **{
                key: value for key, value in result.items()
                if key in ("action", "evidence")
            }}, status=HTTPStatus.OK)
        except Exception as exc:
            context.send_error(HTTPStatus.INTERNAL_SERVER_ERROR,
                               "enrich_error", str(exc))
        return True

    return False


def _handle_skip_question(context: ApiRouteContext) -> bool | None:
    """CP-041R: Skip a question permanently."""
    segments = list(context.segments)
    payload = context.read_json_body()

    if segments == ["evidence-items", "skip-question"]:
        user, _ = context.require_identity()
        question_id = str(payload.get("question_id") or "")

        if not question_id:
            context.send_error(HTTPStatus.UNPROCESSABLE_ENTITY,
                               "validation_error", "question_id is required.")
            return True

        try:
            from backend.evidence.review_service import skip_question_for_evidence
            result = skip_question_for_evidence(user, question_id)
            _persist_user(context, user)
            from backend.evidence.review_service import get_journey_state
            journey = get_journey_state(user)
            context.send_json({**journey, **{
                key: value for key, value in result.items()
                if key in ("action", "evidence")
            }}, status=HTTPStatus.OK)
        except Exception as exc:
            context.send_error(HTTPStatus.INTERNAL_SERVER_ERROR,
                               "skip_error", str(exc))
        return True

    return False


def _handle_journey_state(context: ApiRouteContext) -> bool | None:
    """CP-044R: Get the full evidence journey state."""
    segments = list(context.segments)

    if segments == ["evidence-items", "journey-state"]:
        user, _ = context.require_identity()
        from backend.evidence.review_service import get_journey_state
        result = get_journey_state(user)
        context.send_json(result, status=HTTPStatus.OK)
        return True

    return False



def _handle_ready_actions(context: ApiRouteContext) -> bool | None:
    """CP-041R: Get grounded primary actions when Ready."""
    segments = list(context.segments)

    if segments == ["evidence-items", "ready-actions"]:
        user, _ = context.require_identity()
        from backend.evidence.review_service import build_ready_actions, compute_canonical_readiness
        readiness = compute_canonical_readiness(user)
        actions = build_ready_actions(user) if readiness["is_ready"] else []
        context.send_json({
            "readiness": readiness,
            "primary_actions": actions,
        }, status=HTTPStatus.OK)
        return True

    return False

