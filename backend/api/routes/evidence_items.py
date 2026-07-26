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
    registry.prefix("GET", ("evidence-items",), _handle_get, auth_required=True, name="evidence_items.get")
    registry.prefix("POST", ("evidence-items",), _handle_post, auth_required=True, name="evidence_items.post")
    registry.prefix("PUT", ("evidence-items",), _handle_put, auth_required=True, name="evidence_items.put")

    # CP-040R: Evidence review endpoints
    registry.prefix("GET", ("evidence-items", "next-review"), _handle_next_review,
                    auth_required=True, name="evidence_items.next_review")
    registry.prefix("POST", ("evidence-items", "review-action"), _handle_review_action,
                    auth_required=True, name="evidence_items.review_action")
    registry.prefix("GET", ("evidence-items", "readiness"), _handle_readiness,
                    auth_required=True, name="evidence_items.readiness")
    registry.prefix("POST", ("evidence-items", "clear-spikes"), _handle_clear_spikes,
                    auth_required=True, name="evidence_items.clear_spikes")


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

    # CP-039R: Process sources through Gemini and extract evidence
    if segments == ["evidence-items", "process-sources"]:
        user, _ = context.require_identity()
        asset_ids = list(payload.get("source_ids") or payload.get("asset_ids") or [])
        profile_id = str(payload.get("profile_id") or "")
        sources_data = list(payload.get("sources") or [])

        if not sources_data and not asset_ids:
            context.send_error(HTTPStatus.UNPROCESSABLE_ENTITY,
                               "validation_error", "source_ids or sources with file data required.")
            return True

        # Build source entries from provided data
        sources_to_process = []
        for src in sources_data:
            asset_id = str(src.get("asset_id") or src.get("source_id") or "")
            file_name = str(src.get("file_name") or src.get("display_name") or "")
            file_bytes_b64 = str(src.get("file_bytes") or src.get("data") or "")

            file_bytes = b""
            if file_bytes_b64:
                import base64
                try:
                    file_bytes = base64.b64decode(file_bytes_b64)
                except Exception:
                    file_bytes = file_bytes_b64.encode("utf-8")

            if asset_id and file_bytes:
                sources_to_process.append({
                    "asset_id": asset_id,
                    "file_name": file_name,
                    "file_bytes": file_bytes,
                })

        # For bare asset_ids, try to find in candidate_assets
        metadata = dict(user.metadata or {})
        candidate_assets = list(metadata.get("candidate_assets") or [])
        for aid in asset_ids:
            if any(s["asset_id"] == aid for s in sources_to_process):
                continue
            asset = next((a for a in candidate_assets if str(a.get("asset_id") or "") == aid), None)
            if asset:
                asset_meta = dict(asset.get("metadata") or {})
                source_text = str(asset_meta.get("source_text") or asset_meta.get("text") or "")
                if source_text:
                    sources_to_process.append({
                        "asset_id": aid,
                        "file_name": str(asset.get("display_name") or asset.get("file_name") or ""),
                        "file_bytes": source_text.encode("utf-8"),
                    })

        if not sources_to_process:
            context.send_error(HTTPStatus.UNPROCESSABLE_ENTITY,
                               "validation_error", "No processable sources found.")
            return True

        from backend.capabilities.source_processing.pipeline import (
            process_sources_and_extract_evidence,
        )

        result = process_sources_and_extract_evidence(
            sources_to_process,
            profile_id=profile_id,
        )

        # Persist evidence via metadata-backed store (compatible with CandidateEvidence)
        if result.get("evidence"):
            store = _metadata_evidence_store(context)
            evidence_objs = [CandidateEvidence.from_dict(ev) for ev in result["evidence"]]
            # Idempotency: only store evidence not already persisted
            existing = {ev["evidence_id"]: ev for ev in store.list_all()}
            new_evidence = [ev for ev in evidence_objs if ev.evidence_id not in existing]
            if new_evidence:
                store.upsert_many(new_evidence)

        from backend.capabilities.source_processing.pipeline import (
            build_source_processing_state,
        )
        state = build_source_processing_state(result)

        context.send_json({
            "batch_id": result["batch_id"],
            "status": result["status"],
            "sources": result["sources"],
            "evidence": result["evidence"],
            "summary": result["summary"],
            "state": state,
        }, status=HTTPStatus.OK if result["status"] == "completed" else HTTPStatus.ACCEPTED)
        return True


    return False




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

            context.send_json(result, status=HTTPStatus.OK)
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
