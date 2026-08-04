from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping
from uuid import uuid4

from backend.capabilities.networking import (
    PEOPLE_DISCOVERY_STATUS_FAILED,
    PEOPLE_DISCOVERY_STATUS_RUNNING,
    build_empty_relevant_people_discovery,
    build_hiring_manager_outreach_draft,
    build_relevant_people_discovery as _build_relevant_people_discovery,
    build_referral_outreach_draft,
    build_target_contact_discovery,
    find_referral_contacts_for_company,
    guess_hiring_manager_from_job,
    merge_referral_contacts,
    normalize_relevant_people_discovery_run,
    parse_referral_contacts_csv,
    update_relevant_people_status,
)
from backend.domain.job_identity import canonical_posting_url
from backend.domain.models import JobRecord, ReferralContactRecord, ReviewRecord, UserRecord, WorkspaceDefinition, utc_now_iso
from backend.domain.tracker import review_is_actionable_tracker_item
from backend.repositories.contracts import BackendRepositories


APPLICATION_CONTEXTS_METADATA_KEY = "application_contexts"
RELEVANT_PEOPLE_DISCOVERY_CONTEXT_KEY = "relevant_people_discovery"
LINKEDIN_SYNC_METADATA_KEY = "linkedin_connection_sync"
LINKEDIN_SYNC_INTERVAL = timedelta(days=1)


@dataclass(slots=True)
class TrackerApplicationService:
    repositories: BackendRepositories
    build_relevant_people_discovery: Callable[..., dict[str, Any]] = _build_relevant_people_discovery

    def list_referral_contacts(self, user_id: str) -> list[ReferralContactRecord]:
        user = self.repositories.auth_repository.get_user(user_id)
        contacts = [
            ReferralContactRecord.from_dict(item)
            for item in (user.metadata or {}).get("referrals") or []
            if isinstance(item, dict)
        ]
        return contacts

    def get_referral_contact(self, user_id: str, contact_id: str) -> ReferralContactRecord:
        for contact in self.list_referral_contacts(user_id):
            if contact.contact_id == contact_id:
                return contact
        raise KeyError(f"Referral contact '{contact_id}' not found.")

    def upsert_referral_contact(
        self,
        *,
        user_id: str,
        payload: Mapping[str, Any] | ReferralContactRecord,
        contact_id: str = "",
    ) -> ReferralContactRecord:
        user = self.repositories.auth_repository.get_user(user_id)
        contact = payload if isinstance(payload, ReferralContactRecord) else ReferralContactRecord.from_dict(payload)
        if contact_id:
            contact.contact_id = contact_id
        if not contact.contact_id:
            contact = ReferralContactRecord.create(
                name=contact.name,
                company=contact.company,
                companies=contact.companies,
                linkedin_url=contact.linkedin_url,
                relationship_note=contact.relationship_note,
                can_refer=contact.can_refer,
                source_kind=contact.source_kind,
                import_batch_id=contact.import_batch_id,
                import_ref=contact.import_ref,
                metadata=contact.metadata,
            )
        if not contact.name:
            raise ValueError("contact name is required")
        contact.company = contact.primary_company()
        contact.can_refer = bool(contact.can_refer or any(bool(item.get("can_refer")) for item in contact.companies))
        contact.updated_at = utc_now_iso()

        contacts = self.list_referral_contacts(user_id)
        replaced = False
        normalized_contacts: list[ReferralContactRecord] = []
        for existing in contacts:
            if existing.contact_id == contact.contact_id:
                normalized_contacts.append(contact)
                replaced = True
            else:
                normalized_contacts.append(existing)
        if not replaced:
            normalized_contacts.append(contact)
        self._persist_referral_contacts(user, normalized_contacts)
        return self.get_referral_contact(user_id, contact.contact_id)

    def import_referral_contacts(
        self,
        *,
        user_id: str,
        csv_text: str,
        source_kind: str = "linkedin_csv",
    ) -> dict[str, Any]:
        if not str(csv_text or "").strip():
            raise ValueError("csv_text is required")
        user = self.repositories.auth_repository.get_user(user_id)
        import_batch_id = f"import_{uuid4().hex[:12]}"
        parsed_contacts = parse_referral_contacts_csv(
            csv_text,
            source_kind=source_kind,
            import_batch_id=import_batch_id,
        )
        if not parsed_contacts:
            raise ValueError("No contacts could be parsed from the CSV.")
        existing_contacts = self.list_referral_contacts(user_id)
        merged_contacts, summary = merge_referral_contacts(existing_contacts, parsed_contacts)
        for contact in merged_contacts:
            contact.updated_at = utc_now_iso()
        self._persist_referral_contacts(user, merged_contacts)
        refreshed_contacts = self.list_referral_contacts(user_id)
        imported_contact_ids = {
            contact.contact_id
            for contact in refreshed_contacts
            if contact.import_batch_id == import_batch_id
        }
        return {
            "import_batch_id": import_batch_id,
            "source_kind": source_kind,
            "summary": {
                **summary,
                "parsed": len(parsed_contacts),
                "total_contacts": len(refreshed_contacts),
            },
            "imported_contact_ids": sorted(imported_contact_ids),
            "contacts": [contact.to_dict() for contact in refreshed_contacts],
        }

    def linkedin_sync_status(self, user_id: str) -> dict[str, Any]:
        user = self.repositories.auth_repository.get_user(user_id)
        metadata = dict((user.metadata or {}).get(LINKEDIN_SYNC_METADATA_KEY) or {})
        last_sync_at = str(metadata.get("last_sync_at") or "").strip()
        next_sync_at = ""
        can_sync = True
        if last_sync_at:
            try:
                last_sync = datetime.fromisoformat(last_sync_at.replace("Z", "+00:00"))
                if last_sync.tzinfo is None:
                    last_sync = last_sync.replace(tzinfo=timezone.utc)
                next_sync = last_sync + LINKEDIN_SYNC_INTERVAL
                next_sync_at = next_sync.isoformat().replace("+00:00", "Z")
                can_sync = datetime.now(timezone.utc) >= next_sync
            except ValueError:
                last_sync_at = ""
        return {
            "can_sync": can_sync,
            "last_sync_at": last_sync_at,
            "next_sync_at": next_sync_at,
            "connection_count": sum(
                1
                for contact in self.list_referral_contacts(user_id)
                if contact.source_kind in {"linkedin_csv", "linkedin_csv_import", "linkedin_extension"}
                and contact.is_active
            ),
        }

    def sync_linkedin_connections(self, *, user_id: str, csv_text: str) -> dict[str, Any]:
        status = self.linkedin_sync_status(user_id)
        if not status["can_sync"]:
            raise ValueError("You can only sync your LinkedIn network once per day. Please try again tomorrow.")
        result = self.import_referral_contacts(
            user_id=user_id,
            csv_text=csv_text,
            source_kind="linkedin_extension",
        )
        user = self.repositories.auth_repository.get_user(user_id)
        metadata = dict(user.metadata or {})
        metadata[LINKEDIN_SYNC_METADATA_KEY] = {
            "last_sync_at": utc_now_iso(),
            "last_sync_summary": dict(result.get("summary") or {}),
        }
        user.metadata = metadata
        user.updated_at = utc_now_iso()
        self.repositories.auth_repository.upsert_user(user)
        result["sync_status"] = self.linkedin_sync_status(user_id)
        return result

    def delete_imported_referral_contacts(
        self,
        *,
        user_id: str,
    ) -> dict[str, Any]:
        user = self.repositories.auth_repository.get_user(user_id)
        contacts = self.list_referral_contacts(user_id)
        kept_contacts = [
            contact
            for contact in contacts
            if contact.source_kind not in {"linkedin_csv", "linkedin_csv_import", "linkedin_extension"}
        ]
        deleted_count = len(contacts) - len(kept_contacts)
        if deleted_count:
            self._persist_referral_contacts(user, kept_contacts)
        return {
            "deleted": deleted_count,
            "contacts": [contact.to_dict() for contact in kept_contacts],
        }

    def delete_referral_contact(self, user_id: str, contact_id: str) -> None:
        user = self.repositories.auth_repository.get_user(user_id)
        contacts = self.list_referral_contacts(user_id)
        kept_contacts = [contact for contact in contacts if contact.contact_id != contact_id]
        if len(kept_contacts) == len(contacts):
            raise KeyError(f"Referral contact '{contact_id}' not found.")
        self._persist_referral_contacts(user, kept_contacts)

    def generate_referral_outreach(
        self,
        *,
        user_id: str,
        run_id: str,
        job_id: str,
        contact_id: str = "",
    ) -> dict[str, Any]:
        user = self.repositories.auth_repository.get_user(user_id)
        job = self.get_job_for_run(run_id=run_id, job_id=job_id)
        contacts = self.list_referral_contacts(user_id)
        matches = find_referral_contacts_for_company(contacts, job.company)
        if contact_id:
            contact = next((item for item in matches if item.contact_id == contact_id), None)
            if contact is None:
                contact = self.get_referral_contact(user_id, contact_id)
        else:
            contact = matches[0] if matches else None
        if contact is None:
            raise ValueError("No referral contact matches this job yet.")
        profile = dict((user.metadata or {}).get("profile") or {})
        payload = build_referral_outreach_draft(profile=profile, job=job, contact=contact)
        payload["matched_contacts"] = [item.to_dict() for item in matches]
        return payload

    def generate_hiring_manager_outreach(
        self,
        *,
        user_id: str,
        run_id: str,
        job_id: str,
    ) -> dict[str, Any]:
        user = self.repositories.auth_repository.get_user(user_id)
        job = self.get_job_for_run(run_id=run_id, job_id=job_id)
        profile = dict((user.metadata or {}).get("profile") or {})
        hiring_manager = guess_hiring_manager_from_job(job)
        return build_hiring_manager_outreach_draft(
            profile=profile,
            job=job,
            hiring_manager=hiring_manager,
        )

    def generate_target_contact_discovery(
        self,
        *,
        user_id: str,
        run_id: str,
        job_id: str,
    ) -> dict[str, Any]:
        user = self.repositories.auth_repository.get_user(user_id)
        job = self.get_job_for_run(run_id=run_id, job_id=job_id)
        profile = dict((user.metadata or {}).get("profile") or {})
        return build_target_contact_discovery(profile=profile, job=job)

    def get_job_workspace(
        self,
        *,
        user_id: str,
        run_id: str,
        job_id: str,
    ) -> dict[str, Any]:
        user = self.repositories.auth_repository.get_user(user_id)
        run = self.repositories.run_repository.get(run_id)
        workspace = self.repositories.workspace_repository.get_workspace(run.workspace_id)
        job = self.get_job_for_run(run_id=run_id, job_id=job_id)
        return self._job_workspace_payload(
            user=user,
            run_id=run_id,
            job=job,
            workspace=workspace,
        )

    def get_relevant_people_discovery_status(
        self,
        *,
        user_id: str,
        run_id: str,
        job_id: str,
    ) -> dict[str, Any]:
        workspace_payload = self.get_job_workspace(
            user_id=user_id,
            run_id=run_id,
            job_id=job_id,
        )
        discovery = normalize_relevant_people_discovery_run(
            workspace_payload.get("relevant_people_discovery") or {}
        )
        return {
            "runId": str(run_id or ""),
            "jobId": str(job_id or ""),
            "workspaceId": str(workspace_payload.get("workspace_id") or ""),
            "peopleDiscoveryStatus": str(discovery.get("peopleDiscoveryStatus") or ""),
            "selectedPeopleCount": len(discovery.get("selectedPeople") or []),
            "lastStartedAt": str(discovery.get("lastStartedAt") or ""),
            "lastCompletedAt": str(discovery.get("lastCompletedAt") or ""),
            "lastUpdatedAt": str(discovery.get("lastUpdatedAt") or ""),
            "error": str(discovery.get("error") or ""),
        }

    def get_relevant_people_discovery_results(
        self,
        *,
        user_id: str,
        run_id: str,
        job_id: str,
    ) -> dict[str, Any]:
        workspace_payload = self.get_job_workspace(
            user_id=user_id,
            run_id=run_id,
            job_id=job_id,
        )
        return normalize_relevant_people_discovery_run(
            workspace_payload.get("relevant_people_discovery") or {}
        )

    def start_relevant_people_discovery(
        self,
        *,
        user_id: str,
        run_id: str,
        job_id: str,
    ) -> dict[str, Any]:
        user = self.repositories.auth_repository.get_user(user_id)
        run = self.repositories.run_repository.get(run_id)
        workspace = self.repositories.workspace_repository.get_workspace(run.workspace_id)
        job = self.get_job_for_run(run_id=run_id, job_id=job_id)
        started_at = utc_now_iso()
        running_payload = build_empty_relevant_people_discovery(
            job=job,
            run_id=run_id,
            workspace_id=workspace.id,
            status=PEOPLE_DISCOVERY_STATUS_RUNNING,
            last_started_at=started_at,
        )
        self._persist_job_application_context(
            user,
            run_id=run_id,
            job_id=job_id,
            context_payload={RELEVANT_PEOPLE_DISCOVERY_CONTEXT_KEY: running_payload},
        )

        profile = dict((user.metadata or {}).get("profile") or {})
        try:
            completed_payload = self.build_relevant_people_discovery(
                profile=profile,
                job=job,
                run_id=run_id,
                workspace_id=workspace.id,
                last_started_at=started_at,
            )
        except Exception as exc:
            failed_payload = build_empty_relevant_people_discovery(
                job=job,
                run_id=run_id,
                workspace_id=workspace.id,
                status=PEOPLE_DISCOVERY_STATUS_FAILED,
                error=str(exc),
                last_started_at=started_at,
            )
            self._persist_job_application_context(
                user,
                run_id=run_id,
                job_id=job_id,
                context_payload={RELEVANT_PEOPLE_DISCOVERY_CONTEXT_KEY: failed_payload},
            )
            raise

        self._persist_job_application_context(
            user,
            run_id=run_id,
            job_id=job_id,
            context_payload={RELEVANT_PEOPLE_DISCOVERY_CONTEXT_KEY: completed_payload},
        )
        return completed_payload

    def set_relevant_people_status(
        self,
        *,
        user_id: str,
        run_id: str,
        job_id: str,
        person_id: str,
        status: str,
    ) -> dict[str, Any]:
        user = self.repositories.auth_repository.get_user(user_id)
        current_payload = self.get_relevant_people_discovery_results(
            user_id=user_id,
            run_id=run_id,
            job_id=job_id,
        )
        updated_payload = update_relevant_people_status(
            current_payload,
            person_id=person_id,
            status=status,
        )
        self._persist_job_application_context(
            user,
            run_id=run_id,
            job_id=job_id,
            context_payload={RELEVANT_PEOPLE_DISCOVERY_CONTEXT_KEY: updated_payload},
        )
        return updated_payload

    @staticmethod
    def review_is_actionable_tracker_item(review: ReviewRecord) -> bool:
        return review_is_actionable_tracker_item(review)

    @staticmethod
    def job_record_posting_url(job: JobRecord | None) -> str:
        if job is None:
            return ""
        return canonical_posting_url(job.to_dict())

    def user_tracker_posting_urls(
        self,
        *,
        user_id: str,
        exclude_review_id: str = "",
        exclude_run_id: str = "",
        exclude_job_id: str = "",
    ) -> dict[str, dict[str, str]]:
        normalized_user_id = str(user_id or "").strip()
        if not normalized_user_id:
            return {}
        excluded_review_id = str(exclude_review_id or "").strip()
        excluded_run_id = str(exclude_run_id or "").strip()
        excluded_job_id = str(exclude_job_id or "").strip()
        by_posting_url: dict[str, dict[str, str]] = {}
        for existing_run in self._list_runs(limit=100000, offset=0, status=""):
            if existing_run.normalized_user_id != normalized_user_id:
                continue
            jobs_by_id: dict[str, JobRecord] = {}
            try:
                for jobs in self.repositories.job_store.load_all_job_sets(existing_run.id).values():
                    for job in jobs:
                        jobs_by_id[job.job_id] = job
            except Exception:
                continue
            for existing_review in self._list_reviews(run_id=existing_run.id, limit=100000, offset=0):
                if excluded_review_id and existing_review.review_id == excluded_review_id:
                    continue
                if excluded_run_id and not excluded_job_id and existing_review.run_id == excluded_run_id:
                    continue
                if (
                    excluded_run_id
                    and excluded_job_id
                    and existing_review.run_id == excluded_run_id
                    and existing_review.job_id == excluded_job_id
                ):
                    continue
                if not self.review_is_actionable_tracker_item(existing_review):
                    continue
                posting_url = self.job_record_posting_url(jobs_by_id.get(existing_review.job_id))
                if not posting_url or posting_url in by_posting_url:
                    continue
                by_posting_url[posting_url] = {
                    "posting_url": posting_url,
                    "run_id": existing_run.id,
                    "workspace_id": existing_run.workspace_id,
                    "review_id": existing_review.review_id,
                    "job_id": existing_review.job_id,
                }
        return by_posting_url

    def find_duplicate_user_tracker_posting(
        self,
        *,
        run_id: str,
        job_id: str,
        review_id: str = "",
    ) -> dict[str, str]:
        run = self.repositories.run_repository.get(run_id)
        user_id = run.normalized_user_id
        if not user_id:
            return {}
        try:
            job = self.get_job_for_run(run_id=run_id, job_id=job_id)
        except KeyError:
            return {}
        posting_url = self.job_record_posting_url(job)
        if not posting_url:
            return {}
        existing = self.user_tracker_posting_urls(
            user_id=user_id,
            exclude_review_id=review_id,
            exclude_run_id=run_id,
            exclude_job_id=job_id,
        )
        return dict(existing.get(posting_url) or {})

    def get_job_for_run(self, *, run_id: str, job_id: str) -> JobRecord:
        self.repositories.run_repository.get(run_id)
        for jobs in self.repositories.job_store.load_all_job_sets(run_id).values():
            for job in jobs:
                if job.job_id == job_id:
                    return job
        raise KeyError(f"Job '{job_id}' not found for run '{run_id}'.")

    def _persist_referral_contacts(self, user: UserRecord, contacts: list[ReferralContactRecord]) -> None:
        metadata = dict(user.metadata or {})
        metadata["referrals"] = [contact.to_dict() for contact in contacts]
        user.metadata = metadata
        user.updated_at = utc_now_iso()
        self.repositories.auth_repository.upsert_user(user)

    def _job_application_context_key(self, *, run_id: str, job_id: str) -> str:
        return f"{str(run_id or '').strip()}::{str(job_id or '').strip()}"

    def _load_job_application_context(self, user: UserRecord, *, run_id: str, job_id: str) -> dict[str, Any]:
        metadata = dict(user.metadata or {})
        all_contexts = dict(metadata.get(APPLICATION_CONTEXTS_METADATA_KEY) or {})
        context_key = self._job_application_context_key(run_id=run_id, job_id=job_id)
        return dict(all_contexts.get(context_key) or {})

    def _persist_job_application_context(
        self,
        user: UserRecord,
        *,
        run_id: str,
        job_id: str,
        context_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        metadata = dict(user.metadata or {})
        all_contexts = dict(metadata.get(APPLICATION_CONTEXTS_METADATA_KEY) or {})
        context_key = self._job_application_context_key(run_id=run_id, job_id=job_id)
        existing_context = dict(all_contexts.get(context_key) or {})
        merged_context = {
            **existing_context,
            **dict(context_payload or {}),
            "run_id": str(run_id or "").strip(),
            "job_id": str(job_id or "").strip(),
            "updated_at": utc_now_iso(),
        }
        all_contexts[context_key] = merged_context
        metadata[APPLICATION_CONTEXTS_METADATA_KEY] = all_contexts
        user.metadata = metadata
        user.updated_at = utc_now_iso()
        self.repositories.auth_repository.upsert_user(user)
        refreshed_user = self.repositories.auth_repository.get_user(user.user_id)
        return self._load_job_application_context(refreshed_user, run_id=run_id, job_id=job_id)

    def _job_workspace_payload(
        self,
        *,
        user: UserRecord,
        run_id: str,
        job: JobRecord,
        workspace: WorkspaceDefinition,
    ) -> dict[str, Any]:
        stored_context = self._load_job_application_context(user, run_id=run_id, job_id=job.job_id)
        relevant_people_discovery = stored_context.get(RELEVANT_PEOPLE_DISCOVERY_CONTEXT_KEY)
        if relevant_people_discovery:
            normalized_discovery = normalize_relevant_people_discovery_run(
                dict(relevant_people_discovery or {})
            )
        else:
            normalized_discovery = build_empty_relevant_people_discovery(
                job=job,
                run_id=run_id,
                workspace_id=workspace.id,
            )
        job_payload = job.to_dict()
        description_text = str(job.description_text or job_payload.get("description") or "").strip()
        return {
            "run_id": run_id,
            "workspace_id": workspace.id,
            "workspace_name": workspace.name,
            "job": {
                **job_payload,
                "job_id": str(job.job_id or ""),
                "title": str(job.title or ""),
                "company": str(job.company or ""),
                "location": str(job.location_raw or ""),
                "apply_link": str(job.apply_link or job.link or job.source_url or ""),
                "description_text": description_text,
            },
            "selected_relevant_people": [
                person
                for person in normalized_discovery.get("selectedPeople") or []
                if isinstance(person, dict)
            ],
            "relevant_people_discovery": normalized_discovery,
            "application_context": stored_context,
        }

    def _list_runs(self, *, limit: int = 50, offset: int = 0, status: str = "", workspace_id: str = ""):
        repository = self.repositories.run_repository
        try:
            return repository.list_runs(limit=limit, offset=offset, status=status, workspace_id=workspace_id)
        except TypeError:
            runs = repository.list_runs(
                limit=max(1, int(limit)) + max(0, int(offset)),
                status=status,
                workspace_id=workspace_id,
            )
            normalized_offset = max(0, int(offset))
            normalized_limit = max(1, int(limit))
            return runs[normalized_offset : normalized_offset + normalized_limit]

    def _list_reviews(
        self,
        *,
        run_id: str = "",
        job_id: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> list[ReviewRecord]:
        repository = self.repositories.review_store
        try:
            return repository.list_reviews(run_id=run_id, job_id=job_id, limit=limit, offset=offset)
        except TypeError:
            reviews = repository.list_reviews(
                run_id=run_id,
                job_id=job_id,
                limit=max(1, int(limit)) + max(0, int(offset)),
            )
            normalized_offset = max(0, int(offset))
            normalized_limit = max(1, int(limit))
            return reviews[normalized_offset : normalized_offset + normalized_limit]
