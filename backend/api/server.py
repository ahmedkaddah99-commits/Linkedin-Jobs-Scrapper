from __future__ import annotations

import base64
import io
import json
import logging
import mimetypes
import os
import re
import time
from threading import RLock
import zipfile
from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime, timedelta, timezone
from email.parser import BytesFeedParser
from hashlib import sha256
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from typing import Any, Mapping
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.parse import parse_qsl
from uuid import uuid4

from backend.api.routes import ApiRouteContext, build_route_registry
from backend.api.routes.route_support import (
    _artifact_download_url,
    _extract_bearer_token,
    _file_timestamp_iso,
    _is_unauthorized_permission_error,
    _json_bytes,
    _normalize_hostname_origin,
    _normalize_origin_value,
    _normalize_segments,
    _origin_is_chrome_extension,
    _origin_is_loopback,
    _parse_allowed_extension_origins,
    _parse_allowed_origins,
    _parse_bool_param,
    _parse_int_param,
    _schedule_interval_days,
)
from backend.application.services import (
    BackendValidationError,
    _builder_workspace_flow_id,
    _builder_workspace_source_ids,
)
from backend.application.quota import QuotaExceededError, check_and_increment_quota
from backend.capabilities.networking import find_referral_contacts_for_company
from backend.capabilities.tracker import (
    TRACKER_EMAIL_INTEGRATION_METADATA_KEY,
    begin_google_tracker_authorization,
    build_public_tracker_email_config,
    complete_google_tracker_authorization,
    mark_google_tracker_authorization_error,
    normalize_tracker_email_config,
    sync_tracker_email,
    sync_tracker_gmail,
    test_tracker_email_connection,
    tracker_google_oauth_callback_message,
    tracker_google_oauth_state_is_valid,
    tracker_email_provider_options,
)
from backend.capabilities.tracker.google_oauth import (
    build_google_tracker_authorization_url,
    exchange_google_tracker_oauth_code,
    fetch_google_tracker_profile,
    refresh_google_tracker_access_token,
    tracker_google_oauth_metadata,
)
from backend.capabilities.tailored_documents.modes import (
    APPLIED_CV_ASSET_KIND,
    APPLIED_CV_DOCUMENT_TYPE,
    CV_GENERATION_MODE_STANDARD,
    normalize_cv_generation_mode,
)
from backend.capabilities.tailored_documents.application_requirements import detect_application_requirements
from backend.capabilities.tailored_documents.language_rules import LANGUAGE_ALIASES, normalize_cefr_level
from backend.capabilities.tailored_documents.rendering import get_document_design_options, normalize_cv_template_id
from backend.bootstrap import create_backend
from backend.config import cfg_str, load_job_seeker_config, load_project_dotenv, validate_environment
from backend.profiles.document_text import create_word_companion_bytes, extract_document_text, extraction_metadata
from backend.config.plans import (
    DEFAULT_PLAN_ID,
    PLANS,
    compare_plan_tiers,
    get_plan,
    get_plan_for_product_id,
    get_quota,
    list_plans,
    normalize_plan_id,
)
from backend.domain.phase0_contracts import (
    PERSONALIZATION_SCOPE_BASELINE,
    PERSONALIZATION_SCOPE_FULL,
    PERSONALIZATION_SCOPE_SELECTED,
    legacy_tracker_status_for_application_status,
    normalize_application_document,
    normalize_application_status,
    normalize_candidate_asset_descriptor,
    normalize_gmail_application_detection,
    normalize_gmail_scan_window,
    normalize_referral_outreach_status,
    normalize_rejected_job_review,
    normalize_tracker_application,
    phase0_contract_catalog,
)
from backend.domain.ats_export_gate import evaluate_ats_export_gate
from backend.domain.run_eta import build_run_eta
from backend.tools.discover_company_careers import run_discovery as run_career_url_discovery
from backend.domain.models import (
    JobSource,
    ProfileRef,
    ROLE_ADMIN,
    RUN_STATUS_CANCEL_REQUESTED,
    RUN_STATUS_CANCELLED,
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    RUN_STATUS_PLANNED,
    RUN_STATUS_QUEUED,
    RUN_STATUS_RUNNING,
    STAGE_STATUS_COMPLETED,
    STAGE_STATUS_FAILED,
    STAGE_STATUS_SKIPPED,
    TOKEN_SCOPE_ADMIN,
    TOKEN_SCOPE_ARTIFACTS_READ,
    TOKEN_SCOPE_ARTIFACTS_WRITE,
    TOKEN_SCOPE_REVIEWS_READ,
    TOKEN_SCOPE_REVIEWS_WRITE,
    TOKEN_SCOPE_RUNS_READ,
    TOKEN_SCOPE_RUNS_WRITE,
    TOKEN_SCOPE_SECRETS_READ,
    TOKEN_SCOPE_SECRETS_WRITE,
    TOKEN_SCOPE_TEMPLATES_READ,
    TOKEN_SCOPE_TEMPLATES_WRITE,
    TOKEN_SCOPE_USERS_READ,
    TOKEN_SCOPE_USERS_WRITE,
    TOKEN_SCOPE_WORKER_EXECUTE,
    TOKEN_SCOPE_WORKSPACES_READ,
    TOKEN_SCOPE_WORKSPACES_WRITE,
    ReferralContactRecord,
    UserRecord,
    WorkspaceDefinition,
    utc_plus_seconds,
)
from backend.domain.job_identity import canonical_posting_url
from backend.domain.tracker import (
    ensure_review_placed_in_tracker_at,
    review_is_actionable_tracker_item,
    review_placed_in_tracker_at,
)
from backend.orchestration.workspace_builder import _slugify, build_quick_apply_workflow_template
from backend.profiles.cv_profile_extraction import (
    extract_cv_profile_fallback,
    normalize_profile_payload,
)
from backend.profiles.cv_upload_jobs import (
    CV_STATUS_READY,
    CV_STATUS_UPLOADED,
    cv_upload_status_url,
    cv_upload_status_payload,
    enqueue_cv_upload_processing_run,
)
from backend.profiles.cv_text import extract_cv_text_from_path
from backend.storage import build_private_object_key, materialize_object
from backend.integrations.clerk import (
    build_synthetic_token,
    get_user as get_clerk_user,
    get_display_name as get_clerk_display_name,
    get_primary_email_address as get_clerk_primary_email_address,
    get_signup_source as get_clerk_signup_source,
    normalize_clerk_role,
    update_user_metadata as update_clerk_user_metadata,
    verify_session_token,
    verify_webhook as verify_clerk_webhook,
)
from backend.integrations.creem import (
    create_discount as create_creem_discount,
    delete_discount as delete_creem_discount,
    get_checkout_url as get_creem_checkout_url,
    get_customer_portal_url as get_creem_customer_portal_url,
    list_discounts as list_creem_discounts,
    update_user_plan_in_clerk,
    verify_redirect_signature as verify_creem_redirect_signature,
    verify_webhook_signature as verify_creem_webhook_signature,
)
from backend.api.telemetry import RequestTelemetry, new_telemetry
from backend.worker import WorkerService, configure_worker_logging

_EXPANDED_ARTIFACT_DELIMITER = "__item__"
_EXPANDED_ARTIFACT_SUFFIXES = {".csv", ".docx", ".json", ".md", ".pdf", ".txt", ".xlsx"}
_PROMO_CODE_PATTERN = re.compile(r"^[A-Z0-9]{3,256}$")
_CLIENT_DISCONNECT_ERRORS = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)
_MAX_CV_UPLOAD_REQUEST_BYTES = 10 * 1024 * 1024
_ACTIVE_RUN_STATUSES = {
    RUN_STATUS_PLANNED,
    RUN_STATUS_QUEUED,
    RUN_STATUS_RUNNING,
    RUN_STATUS_CANCEL_REQUESTED,
}
_TERMINAL_STAGE_STATUSES = {STAGE_STATUS_COMPLETED, STAGE_STATUS_SKIPPED}
_AUTH_CONTEXT_CACHE_TTL_SECONDS = 60
_AUTH_CONTEXT_CACHE_MAX_ENTRIES = 256
_AUTH_CONTEXT_CACHE_LOCK = RLock()
_AUTH_CONTEXT_CACHE: dict[str, tuple[float, SimpleNamespace]] = {}


class AtsExportBlockedError(ValueError):
    def __init__(self, gate: dict):
        self.gate = gate
        super().__init__(gate.get("last_warning") or "Final CV export is blocked until the ATS score target is reached.")


class RequestBodyTooLargeError(ValueError):
    pass


def _workspace_schedule_summary(workspace) -> dict:
    raw_schedule = dict((workspace.metadata or {}).get("run_schedule") or {})
    interval_days = _schedule_interval_days(raw_schedule.get("interval_days"))
    enabled = bool(raw_schedule.get("enabled")) and interval_days >= 1
    return {
        "enabled": enabled,
        "interval_days": interval_days if enabled else 0,
        "next_run_at": str(raw_schedule.get("next_run_at") or ""),
        "last_enqueued_at": str(raw_schedule.get("last_enqueued_at") or ""),
        "last_run_id": str(raw_schedule.get("last_run_id") or ""),
        "last_error": str(raw_schedule.get("last_error") or ""),
        "last_error_at": str(raw_schedule.get("last_error_at") or ""),
    }


def _is_cv_like_artifact(
    *,
    file_name: str,
    artifact_type: str = "",
    relative_path: str = "",
    source_artifact_type: str = "",
) -> bool:
    source_type = str(source_artifact_type or artifact_type or "").strip().lower()
    if source_type == "stage4_role_cv_dir":
        return True
    hints = " ".join(
        item.strip().lower()
        for item in (file_name, artifact_type, relative_path, source_artifact_type)
        if str(item).strip()
    )
    return bool(re.search(r"(^|[^a-z])(cv|resume)([^a-z]|$)", hints))


def _infer_expanded_artifact_type(*, file_name: str, relative_path: str, source_artifact_type: str) -> str:
    suffix = Path(file_name).suffix.lower().lstrip(".") or "file"
    lower_path = relative_path.lower()
    if _is_cv_like_artifact(
        file_name=file_name,
        relative_path=relative_path,
        source_artifact_type=source_artifact_type,
    ):
        return f"cv_{suffix}"
    if "email" in lower_path:
        return f"email_{suffix}"
    if "cover" in lower_path or "anschreiben" in lower_path:
        return f"cover_letter_{suffix}"
    return suffix


def _encode_expanded_artifact_id(parent_artifact_id: str, relative_path: str) -> str:
    encoded = base64.urlsafe_b64encode(relative_path.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{parent_artifact_id}{_EXPANDED_ARTIFACT_DELIMITER}{encoded}"


def _decode_expanded_artifact_id(artifact_id: str) -> tuple[str, str]:
    parent_artifact_id, delimiter, encoded_relative_path = artifact_id.partition(_EXPANDED_ARTIFACT_DELIMITER)
    if not delimiter or not parent_artifact_id or not encoded_relative_path:
        return "", ""
    try:
        padding = "=" * (-len(encoded_relative_path) % 4)
        relative_path = base64.urlsafe_b64decode(f"{encoded_relative_path}{padding}").decode("utf-8")
    except Exception:
        return "", ""
    return parent_artifact_id, relative_path


def _resolve_expanded_artifact_path(parent_artifact_path: str, relative_path: str) -> Path:
    parent_dir = Path(parent_artifact_path)
    if not parent_dir.exists() or not parent_dir.is_dir():
        raise KeyError(f"Artifact directory '{parent_artifact_path}' not found.")
    candidate = (parent_dir / relative_path).resolve()
    root = parent_dir.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise KeyError(f"Artifact file '{relative_path}' not found.") from exc
    if not candidate.exists() or not candidate.is_file():
        raise KeyError(f"Artifact file '{relative_path}' not found.")
    return candidate


def _build_artifact_entry(
    run,
    workspace,
    *,
    artifact_id: str,
    artifact_type: str,
    path: str,
    metadata: dict,
    created_at: str,
    relative_path: str = "",
    source_artifact_id: str = "",
    source_artifact_type: str = "",
    is_virtual: bool = False,
) -> dict:
    file_name = Path(path).name or artifact_id
    return {
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "path": path,
        "file_name": file_name,
        "relative_path": relative_path,
        "workspace_id": run.workspace_id,
        "workspace_name": workspace.name if workspace else run.workspace_id,
        "run_id": run.id,
        "created_at": created_at,
        "job_id": str(metadata.get("job_id") or ""),
        "job_title": str(metadata.get("job_title") or ""),
        "company": str(metadata.get("company") or ""),
        "status": str(metadata.get("status") or ("ready" if path else "missing")),
        "download_url": _artifact_download_url(run.id, artifact_id),
        "metadata": metadata,
        "source_artifact_id": source_artifact_id,
        "source_artifact_type": source_artifact_type,
        "content_type": mimetypes.guess_type(file_name)[0] or "application/octet-stream",
        "is_virtual": is_virtual,
        "is_cv": _is_cv_like_artifact(
            file_name=file_name,
            artifact_type=artifact_type,
            relative_path=relative_path,
            source_artifact_type=source_artifact_type,
        ),
    }


def _expand_artifact_entries(run, workspace, artifact) -> list[dict]:
    metadata = dict(artifact.metadata or {})
    artifact_path = Path(artifact.path)
    created_at = str(run.finished_at or run.updated_at)
    if not artifact.path:
        return [
            _build_artifact_entry(
                run,
                workspace,
                artifact_id=artifact.artifact_id,
                artifact_type=artifact.artifact_type,
                path=artifact.path,
                metadata=metadata,
                created_at=created_at,
            )
        ]

    if artifact_path.exists() and artifact_path.is_dir():
        expanded_entries: list[dict] = []
        for child_path in sorted(artifact_path.rglob("*"), key=lambda item: str(item).lower()):
            if not child_path.is_file() or child_path.suffix.lower() not in _EXPANDED_ARTIFACT_SUFFIXES:
                continue
            relative_path = child_path.relative_to(artifact_path).as_posix()
            expanded_entries.append(
                _build_artifact_entry(
                    run,
                    workspace,
                    artifact_id=_encode_expanded_artifact_id(artifact.artifact_id, relative_path),
                    artifact_type=_infer_expanded_artifact_type(
                        file_name=child_path.name,
                        relative_path=relative_path,
                        source_artifact_type=artifact.artifact_type,
                    ),
                    path=str(child_path),
                    metadata=metadata,
                    created_at=_file_timestamp_iso(child_path, fallback=created_at),
                    relative_path=relative_path,
                    source_artifact_id=artifact.artifact_id,
                    source_artifact_type=artifact.artifact_type,
                    is_virtual=True,
                )
            )
        if expanded_entries:
            return expanded_entries

    return [
        _build_artifact_entry(
            run,
            workspace,
            artifact_id=artifact.artifact_id,
            artifact_type=artifact.artifact_type,
            path=artifact.path,
            metadata=metadata,
            created_at=_file_timestamp_iso(artifact_path, fallback=created_at),
        )
    ]


def _resolve_artifact_download(application, run_id: str, artifact_id: str) -> tuple[str, str]:
    try:
        artifact = application.get_artifact(run_id, artifact_id)
    except KeyError:
        parent_artifact_id, relative_path = _decode_expanded_artifact_id(artifact_id)
        if not parent_artifact_id or not relative_path:
            raise
        parent_artifact = application.get_artifact(run_id, parent_artifact_id)
        target = _resolve_expanded_artifact_path(parent_artifact.path, relative_path)
        return str(target), target.name
    object_key = str((artifact.metadata or {}).get("object_key") or "").strip()
    if object_key:
        target = materialize_object(
            application.object_storage,
            object_key,
            filename=Path(str(artifact.path or "")).name or artifact.artifact_id,
        )
        return str(target), (target.name or artifact.artifact_id)
    target = Path(artifact.path)
    return artifact.path, (target.name or artifact.artifact_id)


# ---------------------------------------------------------------------------
# CV extraction helpers
# ---------------------------------------------------------------------------

def _extract_text_from_docx(data: bytes) -> str:
    return str(extract_document_text("upload.docx", data).get("text") or "")


def _extract_text_from_pdf(data: bytes) -> str:
    return str(extract_document_text("upload.pdf", data).get("text") or "")


def _extract_text_from_uploaded_file(filename: str, data: bytes) -> str:
    return str(extract_document_text(filename, data).get("text") or "").strip()


def _extract_cv_profile_for_upload(cv_text: str) -> dict[str, Any]:
    normalized_text = str(cv_text or "").strip()
    return {
        "profile": extract_cv_profile_fallback(normalized_text),
        "provider": "heuristic_fallback",
        "model": "upload_fast_path",
        "warnings": ["ai_profile_extraction_skipped_for_upload_latency"],
        "extracted_at": datetime.now(timezone.utc).isoformat(),
    }


def _parse_cv_sections(cv_text: str) -> dict:
    """Best-effort heuristic extraction of CV sections.

    Returns a dict with optional keys: summary, competencies, experience_lines.
    These are used to pre-populate the profile settings UI after upload.
    """
    lines = [line.rstrip() for line in cv_text.splitlines()]

    # ---- detect section header positions ----
    _SUMMARY_HEADERS = re.compile(
        r"^(professional\s+summary|summary|profile|about\s+me|objective)",
        re.IGNORECASE,
    )
    _SKILLS_HEADERS = re.compile(
        r"^(skills|core\s+competencies|competencies|technical\s+skills|key\s+skills|"
        r"tools|technologies|technology\s+stack|tech\s+stack)",
        re.IGNORECASE,
    )
    _EXP_HEADERS = re.compile(
        r"^(experience|work\s+experience|professional\s+experience|employment)",
        re.IGNORECASE,
    )
    _EDUCATION_HEADERS = re.compile(
        r"^(education|education\s+and\s+training|certifications?|certificates?|licenses?|licences?|"
        r"training|courses?|professional\s+development)",
        re.IGNORECASE,
    )
    _LANGUAGE_HEADERS = re.compile(
        rf"^(?:{_CV_LANGUAGE_HEADER_LABEL_PATTERN})(?:\s*[:\-]\s*.*)?$",
        re.IGNORECASE,
    )
    _PROJECT_HEADERS = re.compile(
        r"^(projects?|key\s+projects|selected\s+projects|professional\s+projects|portfolio|"
        r"case\s+studies|selected\s+work)",
        re.IGNORECASE,
    )

    sections: dict[str, Any] = {"custom_sections": []}
    current_section = "_preamble"
    sections[current_section] = []
    current_custom: dict[str, Any] | None = None
    seen_section_header = False

    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        next_line = lines[index + 1].strip() if index + 1 < len(lines) else ""
        if _SUMMARY_HEADERS.match(stripped):
            current_section = "summary"
            current_custom = None
            seen_section_header = True
            sections.setdefault(current_section, [])
        elif _SKILLS_HEADERS.match(stripped):
            current_section = "skills"
            current_custom = None
            seen_section_header = True
            sections.setdefault(current_section, [])
        elif _EXP_HEADERS.match(stripped):
            current_section = "experience"
            current_custom = None
            seen_section_header = True
            sections.setdefault(current_section, [])
        elif _PROJECT_HEADERS.match(stripped):
            current_section = "projects"
            current_custom = None
            seen_section_header = True
            sections.setdefault(current_section, [])
        elif _EDUCATION_HEADERS.match(stripped):
            current_section = "education"
            current_custom = None
            seen_section_header = True
            sections.setdefault(current_section, [])
        elif _LANGUAGE_HEADERS.match(stripped):
            current_section = "languages"
            current_custom = None
            seen_section_header = True
            sections.setdefault(current_section, [])
            sections[current_section].extend(_cv_language_header_inline_values(stripped))
        elif current_section == "languages" and _looks_like_cv_language_entry_line(
            stripped,
            allow_plain_language=True,
        ):
            sections.setdefault(current_section, []).append(stripped)
        elif seen_section_header and _looks_like_custom_cv_section_header(stripped, next_line):
            current_section = f"custom_{len(sections['custom_sections'])}"
            current_custom = {
                "section_id": _custom_cv_section_id(stripped, len(sections["custom_sections"])),
                "heading": stripped,
                "lines": [],
            }
            sections["custom_sections"].append(current_custom)
            sections[current_section] = current_custom["lines"]
        else:
            sections.setdefault(current_section, []).append(stripped)
            if current_custom is not None and current_section.startswith("custom_"):
                current_custom["lines"] = sections[current_section]

    # ---- build result ----
    result: dict = {}

    summary_lines = sections.get("summary", [])
    if summary_lines:
        result["summary"] = " ".join(summary_lines)

    skills_lines = sections.get("skills", [])
    if skills_lines:
        # Try to treat comma-separated lines as individual competencies
        competencies: list[str] = []
        for skill_line in skills_lines:
            for part in re.split(r"[,;|•·]", skill_line):
                part = part.strip(" .-")
                if part and len(part) < 60:
                    competencies.append(part)
        result["competencies"] = competencies

    exp_lines = sections.get("experience", [])
    if exp_lines:
        result["experience_lines"] = exp_lines

    project_lines = sections.get("projects", [])
    if project_lines:
        result["project_lines"] = project_lines
    language_lines = sections.get("languages", [])
    if language_lines:
        result["languages"] = _normalize_cv_section_lines(language_lines, limit=20)
    custom_sections = _normalize_cv_custom_sections(sections.get("custom_sections") or [])
    if custom_sections:
        result["custom_sections"] = custom_sections

    return result


_CV_LANGUAGE_HEADER_LABEL_PATTERN = (
    r"languages|language\s+skills|spoken\s+languages|language\s+proficiency|"
    r"sprachen|sprachkenntnisse|fremdsprachen|sprachkompetenzen|"
    r"langues|comp(?:e|\u00e9)tences\s+linguistiques|"
    r"idiomas|conocimientos\s+de\s+idiomas|"
    r"lingue|competenze\s+linguistiche"
)
_CV_LANGUAGE_INLINE_HEADER_PATTERN = re.compile(
    rf"^(?:{_CV_LANGUAGE_HEADER_LABEL_PATTERN})\s*[:\-]\s*(?P<values>.+)$",
    re.IGNORECASE,
)
_CV_SECTION_HEADER_PATTERN = re.compile(
    r"^(professional\s+summary|summary|profile|about\s+me|objective|skills|core\s+competencies|"
    r"competencies|technical\s+skills|key\s+skills|tools|technologies|technology\s+stack|"
    r"tech\s+stack|experience|work\s+experience|"
    r"professional\s+experience|employment|education|education\s+and\s+training|certifications?|"
    r"certificates?|licenses?|licences?|training|courses?|professional\s+development|"
    rf"{_CV_LANGUAGE_HEADER_LABEL_PATTERN}|projects?|key\s+projects|selected\s+projects|"
    r"professional\s+projects|portfolio|case\s+studies|selected\s+work|publications?|"
    r"awards?|honou?rs|volunteer(?:ing)?|volunteer\s+experience|memberships?|patents?|"
    r"conferences?|interests?|references?)$",
    re.IGNORECASE,
)
_CV_SUMMARY_HEADER_PATTERN = re.compile(
    r"^(professional\s+summary|summary|profile|about\s+me|objective)$",
    re.IGNORECASE,
)
_CV_CONTACT_LINE_PATTERN = re.compile(
    r"(@|https?://|www\.|linkedin|github|\+?\d[\d\s()./-]{7,})",
    re.IGNORECASE,
)
_CV_DATE_TOKEN_PATTERN = re.compile(
    r"\b("
    r"(?:19|20)\d{2}|present|current|"
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
    r")\b",
    re.IGNORECASE,
)
_CV_LANGUAGE_ALIAS_PATTERN = re.compile(
    r"(?<![A-Za-z])(?:"
    + "|".join(re.escape(alias) for aliases in LANGUAGE_ALIASES.values() for alias in aliases)
    + r")(?![A-Za-z])",
    re.IGNORECASE,
)
_CV_SECTION_DECISION_TARGETS = {"summary", "skills", "experience", "projects", "education", "languages"}


def _custom_cv_section_id(heading: str, index: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", str(heading or "").strip().casefold()).strip("_")
    return f"custom_{slug or 'section'}_{index + 1}"


def _cv_nonempty_lines(cv_text: str) -> list[str]:
    return [line.strip() for line in str(cv_text or "").splitlines() if line.strip()]


def _looks_like_cv_section_header(line: str) -> bool:
    return bool(_CV_SECTION_HEADER_PATTERN.match(str(line or "").strip()))


def _looks_like_cv_contact_line(line: str) -> bool:
    return bool(_CV_CONTACT_LINE_PATTERN.search(str(line or "").strip()))


def _looks_like_cv_date_line(line: str) -> bool:
    return bool(_CV_DATE_TOKEN_PATTERN.search(str(line or "").strip()))


def _cv_split_inline_values(value: str) -> list[str]:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return []
    return [item.strip(" .-") for item in re.split(r"[,;|]|\s+\u2022\s+", text) if item.strip(" .-")]


def _cv_language_header_inline_values(line: str) -> list[str]:
    match = _CV_LANGUAGE_INLINE_HEADER_PATTERN.match(re.sub(r"\s+", " ", str(line or "")).strip())
    if not match:
        return []
    return _cv_split_inline_values(match.group("values"))


def _looks_like_cv_language_entry_line(line: str, *, allow_plain_language: bool = False) -> bool:
    text = re.sub(r"^\s*[-*\u2022]\s*", "", str(line or "").strip()).strip()
    if not text or len(text) > 72:
        return False
    if _looks_like_cv_contact_line(text) or _looks_like_cv_section_header(text):
        return False
    if not _CV_LANGUAGE_ALIAS_PATTERN.search(text):
        return False
    if normalize_cefr_level(text):
        return True
    words = [word for word in re.split(r"\s+", text) if word]
    if allow_plain_language and len(words) <= 3:
        return True
    return bool(re.search(r"[-:/()]", text) and len(words) <= 5)


def _looks_like_custom_cv_section_header(line: str, next_line: str = "") -> bool:
    text = str(line or "").strip()
    if not text:
        return False
    if _looks_like_cv_language_entry_line(text):
        return False
    if text.startswith(("-", "*", "\u2022")) or len(text) > 72:
        return False
    if any(marker in text for marker in ("|", "@", "://", ",", ";")):
        return False
    if text.endswith((".", ",", ";", ":")):
        return False
    if _looks_like_cv_date_line(text) or _looks_like_cv_contact_line(text):
        return False
    if next_line and _looks_like_cv_date_line(next_line) and not text.isupper():
        return False
    if _looks_like_cv_section_header(text):
        return True
    alpha_count = sum(1 for char in text if char.isalpha())
    if alpha_count < 3:
        return False
    words = [word for word in re.split(r"\s+", text) if word]
    if not words or len(words) > 7:
        return False
    if text.isupper():
        return True
    small_words = {"and", "or", "of", "the", "for", "in", "und", "de", "der", "die", "das"}
    return all(
        not any(char.isalpha() for char in word)
        or word.casefold() in small_words
        or word[:1].isupper()
        for word in words
    )


def _normalize_cv_section_lines(raw_value: Any, *, limit: int = 24) -> list[str]:
    if isinstance(raw_value, list):
        raw_lines = raw_value
    elif isinstance(raw_value, str):
        raw_lines = raw_value.replace("\r", "\n").split("\n")
    elif raw_value in (None, "", []):
        raw_lines = []
    else:
        raw_lines = [raw_value]
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw_line in raw_lines:
        line = re.sub(r"^\s*[-*\u2022]\s*", "", str(raw_line or "")).strip()
        if not line:
            continue
        key = line.casefold()
        if key in seen:
            continue
        cleaned.append(line)
        seen.add(key)
        if len(cleaned) >= limit:
            break
    return cleaned


def _normalize_cv_custom_sections(raw_sections: Any) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    if not isinstance(raw_sections, list):
        return sections
    for index, raw_section in enumerate(raw_sections):
        if isinstance(raw_section, str):
            heading = raw_section.strip()
            lines: list[str] = []
            section_id = _custom_cv_section_id(heading, index)
        elif isinstance(raw_section, Mapping):
            heading = str(
                raw_section.get("heading")
                or raw_section.get("title")
                or raw_section.get("label")
                or ""
            ).strip()
            section_id = str(raw_section.get("section_id") or raw_section.get("id") or "").strip()
            raw_lines = raw_section.get("lines")
            if raw_lines is None:
                raw_lines = raw_section.get("items")
            if raw_lines is None:
                raw_lines = raw_section.get("bullets")
            if raw_lines is None:
                raw_lines = raw_section.get("content") or raw_section.get("text") or ""
            lines = _normalize_cv_section_lines(raw_lines, limit=24)
        else:
            continue
        if not heading and not lines:
            continue
        heading = heading or "Additional Information"
        section_id = section_id or _custom_cv_section_id(heading, index)
        sections.append(
            {
                "section_id": section_id,
                "heading": heading,
                "lines": lines,
                "content": "\n".join(lines),
            }
        )
        if len(sections) >= 12:
            break
    return sections


def _normalize_cv_section_decisions(raw_decisions: Any) -> list[dict[str, str]]:
    if not isinstance(raw_decisions, list):
        return []
    decisions: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in raw_decisions:
        if not isinstance(item, Mapping):
            continue
        section_id = str(item.get("section_id") or item.get("id") or "").strip()
        heading = str(item.get("heading") or "").strip()
        if not section_id and not heading:
            continue
        action = str(item.get("action") or "keep").strip().lower()
        target_section = str(item.get("target_section") or item.get("target") or "").strip().lower()
        if action not in {"keep", "hide", "map"}:
            action = "keep"
        if action != "map":
            target_section = ""
        elif target_section not in _CV_SECTION_DECISION_TARGETS:
            action = "keep"
            target_section = ""
        key = (section_id.casefold(), heading.casefold())
        if key in seen:
            continue
        seen.add(key)
        decisions.append(
            {
                "section_id": section_id,
                "heading": heading,
                "action": action,
                "target_section": target_section,
            }
        )
        if len(decisions) >= 30:
            break
    return decisions


def _decision_for_custom_section(section: Mapping[str, Any], decisions: list[dict[str, str]]) -> dict[str, str]:
    section_id = str(section.get("section_id") or section.get("id") or "").strip()
    heading = str(section.get("heading") or "").strip()
    for decision in decisions:
        decision_section_id = str(decision.get("section_id") or "").strip()
        decision_heading = str(decision.get("heading") or "").strip()
        if decision_section_id and section_id and decision_section_id == section_id:
            return decision
        if decision_heading and heading and decision_heading.casefold() == heading.casefold():
            return decision
    return {"section_id": section_id, "heading": heading, "action": "keep", "target_section": ""}


def _cv_preamble_lines(cv_text: str) -> list[str]:
    preamble: list[str] = []
    for line in _cv_nonempty_lines(cv_text):
        if _looks_like_cv_section_header(line):
            break
        preamble.append(line)
        if len(preamble) >= 8:
            break
    return preamble


def _cv_summary_lines(cv_text: str) -> list[str]:
    lines = _cv_nonempty_lines(cv_text)
    summary_lines: list[str] = []
    capture_summary = False
    for line in lines:
        if _CV_SUMMARY_HEADER_PATTERN.match(line):
            capture_summary = True
            continue
        if capture_summary and _looks_like_cv_section_header(line):
            break
        if capture_summary:
            summary_lines.append(line)
    return summary_lines


def _split_preview_experience_heading(line: str) -> tuple[str, str, str]:
    text = re.sub(r"\s+", " ", str(line or "").strip(" -*•\t"))
    if not text:
        return "", "", ""

    pipe_parts = [part.strip() for part in text.split("|") if part.strip()]
    if len(pipe_parts) >= 3 and _looks_like_cv_date_line(pipe_parts[-1]):
        return pipe_parts[0], pipe_parts[1], pipe_parts[-1]
    if len(pipe_parts) >= 2:
        return pipe_parts[0], pipe_parts[1], ""

    dash_parts = [part.strip() for part in re.split(r"\s[-–—]\s", text) if part.strip()]
    if len(dash_parts) >= 3 and _looks_like_cv_date_line(dash_parts[-1]):
        return dash_parts[0], " - ".join(dash_parts[1:-1]), dash_parts[-1]
    if len(dash_parts) >= 2 and _looks_like_cv_date_line(dash_parts[-1]):
        return dash_parts[0], "", dash_parts[-1]

    lower_text = text.lower()
    marker = " at "
    if marker in lower_text:
        marker_index = lower_text.find(marker)
        return text[:marker_index].strip(), text[marker_index + len(marker) :].strip(), ""

    return text, "", ""


def _looks_like_preview_experience_heading(line: str) -> bool:
    text = str(line or "").strip()
    if not text or text.startswith(("-", "*", "•")):
        return False
    if _looks_like_cv_section_header(text) or len(text) > 100:
        return False
    if "|" in text or " at " in text.lower():
        return True
    return False


def _build_preview_experience_items(lines: list[str]) -> list[dict[str, str]]:
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    def flush_current() -> None:
        nonlocal current
        if current is None:
            return
        title = str(current.get("title") or "").strip()
        company = str(current.get("company") or "").strip()
        period = str(current.get("period") or "").strip()
        bullets = [str(item).strip() for item in current.get("bullets") or [] if str(item).strip()]
        if title or company or period or bullets:
            entries.append(
                {
                    "title": title or "Experience Highlight",
                    "company": company,
                    "period": period,
                    "bulletsText": "\n".join(bullets),
                }
            )
        current = None

    for raw_line in lines:
        line = str(raw_line or "").strip()
        if not line or _looks_like_cv_section_header(line):
            continue
        normalized_bullet = re.sub(r"^\s*[-*•]\s*", "", line).strip()
        if current is None:
            title, company, period = _split_preview_experience_heading(line)
            current = {
                "title": title,
                "company": company,
                "period": period,
                "bullets": [],
            }
            continue
        if _looks_like_preview_experience_heading(line):
            flush_current()
            title, company, period = _split_preview_experience_heading(line)
            current = {
                "title": title,
                "company": company,
                "period": period,
                "bullets": [],
            }
            continue
        if not current.get("period") and _looks_like_cv_date_line(line) and len(line) <= 40:
            current["period"] = line
            continue
        if normalized_bullet:
            current.setdefault("bullets", []).append(normalized_bullet)

    flush_current()
    return entries


def _split_preview_project_heading(line: str) -> tuple[str, str]:
    text = re.sub(r"\s+", " ", str(line or "").strip(" -*\u2022\t"))
    if not text:
        return "", ""

    pipe_parts = [part.strip() for part in text.split("|") if part.strip()]
    if len(pipe_parts) >= 2 and _looks_like_cv_date_line(pipe_parts[-1]):
        return " | ".join(pipe_parts[:-1]), pipe_parts[-1]
    if len(pipe_parts) >= 2:
        return pipe_parts[0], ""

    dash_parts = [part.strip() for part in re.split(r"\s[-\u2013\u2014]\s", text) if part.strip()]
    if len(dash_parts) >= 2 and _looks_like_cv_date_line(dash_parts[-1]):
        return " - ".join(dash_parts[:-1]), dash_parts[-1]

    return text, ""


def _looks_like_preview_project_heading(line: str, next_line: str = "") -> bool:
    text = str(line or "").strip()
    if not text or text.startswith(("-", "*", "\u2022")):
        return False
    if _looks_like_cv_section_header(text) or len(text) > 130:
        return False
    if "|" in text:
        return True
    return bool(next_line and len(next_line) <= 40 and _looks_like_cv_date_line(next_line))


def _build_preview_project_items(lines: list[str]) -> list[dict[str, Any]]:
    projects: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    def flush_current() -> None:
        nonlocal current
        if current is None:
            return
        title = str(current.get("title") or "").strip()
        period = str(current.get("period") or "").strip()
        bullets = [str(item).strip() for item in current.get("bullets") or [] if str(item).strip()]
        if title or period or bullets:
            projects.append(
                {
                    "title": title or "Project",
                    "period": period,
                    "bulletsText": "\n".join(bullets),
                    "bullets": bullets,
                }
            )
        current = None

    for index, raw_line in enumerate(lines):
        line = str(raw_line or "").strip()
        if not line or _looks_like_cv_section_header(line):
            continue
        next_line = str(lines[index + 1] or "").strip() if index + 1 < len(lines) else ""
        normalized_bullet = re.sub(r"^\s*[-*\u2022]\s*", "", line).strip()

        if current is None:
            if line.startswith(("-", "*", "\u2022")):
                continue
            title, period = _split_preview_project_heading(line)
            current = {
                "title": title,
                "period": period,
                "bullets": [],
            }
            continue

        if _looks_like_preview_project_heading(line, next_line):
            flush_current()
            title, period = _split_preview_project_heading(line)
            current = {
                "title": title,
                "period": period,
                "bullets": [],
            }
            continue

        if not current.get("period") and _looks_like_cv_date_line(line) and len(line) <= 40:
            current["period"] = line
            continue

        if normalized_bullet:
            current.setdefault("bullets", []).append(normalized_bullet)

    flush_current()
    return projects[:6]


def _apply_cv_custom_section_decisions(
    profile: dict[str, Any],
    custom_sections: list[dict[str, Any]],
    section_decisions: list[dict[str, str]],
) -> dict[str, Any]:
    rendered_custom_sections: list[dict[str, Any]] = []
    detected_custom_sections: list[dict[str, Any]] = []

    for section in custom_sections:
        heading = str(section.get("heading") or "").strip() or "Additional Information"
        lines = _normalize_cv_section_lines(section.get("lines") or section.get("content") or "", limit=24)
        section_id = str(section.get("section_id") or section.get("id") or "").strip() or _custom_cv_section_id(
            heading,
            len(detected_custom_sections),
        )
        if _looks_like_cv_language_entry_line(heading, allow_plain_language=True) and not lines:
            profile["languages"] = _dedupe_preview_values(
                list(profile.get("languages") or []) + [heading],
                limit=20,
            )
            continue
        normalized_section = {
            "section_id": section_id,
            "heading": heading,
            "lines": lines,
            "content": "\n".join(lines),
        }
        decision = _decision_for_custom_section(normalized_section, section_decisions)
        action = str(decision.get("action") or "keep").strip().lower()
        target_section = str(decision.get("target_section") or "").strip().lower()
        detected_custom_sections.append(
            {
                **normalized_section,
                "action": action,
                "target_section": target_section,
            }
        )

        if action == "hide":
            continue
        if action == "map" and target_section in _CV_SECTION_DECISION_TARGETS:
            if target_section == "summary":
                existing_summary = str(profile.get("summary") or "").strip()
                section_text = " ".join(lines).strip()
                if section_text:
                    profile["summary"] = f"{existing_summary}\n\n{section_text}".strip()
            elif target_section == "skills":
                merged_skills = list(profile.get("competencies") or [])
                for line in lines:
                    for piece in re.split(r"[,;|]|\s+\u2022\s+", line):
                        value = piece.strip(" .-")
                        if value:
                            merged_skills.append(value)
                profile["competencies"] = _dedupe_preview_values(merged_skills, limit=35)
            elif target_section == "languages":
                profile["languages"] = _dedupe_preview_values(list(profile.get("languages") or []) + lines, limit=20)
            elif target_section == "projects":
                mapped_projects = _build_preview_project_items(lines)
                if not mapped_projects and (heading or lines):
                    mapped_projects = [
                        {
                            "title": heading,
                            "period": "",
                            "bulletsText": "\n".join(lines),
                            "bullets": lines,
                        }
                    ]
                profile["projects"] = list(profile.get("projects") or []) + mapped_projects
            elif target_section == "education":
                profile["education"] = list(profile.get("education") or []) + [
                    {
                        "degree_title": heading,
                        "institution": "",
                        "period": "",
                        "details": lines,
                        "detailsText": "\n".join(lines),
                    }
                ]
            elif target_section == "experience":
                mapped_experience = _build_preview_experience_items(lines)
                if not mapped_experience and (heading or lines):
                    mapped_experience = [
                        {
                            "title": heading,
                            "role": heading,
                            "company": "",
                            "period": "",
                            "bulletsText": "\n".join(lines),
                            "bullets": lines,
                        }
                    ]
                profile["recent_experience"] = list(profile.get("recent_experience") or []) + mapped_experience
            continue

        rendered_custom_sections.append(normalized_section)

    profile["custom_sections"] = rendered_custom_sections
    profile["detected_custom_sections"] = detected_custom_sections
    profile["section_decisions"] = section_decisions
    return profile


def _dedupe_preview_values(items: list[Any], *, limit: int) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = str(item or "").strip()
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        values.append(value)
        seen.add(key)
        if len(values) >= limit:
            break
    return values


def _build_workspace_cv_preview_profile(
    cv_text: str,
    shared_profile: dict[str, Any],
    *,
    asset_display_name: str = "",
    parsed_profile: dict[str, Any] | None = None,
    section_decisions: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    normalized_shared_profile = normalize_profile_payload(shared_profile)
    normalized_parsed_profile = normalize_profile_payload(parsed_profile)
    parsed_sections = _parse_cv_sections(cv_text)
    preamble_lines = _cv_preamble_lines(cv_text)
    display_lines = [line for line in preamble_lines if not _looks_like_cv_contact_line(line)]

    name = str(normalized_parsed_profile.get("name") or normalized_shared_profile.get("name") or "").strip()
    if not name and display_lines:
        name = display_lines[0]
    if not name:
        name = asset_display_name or "Candidate"

    role_title = str(normalized_parsed_profile.get("role_title") or normalized_shared_profile.get("role_title") or "").strip()
    if not role_title and len(display_lines) >= 2:
        role_title = display_lines[1]

    summary = str(normalized_parsed_profile.get("summary") or parsed_sections.get("summary") or "").strip()
    if not summary:
        summary = " ".join(_cv_summary_lines(cv_text)).strip()
    if not summary:
        summary_candidates = display_lines[2:] if len(display_lines) > 2 else display_lines[1:]
        summary = " ".join(summary_candidates).strip()
    if not summary:
        summary = str(normalized_shared_profile.get("summary") or "").strip()

    competencies = [
        str(item).strip()
        for item in (
            normalized_parsed_profile.get("competencies")
            or parsed_sections.get("competencies")
            or normalized_shared_profile.get("competencies")
            or []
        )
        if str(item).strip()
    ]
    languages = [
        str(item).strip()
        for item in (
            normalized_parsed_profile.get("languages")
            or parsed_sections.get("languages")
            or normalized_shared_profile.get("languages")
            or []
        )
        if str(item).strip()
    ]
    recent_experience = [
        {
            "title": str(item.get("title") or item.get("role") or "").strip(),
            "role": str(item.get("role") or item.get("title") or "").strip(),
            "company": str(item.get("company") or "").strip(),
            "period": str(item.get("period") or "").strip(),
            "bulletsText": str(item.get("bulletsText") or "").strip(),
            "bullets": list(item.get("bullets") or []),
        }
        for item in (normalized_parsed_profile.get("recent_experience") or [])
        if isinstance(item, dict)
    ]
    if not recent_experience:
        recent_experience = _build_preview_experience_items(parsed_sections.get("experience_lines") or [])
    if not recent_experience:
        recent_experience = [
            {
                "title": str(item.get("title") or item.get("role") or "").strip(),
                "role": str(item.get("role") or item.get("title") or "").strip(),
                "company": str(item.get("company") or "").strip(),
                "period": str(item.get("period") or "").strip(),
                "bulletsText": str(item.get("bulletsText") or "").strip(),
                "bullets": list(item.get("bullets") or []),
            }
            for item in (normalized_shared_profile.get("recent_experience") or [])
            if isinstance(item, dict)
        ]
    education = [
        {
            "degree_title": str(item.get("degree_title") or "").strip(),
            "institution": str(item.get("institution") or "").strip(),
            "period": str(item.get("period") or "").strip(),
            "details": list(item.get("details") or []),
            "detailsText": str(item.get("detailsText") or "").strip(),
        }
        for item in (normalized_parsed_profile.get("education") or normalized_shared_profile.get("education") or [])
        if isinstance(item, dict)
    ]
    projects = [
        {
            "title": str(item.get("title") or item.get("name") or "").strip(),
            "period": str(item.get("period") or item.get("date") or item.get("year") or "").strip(),
            "bulletsText": str(item.get("bulletsText") or "").strip(),
            "bullets": list(item.get("bullets") or []),
        }
        for item in (normalized_parsed_profile.get("projects") or normalized_shared_profile.get("projects") or [])
        if isinstance(item, dict)
    ]
    if not projects:
        projects = _build_preview_project_items(parsed_sections.get("project_lines") or [])

    photo_data_url = str(shared_profile.get("photo_data_url") or shared_profile.get("avatar_url") or "").strip()
    avatar_url = str(shared_profile.get("avatar_url") or shared_profile.get("photo_data_url") or "").strip()

    custom_sections = _normalize_cv_custom_sections(
        normalized_parsed_profile.get("custom_sections")
        or parsed_sections.get("custom_sections")
        or normalized_shared_profile.get("custom_sections")
        or []
    )
    normalized_section_decisions = _normalize_cv_section_decisions(section_decisions or [])

    profile = {
        "name": name,
        "role_title": role_title,
        "industry": str(normalized_parsed_profile.get("industry") or normalized_shared_profile.get("industry") or "").strip(),
        "location": str(normalized_parsed_profile.get("location") or normalized_shared_profile.get("location") or "").strip(),
        "email": str(normalized_parsed_profile.get("email") or normalized_shared_profile.get("email") or "").strip(),
        "website": str(normalized_parsed_profile.get("website") or normalized_shared_profile.get("website") or "").strip(),
        "linkedin_url": str(
            normalized_parsed_profile.get("linkedin_url") or normalized_shared_profile.get("linkedin_url") or ""
        ).strip(),
        "github_url": str(
            normalized_parsed_profile.get("github_url") or normalized_shared_profile.get("github_url") or ""
        ).strip(),
        "summary": summary,
        "competencies": competencies,
        "languages": languages,
        "recent_experience": recent_experience,
        "education": education,
        "projects": projects,
        "photo_data_url": photo_data_url,
        "avatar_url": avatar_url,
    }
    return _apply_cv_custom_section_decisions(profile, custom_sections, normalized_section_decisions)


def _parse_multipart_file(content_type_header: str, body: bytes) -> tuple[str, bytes]:
    """Parse a multipart/form-data body and return (filename, file_bytes).

    Returns ('', b'') if parsing fails or no file part is found.
    """
    boundary_match = re.search(r'boundary=([^;\s]+)', content_type_header)
    if not boundary_match:
        return "", b""
    boundary = boundary_match.group(1).strip('"')

    # email.parser expects a header block — prepend a synthetic MIME header
    synthetic = (
        f"Content-Type: multipart/form-data; boundary={boundary}\r\n\r\n"
    ).encode("latin-1")
    parser = BytesFeedParser()
    parser.feed(synthetic + body)
    msg = parser.close()

    for part in msg.get_payload():
        content_disposition = part.get("Content-Disposition", "")
        if 'filename="' not in content_disposition and "filename*=" not in content_disposition:
            continue
        filename_match = re.search(r'filename="([^"]+)"', content_disposition)
        filename = filename_match.group(1) if filename_match else "upload"
        return filename, part.get_payload(decode=True) or b""

    return "", b""


def _guess_image_extension(filename: str, file_bytes: bytes) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg"}:
        return ".jpg" if suffix == ".jpeg" else suffix
    if file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if file_bytes[:3] == b"\xff\xd8\xff":
        return ".jpg"
    return ""


def _store_profile_photo(user, file_bytes: bytes, extension: str) -> tuple[str, str]:
    profile_dir = Path("user_config") / "profile_photos"
    profile_dir.mkdir(parents=True, exist_ok=True)
    normalized_extension = ".jpg" if extension == ".jpeg" else extension
    photo_path = profile_dir / f"{user.user_id}{normalized_extension}"
    photo_path.write_bytes(file_bytes)
    mime_type = "image/png" if normalized_extension == ".png" else "image/jpeg"
    data_url = f"data:{mime_type};base64,{base64.b64encode(file_bytes).decode('ascii')}"
    return str(photo_path.resolve()), data_url


def _workspace_summary(workspace) -> dict:
    return {
        "id": workspace.id,
        "name": workspace.name,
        "description": workspace.description,
        "workflow_template_id": workspace.workflow_template_id,
        "owner_user_id": workspace.owner_user_id,
        "workspace_type": workspace.workspace_type,
        "automation_flow": str(workspace.metadata.get("automation_flow") or workspace.settings.get("automation_flow") or ""),
        "settings": dict(workspace.settings),
        "feature_flags": workspace.feature_flags,
        "profiles": [profile.to_dict() for profile in workspace.profiles],
        "prompt_sets": [prompt_set.to_dict() for prompt_set in workspace.prompt_sets],
        "sources": [source.to_dict() for source in workspace.sources],
        "metadata": dict(workspace.metadata),
        "schedule": _workspace_schedule_summary(workspace),
    }


def _workflow_template_summary(template) -> dict:
    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "stages": [stage.to_dict() for stage in template.stages],
        "default_run_settings": dict(template.default_run_settings),
    }


def _component_summary(descriptor) -> dict:
    return {
        "id": descriptor.id,
        "kind": descriptor.kind,
        "name": descriptor.name,
        "description": descriptor.description,
        "metadata": dict(descriptor.metadata),
    }


def _run_summary(run) -> dict:
    return {
        "id": run.id,
        "workspace_id": run.workspace_id,
        "workflow_template_id": run.workflow_template_id,
        "status": run.status,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
        "queued_at": run.queued_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "attempt_count": run.attempt_count,
        "max_attempts": run.max_attempts,
        "current_stage_id": run.current_stage_id,
        "last_error": run.last_error,
        "stage_results": [result.to_dict() for result in run.stage_results],
        "final_job_set_keys": run.final_job_set_keys,
        "progress": dict(run.metadata.get("progress") or {}),
        "is_test_run": bool(run.is_test_run),
        "run_mode": "test" if run.is_test_run else "normal",
    }


def _iso_to_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _run_progress_payload(run, *, now: datetime | None = None) -> dict[str, Any]:
    progress = dict(run.metadata.get("progress") or {})
    if not progress:
        return {}
    resolved_now = now or datetime.now(timezone.utc)
    started_at = _iso_to_datetime(progress.get("started_at"))
    last_progress_at = _iso_to_datetime(progress.get("last_progress_at"))
    elapsed_seconds = 0
    idle_seconds = 0
    if started_at is not None:
        elapsed_seconds = max(int((resolved_now - started_at).total_seconds()), 0)
    if last_progress_at is not None:
        idle_seconds = max(int((resolved_now - last_progress_at).total_seconds()), 0)
    health = "active"
    health_label = "Running normally"
    if idle_seconds >= 900:
        health = "stale"
        health_label = "Possibly stale"
    elif idle_seconds >= 180:
        health = "slow"
        health_label = "Slow but active"
    return {
        "stage_id": str(progress.get("stage_id") or run.current_stage_id or ""),
        "stage_type": str(progress.get("stage_type") or ""),
        "stage_name": str(progress.get("stage_name") or ""),
        "stage_description": str(progress.get("stage_description") or ""),
        "status": str(progress.get("status") or run.status or ""),
        "message": str(progress.get("message") or ""),
        "started_at": str(progress.get("started_at") or ""),
        "last_progress_at": str(progress.get("last_progress_at") or ""),
        "elapsed_seconds": elapsed_seconds,
        "idle_seconds": idle_seconds,
        "health": health,
        "health_label": health_label,
        "counters": dict(progress.get("counters") or {}),
        "current_item": dict(progress.get("current_item") or {}),
        "recent_failures": [dict(item) for item in progress.get("recent_failures") or [] if isinstance(item, dict)],
    }


def _workflow_snapshot_for_run(application, run) -> dict:
    if run.run_plan and isinstance(run.run_plan.workflow_snapshot, dict) and run.run_plan.workflow_snapshot:
        return dict(run.run_plan.workflow_snapshot)
    workflow = application.repositories.workspace_repository.get_workflow_template(run.workflow_template_id)
    return workflow.to_dict()


def _workspace_snapshot_for_run(run) -> WorkspaceDefinition | None:
    if run.run_plan and isinstance(run.run_plan.workspace_snapshot, dict) and run.run_plan.workspace_snapshot:
        return WorkspaceDefinition.from_dict(run.run_plan.workspace_snapshot)
    return None


def _enabled_workflow_stage_ids(workflow_snapshot: Mapping[str, Any] | None) -> list[str]:
    stage_ids: list[str] = []
    for stage in (workflow_snapshot or {}).get("stages") or []:
        if not isinstance(stage, Mapping):
            continue
        if stage.get("enabled") is False:
            continue
        stage_id = str(stage.get("stage_id") or "").strip()
        if stage_id:
            stage_ids.append(stage_id)
    return stage_ids


def _infer_terminal_run_status(run, workflow_snapshot: Mapping[str, Any] | None = None) -> str:
    current_status = str(getattr(run, "status", "") or "").strip()
    if current_status not in _ACTIVE_RUN_STATUSES:
        return current_status
    stage_results = list(getattr(run, "stage_results", []) or [])
    if not stage_results:
        return current_status
    if any(str(getattr(result, "status", "") or "") == STAGE_STATUS_FAILED for result in stage_results):
        return RUN_STATUS_FAILED

    enabled_stage_ids = _enabled_workflow_stage_ids(workflow_snapshot)
    if not enabled_stage_ids:
        return current_status
    results_by_stage = {
        str(getattr(result, "stage_id", "") or ""): str(getattr(result, "status", "") or "")
        for result in stage_results
    }
    if all(results_by_stage.get(stage_id) in _TERMINAL_STAGE_STATUSES for stage_id in enabled_stage_ids):
        return RUN_STATUS_COMPLETED
    return current_status


def _latest_stage_finished_at(run) -> str:
    return max(
        (
            str(getattr(result, "finished_at", "") or "")
            for result in getattr(run, "stage_results", []) or []
            if str(getattr(result, "finished_at", "") or "").strip()
        ),
        default="",
    )


def _run_with_inferred_terminal_status(run, workflow_snapshot: Mapping[str, Any] | None = None):
    inferred_status = _infer_terminal_run_status(run, workflow_snapshot)
    if inferred_status == str(getattr(run, "status", "") or ""):
        return run
    readable_run = deepcopy(run)
    readable_run.status = inferred_status
    readable_run.metadata = dict(getattr(readable_run, "metadata", {}) or {})
    if inferred_status == RUN_STATUS_COMPLETED:
        readable_run.current_stage_id = ""
        readable_run.last_error = ""
        readable_run.finished_at = readable_run.finished_at or _latest_stage_finished_at(readable_run)
        readable_run.updated_at = readable_run.finished_at or readable_run.updated_at
        readable_run.metadata.pop("progress", None)
    return readable_run


def _job_workspace_url(
    run_id: str,
    job_id: str,
    *,
    mode: str = "context_only",
    source_stage: str = "",
    reason_summary: str = "",
) -> str:
    params = {"mode": str(mode or "context_only").strip() or "context_only"}
    if source_stage:
        params["source_stage"] = str(source_stage).strip()
    if reason_summary:
        params["reason_summary"] = str(reason_summary).strip()
    query = urlencode(params)
    return f"/job-workspaces/{run_id}/{job_id}" + (f"?{query}" if query else "")


def _customer_job_payload(
    job_payload: dict,
    *,
    run_id: str = "",
    review=None,
    document_count: int = 0,
    documents: list[dict] | None = None,
) -> dict:
    review_meta = dict(review.metadata or {}) if review else {}
    tracker_status = str(review_meta.get("tracker_status") or "")
    application_status = normalize_application_status(
        review_meta.get("application_status") or tracker_status,
        default="" if not tracker_status else "Unknown",
    )
    source_label = str(
        job_payload.get("portal")
        or job_payload.get("source_label")
        or job_payload.get("source_type")
        or "unknown"
    )
    application_requirements = _application_requirement_status(
        _application_requirements_from_job_payload(job_payload),
        documents=documents or [],
    )
    return {
        "job_id": str(job_payload.get("job_id") or ""),
        "title": str(job_payload.get("title") or ""),
        "company": str(job_payload.get("company") or ""),
        "location": str(job_payload.get("location_raw") or job_payload.get("location") or ""),
        "apply_link": str(job_payload.get("apply_link") or job_payload.get("link") or job_payload.get("source_url") or ""),
        "linkedin_link": str(job_payload.get("linkedin_link") or job_payload.get("link") or ""),
        "source_type": str(job_payload.get("source_type") or ""),
        "source_label": source_label,
        "manual_approved": bool(job_payload.get("manual_approved") or False),
        "priority_rank": job_payload.get("priority_rank"),
        "priority_bucket": str(job_payload.get("priority_bucket") or ""),
        "filter_status": str(job_payload.get("filter_status") or ""),
        "review_id": review.review_id if review else "",
        "review_status": review.status if review else "",
        "decision": review.decision if review else "",
        "tracker_status": tracker_status,
        "application_status": application_status,
        "document_count": max(0, int(document_count or 0)),
        "application_requirements": application_requirements,
        "application_warnings": list(application_requirements.get("warnings") or []),
        "job_workspace_url": (
            _job_workspace_url(str(run_id or ""), str(job_payload.get("job_id") or ""))
            if run_id and str(job_payload.get("job_id") or "").strip()
            else ""
        ),
    }


_CUSTOMER_LANGUAGE_ALIASES: dict[str, tuple[str, ...]] = {
    "Arabic": ("arabic",),
    "Chinese": ("chinese", "mandarin", "cantonese"),
    "Czech": ("czech",),
    "Danish": ("danish",),
    "Dutch": ("dutch",),
    "English": ("english",),
    "Finnish": ("finnish",),
    "French": ("french", "francais", "français"),
    "German": ("german", "deutsch"),
    "Greek": ("greek",),
    "Hebrew": ("hebrew",),
    "Hindi": ("hindi",),
    "Italian": ("italian",),
    "Japanese": ("japanese",),
    "Korean": ("korean",),
    "Norwegian": ("norwegian",),
    "Polish": ("polish",),
    "Portuguese": ("portuguese",),
    "Romanian": ("romanian",),
    "Russian": ("russian",),
    "Spanish": ("spanish", "espanol", "español"),
    "Swedish": ("swedish",),
    "Turkish": ("turkish",),
    "Ukrainian": ("ukrainian",),
    "Urdu": ("urdu",),
}
_CUSTOMER_CEFR_LEVEL_RANK = {
    "A1": 1,
    "A2": 2,
    "B1": 3,
    "B2": 4,
    "C1": 5,
    "C2": 6,
}
_CUSTOMER_LANGUAGE_LEVEL_HINTS = (
    ("C2", ("native", "bilingual")),
    ("C1", ("fluent", "professional", "business fluent", "verhandlungssicher", "full professional")),
    ("B2", ("upper intermediate",)),
    ("B1", ("intermediate",)),
    ("A2", ("elementary", "basic")),
    ("A1", ("beginner",)),
)


def _customer_extract_language_name(text: str) -> str:
    searchable = str(text or "")
    earliest_hit: tuple[int, str] | None = None
    for canonical_name, aliases in _CUSTOMER_LANGUAGE_ALIASES.items():
        for alias in aliases:
            match = re.search(
                rf"(?<![A-Za-z]){re.escape(alias)}(?![A-Za-z])",
                searchable,
                flags=re.IGNORECASE,
            )
            if match and (earliest_hit is None or match.start() < earliest_hit[0]):
                earliest_hit = (match.start(), canonical_name)
    return earliest_hit[1] if earliest_hit else ""


def _customer_extract_language_level(text: str) -> str:
    searchable = str(text or "")
    matches = re.findall(r"\b(A1|A2|B1|B2|C1|C2)\b", searchable, flags=re.IGNORECASE)
    if matches:
        normalized = [str(item).upper() for item in matches]
        return max(normalized, key=lambda item: _CUSTOMER_CEFR_LEVEL_RANK.get(item, 0))
    folded = searchable.casefold()
    for level, hints in _CUSTOMER_LANGUAGE_LEVEL_HINTS:
        if any(hint in folded for hint in hints):
            return level
    return ""


def _customer_profile_language_levels(user) -> dict[str, str]:
    profile = dict((user.metadata or {}).get("profile") or {})
    language_levels: dict[str, str] = {}
    for item in profile.get("languages") or []:
        raw_value = str(item or "").strip()
        if not raw_value:
            continue
        language_name = _customer_extract_language_name(raw_value)
        if not language_name:
            continue
        level = _customer_extract_language_level(raw_value)
        existing_level = language_levels.get(language_name, "")
        if not existing_level or _CUSTOMER_CEFR_LEVEL_RANK.get(level, 0) >= _CUSTOMER_CEFR_LEVEL_RANK.get(existing_level, 0):
            language_levels[language_name] = level
    return language_levels


def _customer_excluded_reason(entry: dict, user) -> dict[str, object]:
    reason_code = str(entry.get("reason_code") or "unknown")
    raw_summary = str(entry.get("reason_summary") or "").strip()
    raw_details = [str(item).strip() for item in entry.get("details") or [] if str(item).strip()]
    combined_text = " ".join([raw_summary, *raw_details]).strip()

    if reason_code == "language_mismatch":
        language_name = _customer_extract_language_name(combined_text)
        required_level = _customer_extract_language_level(combined_text)
        profile_language_levels = _customer_profile_language_levels(user)
        saved_level = profile_language_levels.get(language_name, "") if language_name else ""

        if "appears to be written in" in combined_text.casefold() and language_name:
            return {
                "reason_code": "listing_language_excluded",
                "reason_label": "Listing language excluded",
                "reason_summary": (
                    f"This listing appears to be written in {language_name}, "
                    "and this workspace is configured to skip that listing language."
                ),
                "details": [f"Detected listing language: {language_name}"],
            }

        if language_name and language_name not in profile_language_levels:
            return {
                "reason_code": "required_language_missing",
                "reason_label": "Required language not listed",
                "reason_summary": f"This role requires {language_name}, which is not listed in your saved languages.",
                "details": [f"Required language: {language_name}"],
            }
        if (
            language_name
            and required_level
            and saved_level
            and _CUSTOMER_CEFR_LEVEL_RANK.get(saved_level, 0) < _CUSTOMER_CEFR_LEVEL_RANK.get(required_level, 0)
        ):
            return {
                "reason_code": "language_level_not_reached",
                "reason_label": "Language level not yet reached",
                "reason_summary": (
                    f"This role requires {language_name} at {required_level} level, "
                    f"which is above your saved level."
                ),
                "details": [
                    f"Required language: {language_name}",
                    f"Required level: {required_level}",
                    f"Saved level: {saved_level}",
                ],
            }
        if language_name and required_level and language_name in profile_language_levels and not saved_level:
            return {
                "reason_code": "language_level_missing",
                "reason_label": "Language level missing",
                "reason_summary": (
                    f"This role requires {language_name} at {required_level} level, "
                    "but your saved language level is missing."
                ),
                "details": [
                    f"Required language: {language_name}",
                    f"Required level: {required_level}",
                    "Saved level: not set",
                ],
            }
        if language_name:
            return {
                "reason_code": "language_mismatch",
                "reason_label": "Language mismatch",
                "reason_summary": f"This role requires a {language_name} language match that is not currently met.",
                "details": [f"Required language: {language_name}"],
            }
        return {
            "reason_code": "language_mismatch",
            "reason_label": "Language mismatch",
            "reason_summary": "This role requires a language match that is not currently met.",
            "details": [],
        }

    reason_messages = {
        "keyword_mismatch": (
            "Role mismatch",
            "This role does not match the target role for this workspace.",
        ),
        "seniority_mismatch": (
            "Experience level mismatch",
            "This role is outside the target experience level for this workspace.",
        ),
        "location_mismatch": (
            "Location mismatch",
            "This role is outside the location scope for this workspace.",
        ),
        "duplicate": (
            "Already tracked",
            "This job already appears in your tracker or elsewhere in this run.",
        ),
        "source_validation_failed": (
            "Listing not usable",
            "This job listing could not be used reliably for document generation.",
        ),
        "manual_rejection": (
            "Not selected",
            "This job was not selected for document generation.",
        ),
        "unknown": (
            "Not selected",
            raw_summary or "This job was not selected for document generation.",
        ),
    }
    reason_label, reason_summary = reason_messages.get(
        reason_code,
        ("Not selected", raw_summary or "This job was not selected for document generation."),
    )
    return {
        "reason_code": reason_code,
        "reason_label": reason_label,
        "reason_summary": reason_summary,
        "details": [],
    }


def _customer_excluded_job_payload(entry: dict, user) -> dict:
    customer_reason = _customer_excluded_reason(entry, user)
    return {
        "job_id": str(entry.get("job_id") or ""),
        "title": str(entry.get("title") or ""),
        "company": str(entry.get("company") or ""),
        "apply_link": str(entry.get("apply_link") or ""),
        "reason_code": str(customer_reason.get("reason_code") or ""),
        "reason_label": str(customer_reason.get("reason_label") or ""),
        "reason_summary": str(customer_reason.get("reason_summary") or ""),
        "details": [str(item) for item in customer_reason.get("details") or [] if str(item).strip()],
        "source_stage": str(entry.get("source_stage") or ""),
        "recorded_at": str(entry.get("recorded_at") or ""),
        "workspace_editor_url": str(entry.get("workspace_editor_url") or ""),
        "job_workspace_url": _job_workspace_url(
            str(entry.get("run_id") or ""),
            str(entry.get("job_id") or ""),
            mode="pre_generation",
            source_stage=str(entry.get("source_stage") or ""),
            reason_summary=str(customer_reason.get("reason_summary") or ""),
        ),
        "can_generate_documents": bool(entry.get("can_requeue") or False),
        "create_documents_run_id": str(entry.get("requeue_run_id") or ""),
        "create_documents_run_status": str(entry.get("requeue_run_status") or ""),
        "create_documents_run_finished_at": str(entry.get("requeue_run_finished_at") or ""),
        "create_documents_run_url": str(entry.get("requeue_run_url") or ""),
    }


def _count_run_tracker_items(reviews: list[object], job_sets: Mapping[str, list[object]]) -> int:
    jobs_by_id: dict[str, object] = {}
    for jobs in job_sets.values():
        for job in jobs:
            job_id = str(getattr(job, "job_id", "") or "")
            if job_id:
                jobs_by_id[job_id] = job

    tracker_count = 0
    counted_posting_urls: set[str] = set()
    for review in reviews:
        review_meta = dict(getattr(review, "metadata", {}) or {})
        tracker_status = str(review_meta.get("tracker_status") or "")
        if getattr(review, "decision", "") != "approved" and not tracker_status:
            continue
        job = jobs_by_id.get(str(getattr(review, "job_id", "") or ""))
        posting_url = canonical_posting_url(job.to_dict() if job else {})
        if posting_url:
            if posting_url in counted_posting_urls:
                continue
            counted_posting_urls.add(posting_url)
        tracker_count += 1
    return tracker_count


def _collect_run_customer_view(application, user, run) -> dict:
    payload_started_at = perf_counter()
    payload_timings_ms: dict[str, float] = {}

    def record_phase(name: str, started_at: float) -> None:
        payload_timings_ms[name] = round((perf_counter() - started_at) * 1000, 2)

    phase_started = perf_counter()
    workflow_snapshot = _workflow_snapshot_for_run(application, run)
    run = _run_with_inferred_terminal_status(run, workflow_snapshot)
    run_is_active = str(run.status or "") in _ACTIVE_RUN_STATUSES
    record_phase("workflow_snapshot", phase_started)

    phase_started = perf_counter()
    progress = _run_progress_payload(run)
    record_phase("progress", phase_started)

    phase_started = perf_counter()
    scrapeops_usage = application.get_scrapeops_usage_summary(run_id=run.id)
    record_phase("scrapeops_usage", phase_started)

    phase_started = perf_counter()
    run_snapshot = _load_run_read_snapshot(
        application,
        [run],
        include_artifacts=True,
        include_reviews=True,
        include_blobs=True,
    )
    run_blobs = run_snapshot["blobs"].get(run.id, {})
    capped_sites = run_blobs.get("capped_sites", [])
    record_phase("capped_sites", phase_started)

    phase_started = perf_counter()
    workflow_stages = [
        dict(stage)
        for stage in workflow_snapshot.get("stages") or []
        if isinstance(stage, dict)
    ]
    record_phase("workflow_stages", phase_started)

    phase_started = perf_counter()
    if run_is_active:
        historical_runs = [
            candidate
            for candidate in application.list_runs(limit=200, offset=0, status="completed")
            if candidate.id != run.id
            and candidate.workflow_template_id == run.workflow_template_id
            and application.user_can_access_run(user, candidate)
        ]
        eta = build_run_eta(run, workflow_stages, historical_runs)
    else:
        eta = {"state": "unavailable", "calculated_at": datetime.now(timezone.utc).isoformat()}
    record_phase("eta", phase_started)

    phase_started = perf_counter()
    workspace = _workspace_snapshot_for_run(run)
    if workspace is None:
        workspace = application.get_workspace(run.workspace_id)
    record_phase("workspace", phase_started)

    phase_started = perf_counter()
    reviews = run_snapshot["reviews"].get(run.id, [])
    record_phase("reviews", phase_started)

    phase_started = perf_counter()
    reviews_by_job = {review.job_id: review for review in reviews}
    job_sets = run_snapshot["job_sets"].get(run.id, {})
    record_phase("job_sets", phase_started)

    phase_started = perf_counter()
    documents = _collect_document_entries(
        application,
        user,
        run_id=run.id,
        run_record=run,
        workspace_record=workspace,
        run_jobs=_ordered_run_jobs_for_document_lookup(run, job_sets),
        artifacts_by_run=run_snapshot["artifacts"],
        access_checked=True,
    )
    record_phase("documents", phase_started)

    document_count_by_job: dict[str, int] = {}
    documents_by_job: dict[str, list[dict]] = {}
    for document in documents:
        job_id = str(document.get("job_id") or "")
        if job_id:
            document_count_by_job[job_id] = document_count_by_job.get(job_id, 0) + 1
            documents_by_job.setdefault(job_id, []).append(document)

    phase_started = perf_counter()
    rejected_entries = _collect_rejected_job_entries(
        application,
        user,
        run_id=run.id,
        run_record=run,
        workspace_record=workspace,
        review_records=reviews,
        run_blobs=run_blobs,
        access_checked=True,
    )
    record_phase("rejected_entries", phase_started)

    rejected_by_stage: dict[str, list[dict]] = {}
    for entry in rejected_entries:
        rejected_by_stage.setdefault(str(entry.get("source_stage") or ""), []).append(entry)

    stage_results_by_id = {result.stage_id: result for result in run.stage_results}
    included_job_ids: set[str] = set()
    excluded_job_ids: set[str] = set()
    included_jobs_by_id: dict[str, dict[str, object]] = {}
    excluded_jobs_by_id: dict[str, dict[str, object]] = {}
    stages: list[dict[str, object]] = []
    known_stage_ids = {str(stage.get("stage_id") or "") for stage in workflow_stages}

    for index, stage_definition in enumerate(workflow_stages, start=1):
        stage_id = str(stage_definition.get("stage_id") or "")
        output_key = str(stage_definition.get("output_key") or "")
        stage_result = stage_results_by_id.get(stage_id)
        status = str(stage_result.status if stage_result else "pending")
        included_jobs_raw = job_sets.get(output_key, []) if output_key else []
        included_jobs = []
        for job in included_jobs_raw:
            review = reviews_by_job.get(job.job_id)
            if review and review.decision == "duplicate":
                continue
            job_payload = job.to_dict()
            if job_payload.get("job_id"):
                included_job_ids.add(str(job_payload.get("job_id")))
            customer_job = _customer_job_payload(
                job_payload,
                run_id=run.id,
                review=review,
                document_count=document_count_by_job.get(job.job_id, 0),
                documents=documents_by_job.get(job.job_id, []),
            )
            included_jobs.append(customer_job)
            existing_customer_job = included_jobs_by_id.get(job.job_id)
            if existing_customer_job is None or int(customer_job.get("document_count") or 0) >= int(existing_customer_job.get("document_count") or 0):
                included_jobs_by_id[job.job_id] = customer_job
        excluded_jobs = []
        for item in rejected_by_stage.get(stage_id, []):
            job_id = str(item.get("job_id") or "")
            if job_id:
                excluded_job_ids.add(job_id)
            customer_excluded_job = _customer_excluded_job_payload(item, user)
            excluded_jobs.append(customer_excluded_job)
            if job_id and job_id not in excluded_jobs_by_id:
                excluded_jobs_by_id[job_id] = customer_excluded_job
        stages.append(
            {
                "stage_id": stage_id,
                "stage_type": str(stage_definition.get("stage_type") or ""),
                "stage_name": str(stage_definition.get("name") or stage_id),
                "stage_description": str(stage_definition.get("description") or ""),
                "position": index,
                "status": status,
                "is_current": bool(run.current_stage_id == stage_id and run.status in {"running", "queued", "planned", "cancel_requested"}),
                "started_at": str(stage_result.started_at if stage_result else ""),
                "finished_at": str(stage_result.finished_at if stage_result else ""),
                "error": str(stage_result.error if stage_result else ""),
                "metrics": dict(stage_result.metrics if stage_result else {}),
                "included_count": len(included_jobs),
                "excluded_count": len(excluded_jobs),
                "included_jobs": included_jobs,
                "excluded_jobs": excluded_jobs,
            }
        )

    extra_stage_names = {
        "manual_review": {
            "stage_name": "Manual Review",
            "stage_description": "Jobs rejected during later manual review or cleanup.",
        },
    }
    for source_stage, items in rejected_by_stage.items():
        if not source_stage or source_stage in known_stage_ids:
            continue
        excluded_jobs = []
        for item in items:
            job_id = str(item.get("job_id") or "")
            if job_id:
                excluded_job_ids.add(job_id)
            customer_excluded_job = _customer_excluded_job_payload(item, user)
            excluded_jobs.append(customer_excluded_job)
            if job_id and job_id not in excluded_jobs_by_id:
                excluded_jobs_by_id[job_id] = customer_excluded_job
        stage_meta = extra_stage_names.get(
            source_stage,
            {
                "stage_name": str(source_stage).replace("_", " ").title(),
                "stage_description": "Jobs excluded outside the main workflow stage list.",
            },
        )
        stages.append(
            {
                "stage_id": source_stage,
                "stage_type": "synthetic_review_stage",
                "stage_name": stage_meta["stage_name"],
                "stage_description": stage_meta["stage_description"],
                "position": len(stages) + 1,
                "status": "completed",
                "is_current": False,
                "started_at": "",
                "finished_at": "",
                "error": "",
                "metrics": {},
                "included_count": 0,
                "excluded_count": len(excluded_jobs),
                "included_jobs": [],
                "excluded_jobs": excluded_jobs,
            }
        )

    phase_started = perf_counter()
    tracker_item_count = _count_run_tracker_items(reviews, job_sets)
    record_phase("tracker_count", phase_started)

    phase_started = perf_counter()
    review_included_jobs = list(included_jobs_by_id.values())
    review_included_jobs.sort(key=lambda item: (str(item.get("title") or "").casefold(), str(item.get("company") or "").casefold(), str(item.get("job_id") or "")))
    review_excluded_jobs = list(excluded_jobs_by_id.values())
    review_excluded_jobs.sort(
        key=lambda item: (
            str(item.get("recorded_at") or ""),
            str(item.get("title") or "").casefold(),
            str(item.get("job_id") or ""),
        ),
        reverse=True,
    )
    current_stage_name = next(
        (
            str(stage.get("stage_name") or "")
            for stage in stages
            if str(stage.get("stage_id") or "") == str(run.current_stage_id or "")
        ),
        str(progress.get("stage_name") or ""),
    )
    generated_job_count = 0
    for key in run.final_job_set_keys or []:
        generated_job_count += len(job_sets.get(key, []))
    record_phase("final_assembly", phase_started)

    payload = {
        "run": {
            **_run_summary(run),
            "workspace_name": workspace.name,
            "workflow_name": str(workflow_snapshot.get("name") or run.workflow_template_id),
            "current_stage_name": current_stage_name,
            "progress": progress,
            "eta": eta,
            "scrapeops_usage": scrapeops_usage,
            "capped_sites": list(capped_sites or []),
        },
        "summary": {
            "stage_count": len(stages),
            "completed_stage_count": sum(1 for stage in stages if str(stage.get("status") or "") == "completed"),
            "included_job_count": len(included_job_ids),
            "excluded_job_count": len(excluded_job_ids),
            "generated_job_count": generated_job_count,
            "tracker_job_count": tracker_item_count,
            "excluded_ready_for_documents_count": sum(
                1
                for item in rejected_entries
                if bool(item.get("can_requeue") or False) and not str(item.get("requeue_run_id") or "")
            ),
            "run_health": str(progress.get("health") or ""),
            "run_health_label": str(progress.get("health_label") or ""),
            "runner_credits_consumed": int(scrapeops_usage.get("totals", {}).get("runner_credits") or 0),
        },
        "tracker": {
            "item_count": tracker_item_count,
            "href": "/tracker",
            "note": "Jobs with generated documents appear in Tracker automatically once the document run finishes.",
        },
        "review": {
            "included_count": len(review_included_jobs),
            "excluded_count": len(review_excluded_jobs),
            "included_jobs": review_included_jobs,
            "excluded_jobs": review_excluded_jobs,
        },
        "stages": stages,
    }
    payload_timings_ms["total"] = round((perf_counter() - payload_started_at) * 1000, 2)
    logging.getLogger("backend.api.customer_view").info(
        json.dumps(
            {
                "event": "customer_view_payload_timing",
                "run_id": str(run.id or ""),
                "workspace_id": str(run.workspace_id or ""),
                "run_status": str(run.status or ""),
                "timings_ms": payload_timings_ms,
                "counts": {
                    "stages": len(stages),
                    "documents": len(documents),
                    "rejected_entries": len(rejected_entries),
                    "reviews": len(reviews),
                    "job_sets": len(job_sets),
                    "tracker_items": tracker_item_count,
                },
            },
            separators=(",", ":"),
        )
    )
    return payload


def _workspace_option(workspace) -> dict:
    return {
        "id": workspace.id,
        "name": workspace.name,
        "workspace_type": workspace.workspace_type,
        "automation_flow": str(workspace.metadata.get("automation_flow") or workspace.settings.get("automation_flow") or ""),
    }


def _looks_like_internal_clerk_value(value: object) -> bool:
    normalized = str(value or "").strip()
    lowered = normalized.lower()
    return (
        not normalized
        or normalized.startswith("user_")
        or lowered.endswith("@clerk.local")
        or "@clerk.local" in lowered
    )


def _public_user_email(user) -> str:
    email = str(getattr(user, "email", "") or "").strip()
    return "" if _looks_like_internal_clerk_value(email) else email


def _public_user_display_name(user) -> str:
    display_name = str(getattr(user, "display_name", "") or "").strip()
    return "" if _looks_like_internal_clerk_value(display_name) else display_name


def _public_profile_text(value: object) -> str:
    text = str(value or "").strip()
    return "" if _looks_like_internal_clerk_value(text) else text


def _merge_profile_metadata(existing_profile: dict, profile_payload: dict, user) -> dict:
    normalized_existing = normalize_profile_payload(existing_profile)
    normalized_payload = normalize_profile_payload(profile_payload)
    payload_keys = set(profile_payload or {})
    public_display_name = _public_user_display_name(user)
    public_email = _public_user_email(user)
    payload_name = _public_profile_text(normalized_payload.get("name"))
    existing_name = _public_profile_text(normalized_existing.get("name"))
    payload_email = _public_profile_text(normalized_payload.get("email"))
    existing_email = _public_profile_text(normalized_existing.get("email"))
    merged = {
        "name": str(
            payload_name
            or existing_name
            or public_display_name
            or (public_email.split("@")[0] if public_email else "")
        ),
        "role_title": str(normalized_payload.get("role_title") or normalized_existing.get("role_title") or ""),
        "industry": str(normalized_payload.get("industry") or normalized_existing.get("industry") or ""),
        "email": str(payload_email or existing_email or public_email),
        "location": str(normalized_payload.get("location") or normalized_existing.get("location") or ""),
        "website": str(normalized_payload.get("website") or normalized_existing.get("website") or ""),
        "linkedin_url": str(normalized_payload.get("linkedin_url") or normalized_existing.get("linkedin_url") or ""),
        "github_url": str(normalized_payload.get("github_url") or normalized_existing.get("github_url") or ""),
        "avatar_url": (
            str(profile_payload.get("avatar_url") or "")
            if "avatar_url" in payload_keys
            else str(existing_profile.get("avatar_url") or "")
        ),
        "photo_data_url": (
            str(profile_payload.get("photo_data_url") or "")
            if "photo_data_url" in payload_keys
            else str(existing_profile.get("photo_data_url") or "")
        ),
        "photo_path": (
            str(profile_payload.get("photo_path") or "")
            if "photo_path" in payload_keys
            else str(existing_profile.get("photo_path") or "")
        ),
        "summary": str(normalized_payload.get("summary") or normalized_existing.get("summary") or ""),
        "competencies": (
            list(normalized_payload.get("competencies") or [])
            if ("competencies" in payload_keys or "skills" in payload_keys)
            else list(normalized_existing.get("competencies") or [])
        ),
        "languages": (
            list(normalized_payload.get("languages") or [])
            if "languages" in payload_keys
            else list(normalized_existing.get("languages") or [])
        ),
        "recent_experience": (
            [
                {
                    "title": str(item.get("title") or item.get("role") or ""),
                    "role": str(item.get("role") or item.get("title") or ""),
                    "company": str(item.get("company") or ""),
                    "period": str(item.get("period") or ""),
                    "bullets": list(item.get("bullets") or []),
                    "bulletsText": str(item.get("bulletsText") or ""),
                }
                for item in normalized_payload.get("recent_experience") or []
                if isinstance(item, dict)
            ]
            if "recent_experience" in payload_keys or "experience" in payload_keys
            else [
                {
                    "title": str(item.get("title") or item.get("role") or ""),
                    "role": str(item.get("role") or item.get("title") or ""),
                    "company": str(item.get("company") or ""),
                    "period": str(item.get("period") or ""),
                    "bullets": list(item.get("bullets") or []),
                    "bulletsText": str(item.get("bulletsText") or ""),
                }
                for item in normalized_existing.get("recent_experience") or []
                if isinstance(item, dict)
            ]
        ),
        "education": (
            [
                {
                    "degree_title": str(item.get("degree_title") or ""),
                    "institution": str(item.get("institution") or ""),
                    "period": str(item.get("period") or ""),
                    "details": list(item.get("details") or []),
                    "detailsText": str(item.get("detailsText") or ""),
                }
                for item in normalized_payload.get("education") or []
                if isinstance(item, dict)
            ]
            if "education" in payload_keys
            else [
                {
                    "degree_title": str(item.get("degree_title") or ""),
                    "institution": str(item.get("institution") or ""),
                    "period": str(item.get("period") or ""),
                    "details": list(item.get("details") or []),
                    "detailsText": str(item.get("detailsText") or ""),
                }
                for item in normalized_existing.get("education") or []
                if isinstance(item, dict)
            ]
        ),
        "projects": (
            [
                {
                    "title": str(item.get("title") or item.get("name") or ""),
                    "period": str(item.get("period") or item.get("date") or item.get("year") or ""),
                    "bullets": list(item.get("bullets") or []),
                    "bulletsText": str(item.get("bulletsText") or ""),
                }
                for item in normalized_payload.get("projects") or []
                if isinstance(item, dict)
            ]
            if "projects" in payload_keys or "project" in payload_keys
            else [
                {
                    "title": str(item.get("title") or item.get("name") or ""),
                    "period": str(item.get("period") or item.get("date") or item.get("year") or ""),
                    "bullets": list(item.get("bullets") or []),
                    "bulletsText": str(item.get("bulletsText") or ""),
                }
                for item in normalized_existing.get("projects") or []
                if isinstance(item, dict)
            ]
        ),
        "custom_sections": (
            [
                {
                    "section_id": str(item.get("section_id") or item.get("id") or ""),
                    "heading": str(item.get("heading") or item.get("title") or "Additional Information"),
                    "lines": list(item.get("lines") or []),
                    "content": str(item.get("content") or item.get("text") or ""),
                }
                for item in normalized_payload.get("custom_sections") or []
                if isinstance(item, dict)
            ]
            if "custom_sections" in payload_keys or "additional_sections" in payload_keys
            else [
                {
                    "section_id": str(item.get("section_id") or item.get("id") or ""),
                    "heading": str(item.get("heading") or item.get("title") or "Additional Information"),
                    "lines": list(item.get("lines") or []),
                    "content": str(item.get("content") or item.get("text") or ""),
                }
                for item in normalized_existing.get("custom_sections") or []
                if isinstance(item, dict)
            ]
        ),
    }
    if not merged["avatar_url"] and merged["photo_data_url"]:
        merged["avatar_url"] = merged["photo_data_url"]
    return merged


DEFAULT_WEB_CV_PALETTE = {
    "primary": "17324D",
    "accent": "D97706",
    "surface": "F8FAFC",
    "text": "0F172A",
    "muted": "475569",
    "border": "CBD5E1",
}


def _normalize_hex_color(value: str, fallback: str) -> str:
    candidate = str(value or "").strip().lstrip("#").upper()
    if re.fullmatch(r"[0-9A-F]{6}", candidate):
        return candidate
    return fallback


def _merge_web_cv_palette(existing_palette: dict, payload_palette: dict) -> dict:
    merged: dict[str, str] = {}
    for key, fallback in DEFAULT_WEB_CV_PALETTE.items():
        value = payload_palette.get(key) if key in payload_palette else existing_palette.get(key)
        merged[key] = _normalize_hex_color(str(value or ""), fallback)
    return merged


def _merge_string_list(existing_value: Any, payload_value: Any, *, limit: int = 25) -> list[str]:
    source = payload_value if payload_value is not None else existing_value
    if isinstance(source, list):
        raw_values = source
    elif source in (None, "", []):
        raw_values = []
    else:
        raw_values = [source]
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw_value in raw_values:
        normalized = str(raw_value or "").strip()
        if not normalized or normalized in seen:
            continue
        cleaned.append(normalized)
        seen.add(normalized)
        if len(cleaned) >= limit:
            break
    return cleaned


def _merge_memory_cards(existing_value: Any, payload_value: Any, *, limit: int = 150) -> list[dict]:
    source = payload_value if payload_value is not None else existing_value
    if not isinstance(source, list):
        return []
    cleaned: list[dict] = []
    for raw_item in source:
        if not isinstance(raw_item, dict):
            continue
        structured_notes_raw = raw_item.get("structuredNotes")
        structured_notes: dict[str, Any] = {}
        if isinstance(structured_notes_raw, dict):
            for note_key, note_value in structured_notes_raw.items():
                key = str(note_key or "").strip()
                if not key:
                    continue
                if isinstance(note_value, list):
                    values = _merge_string_list([], note_value, limit=25)
                    if values:
                        structured_notes[key] = values
                    continue
                value = str(note_value or "").strip()
                if value:
                    structured_notes[key] = value
        card = {
            "id": str(raw_item.get("id") or "").strip(),
            "title": str(raw_item.get("title") or "").strip(),
            "category": str(raw_item.get("category") or "").strip(),
            "source": str(raw_item.get("source") or "").strip(),
            "status": str(raw_item.get("status") or "").strip(),
            "rawNote": str(raw_item.get("rawNote") or "").strip(),
            "structuredNotes": structured_notes,
            "cvBulletSuggestion": str(
                raw_item.get("cvBulletSuggestion") or raw_item.get("polishedCvBullet") or ""
            ).strip(),
            "coverLetterAngle": str(raw_item.get("coverLetterAngle") or "").strip(),
            "tags": _merge_string_list([], raw_item.get("tags"), limit=12),
            "missingDetails": _merge_string_list([], raw_item.get("missingDetails"), limit=12),
            "confidenceLabel": str(raw_item.get("confidenceLabel") or "").strip(),
            "useInCv": bool(raw_item.get("useInCv", True)),
            "useInLetter": bool(raw_item.get("useInLetter", False)),
            "createdAt": str(raw_item.get("createdAt") or "").strip(),
            "updatedAt": str(raw_item.get("updatedAt") or "").strip(),
        }
        if not any(
            (
                card["title"],
                card["rawNote"],
                card["cvBulletSuggestion"],
                card["coverLetterAngle"],
            )
        ):
            continue
        cleaned.append(card)
        if len(cleaned) >= limit:
            break
    return cleaned


def _merge_document_metadata(existing_documents: dict, documents_payload: dict) -> dict:
    existing_web_cv_palette = dict(existing_documents.get("web_cv_palette") or {})
    payload_web_cv_palette = dict(documents_payload.get("web_cv_palette") or {})
    default_web_cv_show_photo = existing_documents.get("web_cv_show_photo")
    if default_web_cv_show_photo is None:
        default_web_cv_show_photo = existing_documents.get("include_photo", True)

    raw_web_cv_template = str(
        documents_payload.get("web_cv_template")
        or existing_documents.get("web_cv_template")
        or "plain"
    ).strip()
    cv_template = normalize_cv_template_id(
        documents_payload.get("cv_template") or existing_documents.get("cv_template") or "plain"
    )
    include_photo = bool(documents_payload.get("include_photo", existing_documents.get("include_photo", True)))

    return {
        "generate_docx": bool(documents_payload.get("generate_docx", existing_documents.get("generate_docx", True))),
        "generate_pdf": bool(documents_payload.get("generate_pdf", existing_documents.get("generate_pdf", True))),
        "export_tracker": bool(documents_payload.get("export_tracker", existing_documents.get("export_tracker", True))),
        "export_package": bool(documents_payload.get("export_package", existing_documents.get("export_package", True))),
        "file_naming": str(documents_payload.get("file_naming") or existing_documents.get("file_naming") or "workspace_job_title"),
        "cv_template": cv_template,
        "cv_color_scheme": str(documents_payload.get("cv_color_scheme") or existing_documents.get("cv_color_scheme") or "classic_navy"),
        "cv_font": str(documents_payload.get("cv_font") or existing_documents.get("cv_font") or "Calibri"),
        "include_photo": include_photo,
        "web_cv_template": normalize_cv_template_id(raw_web_cv_template),
        "web_cv_font": str(
            documents_payload.get("web_cv_font")
            or existing_documents.get("web_cv_font")
            or documents_payload.get("cv_font")
            or existing_documents.get("cv_font")
            or "Aptos"
        ),
        "web_cv_show_photo": bool(documents_payload.get("web_cv_show_photo", default_web_cv_show_photo)),
        "web_cv_palette": _merge_web_cv_palette(existing_web_cv_palette, payload_web_cv_palette),
        "master_career_profile_asset_id": str(
            documents_payload.get("master_career_profile_asset_id")
            if "master_career_profile_asset_id" in documents_payload
            else existing_documents.get("master_career_profile_asset_id")
            or ""
        ).strip(),
        "master_career_profile_text": str(
            documents_payload.get("master_career_profile_text")
            if "master_career_profile_text" in documents_payload
            else existing_documents.get("master_career_profile_text")
            or ""
        ).strip(),
        "career_highlights_text": str(
            documents_payload.get("career_highlights_text")
            if "career_highlights_text" in documents_payload
            else existing_documents.get("career_highlights_text")
            or ""
        ).strip(),
        "bullet_bank_text": str(
            documents_payload.get("bullet_bank_text")
            if "bullet_bank_text" in documents_payload
            else existing_documents.get("bullet_bank_text")
            or ""
        ).strip(),
        "professional_hurdles_text": str(
            documents_payload.get("professional_hurdles_text")
            if "professional_hurdles_text" in documents_payload
            else existing_documents.get("professional_hurdles_text")
            or ""
        ).strip(),
        "motivation_letter_notes": str(
            documents_payload.get("motivation_letter_notes")
            if "motivation_letter_notes" in documents_payload
            else existing_documents.get("motivation_letter_notes")
            or ""
        ).strip(),
        "ai_canvas_source_asset_ids": _merge_string_list(
            existing_documents.get("ai_canvas_source_asset_ids"),
            documents_payload.get("ai_canvas_source_asset_ids")
            if "ai_canvas_source_asset_ids" in documents_payload
            else None,
        ),
        "generated_memory_cards": _merge_memory_cards(
            existing_documents.get("generated_memory_cards"),
            documents_payload.get("generated_memory_cards")
            if "generated_memory_cards" in documents_payload
            else None,
        ),
    }


def _build_run_input_overrides(user, payload: dict, *, workspace_settings: dict | None = None) -> dict:
    profile = dict((user.metadata or {}).get("profile") or {})
    documents = dict((user.metadata or {}).get("documents") or {})
    candidate_config = load_job_seeker_config()
    overrides = dict(payload.get("run_input_overrides") or {})
    workspace_settings = dict(workspace_settings or {})
    requested_run_mode = str(payload.get("run_mode") or overrides.get("run_mode") or "normal").strip().lower()
    if requested_run_mode not in {"normal", "test"}:
        raise ValueError("run_mode must be one of: normal, test")
    if requested_run_mode == "test":
        source_ids = {
            str(item or "").strip()
            for item in workspace_settings.get("_source_ids", workspace_settings.get("source_ids", []))
            if str(item or "").strip()
        }
        uses_academic_sources = "academic_career_sites" in source_ids or bool(
            workspace_settings.get("academic_career_sites")
        )
        test_overrides = {
            "run_mode": "test",
            "test_run_job_limit": 1,
            "stage4_max_jobs": 1,
            "stage4_retries": 1,
            "stage4_retry_sleep": 0,
            "stage4_sleep_seconds": 0,
            "stage4_ats_max_attempts": 1,
            "max_jobs_total": 1,
            "linkedin_max_pages": 1,
            "max_enrich_jobs": 1,
            "ai_batch_size": 1,
            "company_site_max_jobs_per_site": 1,
            "academic_site_max_jobs_per_site": 1,
            "company_site_max_job_links_per_site": 1,
            "company_site_runner_credit_budget": 150,
        }
        test_overrides["company_site_max_sites_per_run"] = 10 if uses_academic_sources else 1
        overrides.update(test_overrides)
    else:
        overrides["run_mode"] = "normal"
    personalization_scope = str(
        workspace_settings.get("personalization_scope") or PERSONALIZATION_SCOPE_BASELINE
    ).strip()

    def workspace_has_value(key: str) -> bool:
        value = workspace_settings.get(key)
        return value not in (None, "", [], {})

    if profile.get("name") and not workspace_has_value("candidate_name"):
        overrides.setdefault("candidate_name", str(profile.get("name")))
    if profile.get("email") and not workspace_has_value("candidate_email"):
        overrides.setdefault("candidate_email", str(profile.get("email")))
    if profile.get("languages") and not workspace_has_value("languages"):
        overrides.setdefault("languages", [str(item) for item in profile.get("languages") or [] if str(item).strip()])
    linkedin_url = str(
        profile.get("linkedin_url")
        or cfg_str(candidate_config, ("candidate", "profile_links", "linkedin", "url"), "")
    ).strip()
    github_url = str(
        profile.get("github_url")
        or cfg_str(candidate_config, ("candidate", "profile_links", "github", "url"), "")
    ).strip()
    if linkedin_url and not workspace_has_value("linkedin_url"):
        overrides.setdefault("linkedin_url", linkedin_url)
    if github_url and not workspace_has_value("github_url"):
        overrides.setdefault("github_url", github_url)

    effective_cv_template = normalize_cv_template_id(
        workspace_settings.get("cv_template") or documents.get("cv_template") or "plain"
    )

    if not workspace_has_value("cv_font"):
        overrides.setdefault("cv_font", str(documents.get("cv_font") or "Calibri"))
    if not workspace_has_value("cv_template"):
        overrides.setdefault("cv_template", effective_cv_template)
    if not workspace_has_value("cv_color_scheme"):
        overrides.setdefault("cv_color_scheme", str(documents.get("cv_color_scheme") or "classic_navy"))
    if not workspace_has_value("include_photo"):
        overrides.setdefault("include_photo", bool(documents.get("include_photo", True)))

    include_photo_enabled = workspace_settings.get("include_photo")
    if include_photo_enabled is None:
        include_photo_enabled = bool(documents.get("include_photo", True))
    include_photo_enabled = bool(include_photo_enabled)
    if include_photo_enabled and not workspace_has_value("profile_image"):
        photo_path = str(profile.get("photo_path") or "")
        if photo_path:
            overrides.setdefault("profile_image", photo_path)
    elif not include_photo_enabled and not workspace_has_value("profile_image"):
        overrides["profile_image"] = ""

    if personalization_scope in {PERSONALIZATION_SCOPE_SELECTED, PERSONALIZATION_SCOPE_FULL}:
        selected_asset_ids = _merge_string_list(
            [],
            documents.get("ai_canvas_source_asset_ids"),
            limit=50,
        )
        if selected_asset_ids and not workspace_has_value("ai_canvas_source_asset_ids"):
            overrides.setdefault("ai_canvas_source_asset_ids", selected_asset_ids)

    if personalization_scope == PERSONALIZATION_SCOPE_FULL:
        for field_id in (
            "master_career_profile_text",
            "career_highlights_text",
            "bullet_bank_text",
            "professional_hurdles_text",
            "motivation_letter_notes",
        ):
            field_value = str(documents.get(field_id) or "").strip()
            if field_value and not workspace_has_value(field_id):
                overrides.setdefault(field_id, field_value)
        memory_cards = _merge_memory_cards([], documents.get("generated_memory_cards"), limit=150)
        if memory_cards and not workspace_has_value("generated_memory_cards"):
            overrides.setdefault("generated_memory_cards", memory_cards)

    return overrides


def _build_quick_apply_run_input_overrides(application, user, workspace, payload: dict) -> dict:
    requested_settings = dict(payload.get("settings") or {})
    requested_overrides = {
        **requested_settings,
        **dict(payload.get("run_input_overrides") or {}),
    }
    workspace_settings = {
        **dict(getattr(workspace, "settings", {}) or {}),
        **requested_overrides,
    }
    overrides = _build_run_input_overrides(
        user,
        {
            "run_mode": payload.get("run_mode"),
            "run_input_overrides": requested_overrides,
        },
        workspace_settings=workspace_settings,
    )
    overrides.setdefault("stage4_retries", 1)
    overrides.setdefault("stage4_retry_sleep", 0)
    overrides.setdefault("stage4_sleep_seconds", 0)
    overrides.setdefault("stage4_ats_max_attempts", 1)

    asset_id = str(overrides.get("workspace_cv_asset_id") or "").strip()
    if asset_id:
        runtime_settings, _workspace_cv_asset = _resolve_workspace_cv_binding(application, user, asset_id)
        overrides.update(runtime_settings)
    return overrides


def _quick_apply_workspace_id(user) -> str:
    user_id = _slugify(str(getattr(user, "user_id", "") or "user")) or "user"
    return f"quick_apply_{user_id}"


def _ensure_quick_apply_workspace(application, user):
    workspace_id = _quick_apply_workspace_id(user)
    try:
        return application.get_workspace(workspace_id)
    except KeyError:
        pass

    workflow = build_quick_apply_workflow_template()
    application.upsert_workflow_template(workflow)
    return application.upsert_workspace(
        WorkspaceDefinition(
            id=workspace_id,
            name="Quick Apply Workspace",
            workflow_template_id=workflow.id,
            owner_user_id=user.user_id,
            description="Internal workspace used for quick applications.",
            workspace_type="internal",
            settings={
                "automation_flow": "tailored_documents",
                "config_loader": "tailored_documents",
                "manual_sources_are_preapproved": True,
            },
            feature_flags={"enable_manual_urls": True, "tailored_document_generation": True},
            profiles=[
                ProfileRef(
                    id=f"{workspace_id}_profile",
                    label="Primary Job Seeker Profile",
                    settings={"automation_flow": "tailored_documents"},
                )
            ],
            sources=[JobSource(id="source_exact_job_links", connector_id="curated_job_urls")],
            metadata={
                "automation_flow": "tailored_documents",
                "builder_mode": "quick_apply",
                "internal": True,
                "created_by": "system",
            },
        )
    )


def _referral_contacts_from_user(user) -> list[ReferralContactRecord]:
    return [
        ReferralContactRecord.from_dict(item)
        for item in (user.metadata or {}).get("referrals") or []
        if isinstance(item, dict)
    ]


def _build_settings_payload(application, user) -> dict:
    workspaces = [workspace for workspace in application.list_workspaces() if application.user_can_access_workspace(user, workspace.id)]
    profile_options: dict[str, dict] = {}
    prompt_set_options: dict[str, dict] = {}
    for workspace in workspaces:
        for profile in workspace.profiles:
            profile_options.setdefault(profile.id, {"id": profile.id, "label": profile.label, "settings": dict(profile.settings)})
        for prompt_set in workspace.prompt_sets:
            prompt_set_options.setdefault(
                prompt_set.id,
                {"id": prompt_set.id, "family": prompt_set.family, "settings": dict(prompt_set.settings)},
            )

    metadata = dict(user.metadata or {})
    profile = dict(metadata.get("profile") or {})
    defaults = dict(metadata.get("defaults") or {})
    documents = _merge_document_metadata(dict(metadata.get("documents") or {}), {})
    review_preferences = dict(metadata.get("review_preferences") or {})
    referrals = [contact.to_dict() for contact in _referral_contacts_from_user(user)]

    if not defaults.get("default_workspace_id") and workspaces:
        defaults["default_workspace_id"] = workspaces[0].id
    if not defaults.get("default_execution_mode"):
        defaults["default_execution_mode"] = "queued"
    if not defaults.get("default_profile_id") and profile_options:
        defaults["default_profile_id"] = next(iter(profile_options.keys()))
    if not defaults.get("default_prompt_set_id") and prompt_set_options:
        defaults["default_prompt_set_id"] = next(iter(prompt_set_options.keys()))
    if "max_jobs_per_run" not in defaults:
        defaults["max_jobs_per_run"] = 25

    if "require_review_before_use" not in review_preferences:
        review_preferences["require_review_before_use"] = True
    if not review_preferences.get("default_decision_state"):
        review_preferences["default_decision_state"] = "waiting_review"
    if "rejection_note_required" not in review_preferences:
        review_preferences["rejection_note_required"] = True
    if "auto_open_next_item" not in review_preferences:
        review_preferences["auto_open_next_item"] = True

    profile_section = _merge_profile_metadata(profile, {}, user)
    candidate_config = load_job_seeker_config()
    profile_section["linkedin_url"] = str(
        profile_section.get("linkedin_url")
        or cfg_str(candidate_config, ("candidate", "profile_links", "linkedin", "url"), "")
    )
    profile_section["github_url"] = str(
        profile_section.get("github_url")
        or cfg_str(candidate_config, ("candidate", "profile_links", "github", "url"), "")
    )
    document_design_options = get_document_design_options()

    return {
        "profile": profile_section,
        "candidate_assets": _load_candidate_assets(user),
        "defaults": defaults,
        "documents": documents,
        "review_preferences": review_preferences,
        "referrals": referrals,
        "account": {
            "display_name": _public_user_display_name(user),
            "email": _public_user_email(user),
            "role": user.role,
            "allowed_workspace_ids": list(user.allowed_workspace_ids),
            "is_active": user.is_active,
        },
        "options": {
            "workspaces": [_workspace_option(workspace) for workspace in workspaces],
            "profiles": list(profile_options.values()),
            "prompt_sets": list(prompt_set_options.values()),
            "execution_modes": [
                {"id": "queued", "label": "Queued"},
                {"id": "planned", "label": "Planned"},
                {"id": "sync", "label": "Run Immediately"},
            ],
            "review_default_states": [
                {"id": "waiting_review", "label": "Waiting Review"},
                {"id": "approved", "label": "Approved"},
                {"id": "rejected", "label": "Rejected"},
            ],
            "document_naming_modes": [
                {"id": "workspace_job_title", "label": "Workspace + Job Title"},
                {"id": "company_job_title", "label": "Company + Job Title"},
                {"id": "run_artifact_id", "label": "Run + Artifact ID"},
            ],
            "cv_templates": document_design_options["templates"],
            "cv_color_schemes": document_design_options["color_schemes"],
            "cv_fonts": document_design_options["fonts"],
        },
    }


def _user_can_access_workspace_record(user, workspace) -> bool:
    if user.role == ROLE_ADMIN:
        return True
    normalized_workspace_id = str(getattr(workspace, "id", "") or "").strip()
    if not normalized_workspace_id:
        return False
    if str(getattr(workspace, "owner_user_id", "") or "").strip() == str(user.user_id or "").strip():
        return True
    allowed = {str(item).strip() for item in user.allowed_workspace_ids if str(item).strip()}
    return normalized_workspace_id in allowed


def _user_can_access_run_from_workspace_map(user, run, workspaces: Mapping[str, object]) -> bool:
    if user.role == ROLE_ADMIN:
        return True
    if str(getattr(run, "normalized_user_id", "") or "").strip() != str(user.user_id or "").strip():
        return False
    return str(getattr(run, "workspace_id", "") or "").strip() in workspaces


def _collect_authorized_runs(application, user, *, workspace_id: str = "") -> tuple[dict[str, object], list[object]]:
    workspaces = {
        workspace.id: workspace
        for workspace in application.list_workspaces()
        if _user_can_access_workspace_record(user, workspace)
    }
    runs = [
        run
        for run in application.list_runs(limit=1000, offset=0, status="", workspace_id=workspace_id)
        if _user_can_access_run_from_workspace_map(user, run, workspaces)
    ]
    return workspaces, runs


def _load_job_sets_by_run(application, runs: list[object]) -> dict[str, dict[str, list[object]]]:
    run_ids = [str(run.id) for run in runs]
    loader = getattr(application.repositories.job_store, "load_job_sets_for_runs", None)
    if callable(loader):
        return loader(run_ids)
    return {
        run_id: application.repositories.job_store.load_all_job_sets(run_id)
        for run_id in run_ids
    }


def _load_reviews_by_run(application, runs: list[object]) -> dict[str, list[object]]:
    run_ids = [str(run.id) for run in runs]
    loader = getattr(application.repositories.review_store, "list_reviews_for_runs", None)
    if callable(loader):
        return loader(run_ids)
    return {
        run_id: application.repositories.review_store.list_reviews(
            run_id=run_id,
            limit=1000,
            offset=0,
        )
        for run_id in run_ids
    }


def _load_artifacts_by_run(application, runs: list[object]) -> dict[str, list[object]]:
    run_ids = [str(run.id) for run in runs]
    loader = getattr(application.repositories.artifact_store, "load_artifacts_for_runs", None)
    if callable(loader):
        return loader(run_ids)
    return {
        run_id: application.repositories.artifact_store.load_artifacts(run_id)
        for run_id in run_ids
    }


def _load_run_read_snapshot(
    application,
    runs: list[object],
    *,
    include_artifacts: bool = False,
    include_reviews: bool = False,
    include_blobs: bool = False,
    preserve_job_sets: bool = True,
    review_jobs_only: bool = False,
) -> dict[str, dict]:
    loader = getattr(application.repositories.job_store, "load_run_read_snapshot", None)
    if callable(loader):
        return loader(
            [str(run.id) for run in runs],
            include_artifacts=include_artifacts,
            include_reviews=include_reviews,
            include_blobs=include_blobs,
            preserve_job_sets=preserve_job_sets,
            review_jobs_only=review_jobs_only,
        )
    return {
        "job_sets": _load_job_sets_by_run(application, runs),
        "artifacts": _load_artifacts_by_run(application, runs) if include_artifacts else {},
        "reviews": _load_reviews_by_run(application, runs) if include_reviews else {},
        "blobs": (
            {
                str(run.id): application.repositories.job_store.load_all_blobs(str(run.id))
                for run in runs
            }
            if include_blobs
            else {}
        ),
    }


def _collect_review_queue_entries(application, user, *, workspace_id: str = "", run_id: str = "") -> list[dict]:
    workspaces, runs = _collect_authorized_runs(application, user, workspace_id=workspace_id)
    referral_contacts = _referral_contacts_from_user(user)
    snapshot = _load_run_read_snapshot(
        application,
        runs,
        include_artifacts=True,
        include_reviews=True,
    )
    job_sets_by_run = snapshot["job_sets"]
    reviews_by_run = snapshot["reviews"]
    artifacts_by_run = snapshot["artifacts"]
    entries: list[dict] = []
    for run in runs:
        if run_id and run.id != run_id:
            continue
        job_sets = job_sets_by_run.get(run.id, {})
        review_records = reviews_by_run.get(run.id, [])
        reviews_by_job: dict[str, object] = {}
        for review in review_records:
            reviews_by_job.setdefault(review.job_id, review)
        artifact_count = len(artifacts_by_run.get(run.id, []))
        workspace = workspaces.get(run.workspace_id)
        preferred_keys = run.final_job_set_keys or list(job_sets.keys())
        for set_key in preferred_keys:
            for job in job_sets.get(set_key, []):
                review = reviews_by_job.get(job.job_id)
                status = str((review.status if review else "") or "waiting_review")
                review_meta = dict(review.metadata or {}) if review else {}
                matched_contacts = find_referral_contacts_for_company(referral_contacts, job.company)
                tracker_status = str(review_meta.get("tracker_status") or "")
                application_status = normalize_application_status(
                    review_meta.get("application_status") or tracker_status,
                    default="" if not tracker_status else "Unknown",
                )
                matched_contact_payloads = []
                for contact in matched_contacts:
                    contact_payload = contact.to_dict()
                    contact_payload["outreach_status"] = _get_referral_outreach_status(
                        user,
                        run_id=run.id,
                        job_id=job.job_id,
                        contact_id=contact.contact_id,
                    )
                    matched_contact_payloads.append(contact_payload)
                entries.append(
                    {
                        "review_id": review.review_id if review else "",
                        "run_id": run.id,
                        "workspace_id": run.workspace_id,
                        "workspace_name": workspace.name if workspace else run.workspace_id,
                        "job_set_key": set_key,
                        "job_id": job.job_id,
                        "title": job.title,
                        "company": job.company,
                        "source_label": job.portal or job.source_type or "unknown",
                        "source_type": job.source_type,
                        "status": status,
                        "decision": review.decision if review else "",
                        "reviewer": review.reviewer if review else "",
                        "notes": review.notes if review else "",
                        "artifact_status": "artifact_ready" if artifact_count else "no_artifact",
                        "artifact_count": artifact_count,
                        "apply_link": job.apply_link or job.link or job.source_url,
                        "location": job.location_raw,
                        "filter_status": job.filter_status,
                        "manual_approved": bool(job.manual_approved),
                        "updated_at": review.updated_at if review else run.updated_at,
                        "job_workspace_url": _job_workspace_url(run.id, job.job_id),
                        # Tracker fields (REQ-09 / REQ-10)
                        "tracker_status": tracker_status,
                        "application_status": application_status,
                        "email_confirmed": bool(review_meta.get("email_confirmed") or False),
                        "referral_contacts": matched_contact_payloads,
                        "has_referral_contact": bool(matched_contacts),
                        "referable_contact_count": sum(1 for contact in matched_contacts if contact.can_refer),
                    }
                )
    entries.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return entries


TRACKER_EXCEL_BASELINE_COLUMNS = [
    "run_date",
    "run_timestamp",
    "job_id",
    "title",
    "company",
    "location_raw",
    "keyword",
    "posted_time_text",
    "posted_age_hours",
    "applicant_count",
    "priority_rank",
    "priority_rule",
    "easy_apply_status",
    "apply_link",
    "apply_link_source",
    "linkedin_link",
    "link",
    "enrich_status_code",
    "enrich_error",
    "full_description",
    "cv_professional_summary",
    "cv_professional_experience",
    "cv_strategic_initiatives",
    "cv_skills",
    "cv_education",
    "applied_cv",
    "tailored_cv",
    "cv_docx",
    "cv_pdf",
    "tailored_cv_docx",
    "pdf_generation_error",
    "doc_generation_error",
    "posted_datetime_estimated_utc",
    "priority_bucket",
    "priority_tier",
    "Status",
    "applied?",
    "notes",
]

TRACKER_TABLE_COLUMNS = [
    {"key": "Status", "label": "Status"},
    {"key": "company", "label": "Company"},
    {"key": "title", "label": "Role"},
    {"key": "location_raw", "label": "Location"},
    {"key": "application_date", "label": "Application date"},
    {"key": "apply_link", "label": "Resource"},
    {"key": "priority_rank", "label": "Priority"},
    {"key": "notes", "label": "Notes"},
]


def _run_date(value: str) -> str:
    text = str(value or "").strip()
    return text[:10] if text else ""


def _tracker_baseline_row(
    *,
    job,
    run,
    review=None,
    application_status: str,
    documents: list[dict] | None = None,
    external: dict | None = None,
) -> dict:
    external = dict(external or {})
    review_meta = dict(getattr(review, "metadata", None) or {})
    job_payload = job.to_dict() if job else {}
    row = {column: job_payload.get(column, "") for column in TRACKER_EXCEL_BASELINE_COLUMNS}
    run_timestamp = str(
        row.get("run_timestamp")
        or getattr(run, "finished_at", "")
        or getattr(run, "updated_at", "")
        or getattr(run, "created_at", "")
        or external.get("updated_at")
        or external.get("created_at")
        or ""
    )
    row.update(
        {
            "run_date": row.get("run_date") or _run_date(run_timestamp),
            "run_timestamp": run_timestamp,
            "job_id": row.get("job_id") or (job.job_id if job else external.get("application_id", "")),
            "title": row.get("title") or (job.title if job else external.get("title", "")),
            "company": row.get("company") or (job.company if job else external.get("company", "")),
            "location_raw": row.get("location_raw") or (job.location_raw if job else external.get("location", "")),
            "apply_link": row.get("apply_link") or (job.apply_link or job.link or job.source_url if job else external.get("apply_link", "")),
            "linkedin_link": row.get("linkedin_link") or (job_payload.get("linkedin_link") or (job.link if job else "")),
            "link": row.get("link") or (job.link if job else external.get("apply_link", "")),
            "full_description": row.get("full_description") or (job.description_text if job else external.get("full_description", "")),
            "priority_rank": row.get("priority_rank") or (job.priority_rank if job else external.get("priority_rank", "")),
            "Status": application_status,
            "applied?": application_status,
            "notes": (
                str(getattr(review, "notes", "") or review_meta.get("notes") or "")
                if review
                else str(external.get("notes") or "")
            ),
        }
    )
    row["application_date"] = str(
        review_meta.get("application_date")
        or review_meta.get("applied_at")
        or external.get("application_date")
        or ""
    )
    row["documents"] = documents or []
    return row


def _tracker_document_summary(document: dict, *, source_scope: str = "") -> dict:
    metadata = dict(document.get("metadata") or {})
    label = str(document.get("display_name") or document.get("document_name") or document.get("relative_path") or "").strip()
    document_type = str(document.get("document_type") or _document_type_for_asset_kind(str(document.get("asset_kind") or ""))).strip()
    suffix = Path(
        str(
            document.get("relative_path")
            or document.get("path")
            or document.get("file_name")
            or document.get("display_name")
            or ""
        )
    ).suffix.lower()
    if not label:
        label = document_type or "Document"
    if label and document_type and label.casefold() == document_type.casefold() and suffix:
        label = f"{document_type} {suffix.lstrip('.').upper()}".strip()
    ats_export_gate = document.get("ats_export_gate") if isinstance(document.get("ats_export_gate"), dict) else {}
    return {
        "document_id": str(document.get("document_id") or ""),
        "field": str(document.get("asset_kind") or ""),
        "label": label,
        "document_type": document_type,
        "asset_kind": str(document.get("asset_kind") or ""),
        "download_url": str(document.get("download_url") or ""),
        "path": str(document.get("relative_path") or document.get("path") or ""),
        "file_name": str(document.get("file_name") or ""),
        "file_extension": suffix.lstrip("."),
        "content_type": str(document.get("content_type") or ""),
        "workspace_id": str(document.get("workspace_id") or ""),
        "run_id": str(document.get("run_id") or ""),
        "job_id": str(metadata.get("job_id") or document.get("job_id") or ""),
        "source_origin": str(document.get("source_origin") or ""),
        "source_scope": source_scope,
        "final_export_blocked": bool(document.get("final_export_blocked") or False),
        "ats_export_gate": dict(ats_export_gate),
    }


def _dedupe_tracker_documents(documents: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    seen_index: dict[str, int] = {}
    for document in documents:
        key = (
            str(document.get("path") or "")
            or str(document.get("document_id") or "")
            or str(document.get("download_url") or "")
            or f"{document.get('field')}::{document.get('label')}"
        )
        if key in seen_index:
            existing = deduped[seen_index[key]]
            for field_name in (
                "document_id",
                "download_url",
                "asset_kind",
                "document_type",
                "run_id",
                "workspace_id",
                "source_origin",
            ):
                if not existing.get(field_name) and document.get(field_name):
                    existing[field_name] = document[field_name]
            continue
        seen_index[key] = len(deduped)
        deduped.append(document)
    return deduped


def _index_tracker_documents(document_entries: list[dict]) -> tuple[dict[tuple[str, str], list[dict]], list[dict]]:
    by_run_and_job: dict[tuple[str, str], list[dict]] = {}
    standard_documents: list[dict] = []
    standard_asset_kinds = {
        "workspace_cv",
        "certification",
        "recommendation_letter",
        "uploaded_document",
        "motivation_letter",
        "cover_letter",
    }
    for document in document_entries:
        metadata = dict(document.get("metadata") or {})
        run_id = str(document.get("run_id") or "")
        job_id = str(metadata.get("job_id") or document.get("job_id") or "")
        if run_id and job_id:
            by_run_and_job.setdefault((run_id, job_id), []).append(
                _tracker_document_summary(document, source_scope="application")
            )
            continue
        asset_kind = str(document.get("asset_kind") or "").lower()
        if asset_kind in standard_asset_kinds or str(document.get("source_origin") or "") == "upload":
            standard_documents.append(_tracker_document_summary(document, source_scope="standard"))
    return by_run_and_job, standard_documents


def _standard_documents_for_workspace(documents: list[dict], workspace_id: str) -> list[dict]:
    workspace_id = str(workspace_id or "")
    return [
        document
        for document in documents
        if not str(document.get("workspace_id") or "") or str(document.get("workspace_id") or "") == workspace_id
    ]


_APPLICATION_DOCUMENT_ALIASES: dict[str, tuple[str, ...]] = {
    "motivation_letter": ("motivation_letter", "cover_letter"),
    "recommendation_letter": ("recommendation_letter",),
    "transcript": ("transcript", "transcript_of_records", "uploaded_document"),
    "grades": ("grades", "grade_report", "uploaded_document"),
    "degree_certificate": ("degree_certificate", "university_certificate", "certificate", "certification", "uploaded_document"),
}
_APPLICATION_DOCUMENT_TEXT_ALIASES: dict[str, tuple[str, ...]] = {
    "motivation_letter": ("motivation", "cover letter", "anschreiben"),
    "recommendation_letter": ("recommendation", "reference letter", "referenz"),
    "transcript": ("transcript", "notenspiegel", "records"),
    "grades": ("grade", "grades", "noten"),
    "degree_certificate": ("degree", "certificate", "diploma", "abschluss"),
}


def _application_requirements_from_job_payload(job_payload: Mapping[str, Any]) -> dict[str, Any]:
    existing = job_payload.get("application_requirements")
    if isinstance(existing, Mapping):
        return deepcopy(dict(existing))
    return detect_application_requirements(
        job_payload,
        cv_includes_photo=bool(job_payload.get("cv_include_photo") or False),
    )


def _document_satisfies_requirement(document: Mapping[str, Any], document_type: str) -> bool:
    normalized_type = str(document_type or "").strip().lower()
    aliases = _APPLICATION_DOCUMENT_ALIASES.get(normalized_type, (normalized_type,))
    asset_kind = str(document.get("asset_kind") or document.get("field") or "").strip().lower()
    document_label = " ".join(
        str(document.get(key) or "")
        for key in ("label", "document_type", "file_name", "path", "download_url")
    ).casefold()
    if asset_kind in aliases and asset_kind != "uploaded_document":
        return True
    return any(alias.casefold() in document_label for alias in _APPLICATION_DOCUMENT_TEXT_ALIASES.get(normalized_type, (normalized_type,)))


def _application_requirement_status(requirements: Mapping[str, Any] | None, documents: list[dict] | None = None) -> dict[str, Any]:
    raw_requirements = deepcopy(dict(requirements or {}))
    available_documents = [dict(item or {}) for item in documents or [] if isinstance(item, Mapping)]
    required_documents: list[dict[str, Any]] = []
    missing_documents: list[dict[str, Any]] = []

    for document in raw_requirements.get("required_documents") or []:
        if not isinstance(document, Mapping):
            continue
        item = dict(document)
        document_type = str(item.get("document_type") or "").strip().lower()
        has_document = any(_document_satisfies_requirement(candidate, document_type) for candidate in available_documents)
        item["available"] = bool(has_document)
        item["missing"] = not has_document
        required_documents.append(item)
        if not has_document:
            missing_documents.append(item)

    warnings = [dict(item) for item in raw_requirements.get("warnings") or [] if isinstance(item, Mapping)]
    for document in missing_documents:
        warnings.append(
            {
                "code": "required_document_missing",
                "severity": "blocking",
                "title": f"{document.get('label') or 'Required document'} missing",
                "message": f"Upload or attach the requested {str(document.get('label') or 'document').lower()} before applying.",
                "document_type": str(document.get("document_type") or ""),
                "evidence": str(document.get("evidence") or ""),
            }
        )

    return {
        **raw_requirements,
        "required_documents": required_documents,
        "missing_documents": missing_documents,
        "warnings": warnings,
        "blocking_count": sum(1 for item in warnings if str(item.get("severity") or "") == "blocking"),
        "review_count": len(warnings),
    }


def _cv_studio_seed_from_job_extra(job_extra: Mapping[str, Any], *, user, job=None) -> dict[str, Any]:
    has_generated_profile = any(
        job_extra.get(field_name)
        for field_name in (
            "cv_professional_summary",
            "cv_professional_experience",
            "cv_skills",
            "cv_education",
            "cv_strategic_initiatives",
        )
    )
    if not has_generated_profile:
        return {}
    profile = dict((user.metadata or {}).get("profile") or {})
    experiences = []
    for item in job_extra.get("cv_professional_experience") or []:
        if not isinstance(item, Mapping):
            continue
        experiences.append(
            {
                "id": str(item.get("id") or item.get("experience_id") or ""),
                "title": str(item.get("role_title") or item.get("title") or ""),
                "company": str(item.get("company") or item.get("employer") or ""),
                "location": str(item.get("location") or item.get("city") or ""),
                "start_date": str(item.get("start_date") or item.get("start") or ""),
                "end_date": str(item.get("end_date") or item.get("end") or ""),
                "period": str(item.get("period") or item.get("date_range") or ""),
                "bullets": [
                    dict(value) if isinstance(value, Mapping) else str(value).strip()
                    for value in item.get("bullets") or []
                    if (isinstance(value, Mapping) and str(value.get("text") or "").strip())
                    or (not isinstance(value, Mapping) and str(value).strip())
                ],
            }
        )
    education = [dict(item) for item in job_extra.get("cv_education") or [] if isinstance(item, Mapping)]
    projects = []
    for item in job_extra.get("cv_strategic_initiatives") or []:
        if isinstance(item, Mapping):
            projects.append(
                {
                    "id": str(item.get("id") or item.get("project_id") or ""),
                    "title": str(item.get("title") or ""),
                    "period": str(item.get("period") or item.get("date") or item.get("year") or ""),
                    "bullets": [
                        dict(value) if isinstance(value, Mapping) else str(value).strip()
                        for value in item.get("bullets") or []
                        if (isinstance(value, Mapping) and str(value.get("text") or "").strip())
                        or (not isinstance(value, Mapping) and str(value).strip())
                    ],
                }
            )
    return {
        "profile": {
            **profile,
            "summary": str(job_extra.get("cv_professional_summary") or profile.get("summary") or ""),
            "competencies": [str(value).strip() for value in job_extra.get("cv_skills") or [] if str(value).strip()],
            "recent_experience": experiences,
            "education": education or list(profile.get("education") or []),
            "projects": projects,
            "target_role": str(getattr(job, "title", "") or job_extra.get("title") or ""),
            "target_company": str(getattr(job, "company", "") or job_extra.get("company") or ""),
            "cv_output_language": str(job_extra.get("cv_output_language") or ""),
        },
        "documents": {
            "cv_template": str(job_extra.get("cv_template") or ""),
            "cv_color_scheme": str(job_extra.get("cv_color_scheme") or ""),
            "cv_font": str(job_extra.get("cv_font") or ""),
            "include_photo": bool(job_extra.get("cv_include_photo") or False),
            "cv_output_language": str(job_extra.get("cv_output_language") or ""),
        },
        "source": "generated_cv",
    }


def _tracker_manual_documents_for_job_extra(job_extra: dict[str, object]) -> tuple[dict[str, str], list[dict[str, str]]]:
    cv_generation_mode = normalize_cv_generation_mode(job_extra.get("cv_generation_mode"))
    document_fields = {
        "applied_cv": str(job_extra.get("applied_cv") or ""),
        "cv_docx": str(job_extra.get("cv_docx") or job_extra.get("original_cv_docx") or ""),
        "cv_pdf": str(job_extra.get("cv_pdf") or job_extra.get("original_cv_pdf") or ""),
        "tailored_cv_docx": str(job_extra.get("tailored_cv_docx") or ""),
        "tailored_cv": str(job_extra.get("tailored_cv") or job_extra.get("tailored_cv_pdf") or ""),
    }
    if cv_generation_mode == CV_GENERATION_MODE_STANDARD and document_fields["applied_cv"]:
        return document_fields, [
            {
                "field": "applied_cv",
                "label": "Applied Workspace CV",
                "document_type": APPLIED_CV_DOCUMENT_TYPE,
                "path": document_fields["applied_cv"],
            }
        ]
    return document_fields, [
        {"field": key, "label": label, "path": value, "document_type": document_type}
        for key, label, value, document_type in [
            ("cv_docx", "Original CV DOCX", document_fields["cv_docx"], "Original CV"),
            ("cv_pdf", "Original CV PDF", document_fields["cv_pdf"], "Original CV"),
            ("tailored_cv_docx", "Tailored CV DOCX", document_fields["tailored_cv_docx"], "Tailored CV"),
            ("tailored_cv", "Tailored CV", document_fields["tailored_cv"], "Tailored CV"),
        ]
        if value
    ]


def _is_explicit_tracker_application(*, tracker_status: object = "", email_confirmed: object = False) -> bool:
    return bool(str(tracker_status or "").strip()) or bool(email_confirmed)


def _collect_tracker_entries(application, user) -> list[dict]:
    """Return all reviews that have been approved or have a tracker_status set."""
    workspaces, runs = _collect_authorized_runs(application, user)
    snapshot = _load_run_read_snapshot(
        application,
        runs,
        include_reviews=True,
        preserve_job_sets=False,
        review_jobs_only=True,
    )
    job_sets_by_run = snapshot["job_sets"]
    reviews_by_run = snapshot["reviews"]
    tracker_run_ids = {
        str(run.id)
        for run in runs
        for review in reviews_by_run.get(run.id, [])
        if review.decision == "approved" or str((review.metadata or {}).get("tracker_status") or "")
    }
    tracker_runs = [run for run in runs if str(run.id) in tracker_run_ids]
    artifacts_by_run = _load_artifacts_by_run(application, tracker_runs)
    application_documents, standard_documents = _index_tracker_documents(
        _collect_document_entries(
            application,
            user,
            run_records=tracker_runs,
            workspace_records=workspaces,
            job_sets_by_run=job_sets_by_run,
            artifacts_by_run=artifacts_by_run,
        )
    )
    entries: list[dict] = []
    entries_by_posting_url: dict[str, int] = {}
    for run in runs:
        job_sets = job_sets_by_run.get(run.id, {})
        review_records = reviews_by_run.get(run.id, [])
        # build a fast job lookup
        jobs_by_id: dict[str, object] = {}
        for jobs in job_sets.values():
            for job in jobs:
                jobs_by_id[job.job_id] = job
        workspace = workspaces.get(run.workspace_id)
        for review in review_records:
            review_meta = dict(review.metadata or {})
            raw_tracker_status = str(review_meta.get("tracker_status") or "")
            email_confirmed = bool(review_meta.get("email_confirmed") or False)
            # Include if approved decision OR has any tracker status already set.
            if review.decision != "approved" and not raw_tracker_status:
                continue
            tracker_status = raw_tracker_status
            if not tracker_status:
                tracker_status = "not_applied"
            application_status = normalize_application_status(
                review_meta.get("application_status") or tracker_status,
                default="Not applied",
            )
            job = jobs_by_id.get(review.job_id)
            job_extra = dict(job.extra_fields or {}) if job else {}
            posting_url = canonical_posting_url(job.to_dict() if job else {})
            if posting_url and posting_url in entries_by_posting_url:
                existing_index = entries_by_posting_url[posting_url]
                existing_entry = entries[existing_index]
                existing_entry["duplicate_sighting_count"] = int(existing_entry.get("duplicate_sighting_count") or 0) + 1
                continue
            description_text = str(
                (job.description_text if job else "")
                or job_extra.get("full_description")
                or job_extra.get("description")
                or ""
            )
            document_fields, documents = _tracker_manual_documents_for_job_extra(job_extra)
            documents = _dedupe_tracker_documents(
                [
                    *documents,
                    *_standard_documents_for_workspace(standard_documents, run.workspace_id),
                    *application_documents.get((run.id, review.job_id), []),
                ]
            )
            application_requirements = _application_requirement_status(
                _application_requirements_from_job_payload({**job_extra, **(job.to_dict() if job else {})}),
                documents=documents,
            )
            entry = {
                "review_id": review.review_id,
                "run_id": review.run_id,
                "workspace_id": run.workspace_id,
                "workspace_name": workspace.name if workspace else run.workspace_id,
                "is_test_run": bool(run.is_test_run),
                "run_mode": "test" if run.is_test_run else "normal",
                "tracker_source_type": "test_run" if run.is_test_run else "standard_run",
                "job_id": review.job_id,
                "title": job.title if job else "",
                "company": job.company if job else "",
                "apply_link": (job.apply_link or job.link or job.source_url) if job else "",
                "canonical_posting_url": posting_url,
                "linkedin_link": str(job_extra.get("linkedin_link") or (job.link if job else "") or ""),
                "location": job.location_raw if job else "",
                "full_description": description_text,
                "tracker_status": tracker_status,
                "application_status": application_status,
                "email_confirmed": email_confirmed,
                "is_explicit_application": _is_explicit_tracker_application(
                    tracker_status=raw_tracker_status,
                    email_confirmed=email_confirmed,
                ),
                "rejection_note": str(review_meta.get("rejection_note") or ""),
                "rejected_at": str(review_meta.get("rejected_at") or ""),
                "application_date": str(review_meta.get("application_date") or review_meta.get("applied_at") or ""),
                "notes": str(review.notes or review_meta.get("notes") or ""),
                "applicant_count": job_extra.get("applicant_count") or job_extra.get("num_applicants") or "",
                "posted_time_text": str(job_extra.get("posted_time_text") or job_extra.get("listed_at_text") or ""),
                "priority_rank": job.priority_rank if job else job_extra.get("priority_rank"),
                "priority_bucket": str(job_extra.get("priority_bucket") or job_extra.get("priority_tier") or ""),
                "job_workspace_url": _job_workspace_url(run.id, review.job_id),
                **document_fields,
                "documents": documents,
                "application_requirements": application_requirements,
                "application_warnings": list(application_requirements.get("warnings") or []),
                "cv_studio_seed": _cv_studio_seed_from_job_extra(job_extra, user=user, job=job),
                "duplicate_sighting_count": 0,
                "placed_in_tracker_at": review_placed_in_tracker_at(review),
                "updated_at": review.updated_at,
                "run_finished_at": run.finished_at or run.updated_at,
            }
            entry["tracker_table_row"] = _tracker_baseline_row(
                job=job,
                run=run,
                review=review,
                application_status=application_status,
                documents=documents,
            )
            entry["tracker_application"] = normalize_tracker_application({**entry, "metadata": review_meta})
            if posting_url:
                entries_by_posting_url[posting_url] = len(entries)
            entries.append(entry)
    for external in _load_external_tracker_applications(user):
        raw_tracker_status = str(external.get("tracker_status") or "")
        email_confirmed = bool(external.get("email_confirmed") or False)
        application_status = normalize_application_status(
            external.get("application_status") or raw_tracker_status,
            default="Unknown",
        )
        tracker_status = str(
            raw_tracker_status
            or legacy_tracker_status_for_application_status(application_status)
        )
        entry = {
            "review_id": str(external.get("review_id") or external.get("application_id") or ""),
            "application_id": str(external.get("application_id") or ""),
            "run_id": "",
            "workspace_id": "",
            "workspace_name": "External applications",
            "is_test_run": False,
            "run_mode": "external",
            "tracker_source_type": "external",
            "job_id": str(external.get("application_id") or ""),
            "title": str(external.get("title") or ""),
            "company": str(external.get("company") or ""),
            "apply_link": str(external.get("apply_link") or ""),
            "linkedin_link": "",
            "location": str(external.get("location") or ""),
            "full_description": str(external.get("full_description") or ""),
            "tracker_status": tracker_status,
            "application_status": application_status,
            "email_confirmed": email_confirmed,
            "is_explicit_application": _is_explicit_tracker_application(
                tracker_status=raw_tracker_status,
                email_confirmed=email_confirmed,
            ),
            "rejection_note": str(external.get("rejection_note") or ""),
            "rejected_at": str(external.get("rejected_at") or ""),
            "application_date": str(external.get("application_date") or ""),
            "notes": str(external.get("notes") or ""),
            "applicant_count": "",
            "posted_time_text": "",
            "priority_rank": external.get("priority_rank"),
            "priority_bucket": "external",
            "cv_docx": "",
            "cv_pdf": "",
            "tailored_cv_docx": "",
            "tailored_cv": "",
            "documents": list(standard_documents),
            "updated_at": str(external.get("updated_at") or external.get("created_at") or ""),
            "run_finished_at": "",
            "source_label": (
                "Assisted Apply" if str(external.get("source") or "") == "assisted_apply" else "Gmail"
            ),
            "external_application": True,
            "gmail_detection": dict(external.get("gmail_detection") or {}),
            "application_requirements": _application_requirement_status({}, documents=list(standard_documents)),
            "application_warnings": [],
            "cv_studio_seed": {},
            "placed_in_tracker_at": str(
                external.get("placed_in_tracker_at")
                or external.get("created_at")
                or ""
            ),
        }
        entry["tracker_table_row"] = _tracker_baseline_row(
            job=None,
            run=None,
            review=None,
            application_status=application_status,
            documents=list(standard_documents),
            external=external,
        )
        entry["tracker_application"] = normalize_tracker_application({**entry, "metadata": dict(external)})
        entries.append(entry)
    entries.sort(
        key=lambda item: (
            str(item.get("placed_in_tracker_at") or ""),
            str(item.get("review_id") or ""),
        ),
        reverse=True,
    )
    return entries


def _tracker_ats_detail_payload(entry: Mapping[str, Any]) -> dict[str, Any]:
    documents = [dict(item) for item in entry.get("documents") or [] if isinstance(item, Mapping)]
    ats_documents = [
        document
        for document in documents
        if isinstance(document.get("ats_export_gate"), Mapping)
        or bool(document.get("final_export_blocked"))
        or str(document.get("asset_kind") or "").lower() == "generated_cv"
    ]
    selected_document = next(
        (document for document in ats_documents if document.get("final_export_blocked")),
        ats_documents[0] if ats_documents else {},
    )
    gate = evaluate_ats_export_gate(
        selected_document.get("ats_export_gate")
        if isinstance(selected_document.get("ats_export_gate"), Mapping)
        else {}
    )
    metadata = dict(gate.get("metadata") or {})
    attempt_history = [
        dict(attempt)
        for attempt in metadata.get("attempt_history") or []
        if isinstance(attempt, Mapping)
    ]
    present_criteria = [
        str(item).strip()
        for item in (
            metadata.get("present_requirements")
            or metadata.get("covered_requirements")
            or metadata.get("matched_requirements")
            or []
        )
        if str(item).strip()
    ]
    recommendations: list[str] = []
    for attempt in reversed(attempt_history):
        recommendations.extend(
            str(item).strip()
            for item in attempt.get("improvement_actions") or []
            if str(item).strip()
        )
        if recommendations:
            break
    description = str(entry.get("full_description") or "")
    extraction_warnings: list[str] = []
    if not description.strip():
        description_state = "missing"
        extraction_warnings.append("No stored job description is available for this ATS assessment.")
    elif len(description.strip()) < 200:
        description_state = "insufficient"
        extraction_warnings.append("The stored job description is short and may be a listing teaser.")
    else:
        description_state = "ready"
    if any(marker in description for marker in ("\ufffd", "Ã", "Â", "â€")):
        extraction_warnings.append("The stored job description contains possible encoding corruption.")
    extraction_warnings.extend(
        str(item.get("message") or item.get("title") or "").strip()
        for item in entry.get("application_warnings") or []
        if isinstance(item, Mapping) and str(item.get("message") or item.get("title") or "").strip()
    )
    return {
        "review_id": str(entry.get("review_id") or ""),
        "read_only": True,
        "application": {
            "run_id": str(entry.get("run_id") or ""),
            "job_id": str(entry.get("job_id") or ""),
            "title": str(entry.get("title") or ""),
            "company": str(entry.get("company") or ""),
            "workspace_id": str(entry.get("workspace_id") or ""),
        },
        "score": {
            "best": int(gate.get("best_score") or 0),
            "target": int(gate.get("target_score") or 90),
            "gate_state": str(gate.get("gate_state") or "not_started"),
            "attempt_count": int(gate.get("attempt_count") or 0),
            "max_attempts": int(gate.get("max_attempts") or 3),
            "stop_reason": str(metadata.get("stop_reason") or ""),
            "last_warning": str(gate.get("last_warning") or ""),
        },
        "attempt_history": attempt_history,
        "criteria": {
            "missing": list(gate.get("missing_requirements") or []),
            "present": present_criteria,
        },
        "identifiers": {
            "cv_asset_id": str(metadata.get("workspace_cv_asset_id") or metadata.get("cv_asset_id") or ""),
            "generated_document_id": str(selected_document.get("document_id") or ""),
            "generated_artifact_id": str(metadata.get("artifact_id") or selected_document.get("document_id") or ""),
            "job_description_id": str(entry.get("job_id") or ""),
        },
        "job_description": {
            "state": description_state,
            "char_count": len(description.strip()),
            "warnings": list(dict.fromkeys(extraction_warnings)),
        },
        "scorer": {
            "model": str(metadata.get("model") or metadata.get("scorer_model") or "legacy-unversioned"),
            "prompt_version": str(metadata.get("prompt_version") or "legacy-unversioned"),
        },
        "recommendations": list(dict.fromkeys(recommendations)),
        "diagnostic_limitations": (
            "This view reports the persisted ATS assessment. It does not recalculate or change the score."
        ),
    }


def _tracker_email_secret_name(user) -> str:
    return _tracker_email_named_secret(user, kind="password")


def _tracker_email_named_secret(user, *, kind: str) -> str:
    return f"tracker-email-{kind}-{user.user_id}"


def _get_tracker_email_config(user) -> dict:
    metadata = dict(user.metadata or {})
    return normalize_tracker_email_config(metadata.get(TRACKER_EMAIL_INTEGRATION_METADATA_KEY) or {})


def _persist_tracker_email_config(application, user, config: dict) -> object:
    metadata = dict(user.metadata or {})
    metadata[TRACKER_EMAIL_INTEGRATION_METADATA_KEY] = normalize_tracker_email_config(config)
    user.metadata = metadata
    user.updated_at = datetime.now(timezone.utc).isoformat()
    application.repositories.auth_repository.upsert_user(user)
    return application.get_user(user.user_id)


def _gmail_detection_id(payload: dict | None) -> str:
    detection = normalize_gmail_application_detection(payload or {})
    detection_id = str(detection.get("detection_id") or "").strip()
    if detection_id:
        return detection_id
    message_id = str(detection.get("source_email", {}).get("message_id") or "").strip()
    if message_id:
        return f"gmail::{message_id}"
    return ""


def _merge_pending_tracker_detections(
    *,
    existing: list[dict] | None,
    additions: list[dict] | None = None,
    remove_ids: set[str] | None = None,
) -> list[dict]:
    resolved_ids = {str(item).strip() for item in (remove_ids or set()) if str(item).strip()}
    merged: list[dict] = []
    for payload in [*(additions or []), *(existing or [])]:
        if not isinstance(payload, dict):
            continue
        detection = normalize_gmail_application_detection(payload)
        detection_id = _gmail_detection_id(detection)
        if not detection_id or detection["status"]["approval_state"] != "pending_review" or detection_id in resolved_ids:
            continue
        detection["detection_id"] = detection_id
        merged.append(detection)
    merged.sort(key=lambda item: str(item.get("source_email", {}).get("sent_at") or ""), reverse=True)
    deduped: list[dict] = []
    seen: set[str] = set()
    for detection in merged:
        detection_id = _gmail_detection_id(detection)
        if not detection_id or detection_id in seen:
            continue
        seen.add(detection_id)
        deduped.append(detection)
    return deduped[:50]


_REFERRAL_OUTREACH_METADATA_KEY = "referral_outreach"
_EXTERNAL_TRACKER_APPLICATIONS_METADATA_KEY = "external_tracker_applications"


def _referral_outreach_key(*, run_id: str, job_id: str, contact_id: str) -> str:
    return "::".join([str(run_id or "").strip(), str(job_id or "").strip(), str(contact_id or "").strip()])


def _get_referral_outreach_status(user, *, run_id: str, job_id: str, contact_id: str) -> str:
    metadata = dict(user.metadata or {})
    outreach = dict(metadata.get(_REFERRAL_OUTREACH_METADATA_KEY) or {})
    record = dict(outreach.get(_referral_outreach_key(run_id=run_id, job_id=job_id, contact_id=contact_id)) or {})
    return normalize_referral_outreach_status(record.get("outreach_status"))


def _persist_referral_outreach_status(
    application,
    user,
    *,
    run_id: str,
    job_id: str,
    contact_id: str,
    outreach_status: str,
    contact_snapshot: dict | None = None,
) -> tuple[object, dict]:
    status = normalize_referral_outreach_status(outreach_status)
    metadata = dict(user.metadata or {})
    outreach = dict(metadata.get(_REFERRAL_OUTREACH_METADATA_KEY) or {})
    key = _referral_outreach_key(run_id=run_id, job_id=job_id, contact_id=contact_id)
    snapshot = dict(contact_snapshot or {})
    record = {
        "run_id": str(run_id or "").strip(),
        "job_id": str(job_id or "").strip(),
        "contact_id": str(contact_id or "").strip(),
        "outreach_status": status,
        "contact_name": str(snapshot.get("name") or ""),
        "contact_company": str(snapshot.get("company") or ""),
        "contact_linkedin_url": str(snapshot.get("linkedin_url") or ""),
        "contact_can_refer": bool(snapshot.get("can_refer") or False),
        "relationship_note": str(snapshot.get("relationship_note") or ""),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    outreach[key] = record
    metadata[_REFERRAL_OUTREACH_METADATA_KEY] = outreach
    user.metadata = metadata
    user.updated_at = datetime.now(timezone.utc).isoformat()
    application.repositories.auth_repository.upsert_user(user)
    return application.get_user(user.user_id), record


def _load_referral_outreach_records(user) -> list[dict]:
    metadata = dict(user.metadata or {})
    outreach = dict(metadata.get(_REFERRAL_OUTREACH_METADATA_KEY) or {})
    records: list[dict] = []
    for key, raw_record in outreach.items():
        record = dict(raw_record or {})
        run_id = str(record.get("run_id") or "").strip()
        job_id = str(record.get("job_id") or "").strip()
        contact_id = str(record.get("contact_id") or "").strip()
        if not (run_id and job_id and contact_id):
            key_parts = [part.strip() for part in str(key or "").split("::")]
            if len(key_parts) == 3:
                run_id = run_id or key_parts[0]
                job_id = job_id or key_parts[1]
                contact_id = contact_id or key_parts[2]
        if not (run_id and job_id and contact_id):
            continue
        records.append(
            {
                "run_id": run_id,
                "job_id": job_id,
                "contact_id": contact_id,
                "outreach_status": normalize_referral_outreach_status(record.get("outreach_status")),
                "contact_name": str(record.get("contact_name") or ""),
                "contact_company": str(record.get("contact_company") or ""),
                "contact_linkedin_url": str(record.get("contact_linkedin_url") or ""),
                "contact_can_refer": bool(record.get("contact_can_refer") or False),
                "relationship_note": str(record.get("relationship_note") or ""),
                "updated_at": str(record.get("updated_at") or ""),
            }
        )
    records.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return records


def _collect_referral_outreach_entries(
    application,
    user,
    *,
    contact_id: str = "",
    run_id: str = "",
    job_id: str = "",
) -> list[dict]:
    requested_contact_id = str(contact_id or "").strip()
    requested_run_id = str(run_id or "").strip()
    requested_job_id = str(job_id or "").strip()
    records = [
        record
        for record in _load_referral_outreach_records(user)
        if (not requested_contact_id or record["contact_id"] == requested_contact_id)
        and (not requested_run_id or record["run_id"] == requested_run_id)
        and (not requested_job_id or record["job_id"] == requested_job_id)
    ]
    if not records:
        return []

    workspaces, runs = _collect_authorized_runs(application, user)
    runs_by_id = {run.id: run for run in runs}
    contacts_by_id = {
        contact.contact_id: contact.to_dict() for contact in _referral_contacts_from_user(user)
    }
    jobs_by_run: dict[str, dict[str, object]] = {}
    entries: list[dict] = []

    for record in records:
        run = runs_by_id.get(record["run_id"])
        if run is None:
            continue
        if run.id not in jobs_by_run:
            run_jobs: dict[str, object] = {}
            for job_set in application.list_job_sets(run.id).values():
                for job in job_set:
                    run_jobs[job.job_id] = job
            jobs_by_run[run.id] = run_jobs
        job = jobs_by_run[run.id].get(record["job_id"])
        workspace = workspaces.get(run.workspace_id)
        live_contact = dict(contacts_by_id.get(record["contact_id"]) or {})
        contact_name = str(live_contact.get("name") or record.get("contact_name") or "").strip()
        contact_company = str(live_contact.get("company") or record.get("contact_company") or "").strip()
        contact_linkedin_url = str(
            live_contact.get("linkedin_url") or record.get("contact_linkedin_url") or ""
        ).strip()
        relationship_note = str(
            live_contact.get("relationship_note") or record.get("relationship_note") or ""
        ).strip()
        can_refer = bool(
            live_contact.get("can_refer")
            if "can_refer" in live_contact
            else record.get("contact_can_refer") or False
        )
        apply_link = (
            str(job.apply_link or job.link or job.source_url).strip()
            if job is not None
            else ""
        )
        source_label = (
            str(job.portal or job.source_type or "").strip()
            if job is not None
            else ""
        )
        job_title = str(job.title if job is not None else "").strip()
        company_name = str(job.company if job is not None else "").strip() or contact_company
        entries.append(
            {
                **record,
                "workspace_id": str(run.workspace_id or ""),
                "workspace_name": workspace.name if workspace else run.workspace_id,
                "job_title": job_title,
                "company": company_name,
                "apply_link": apply_link,
                "source_label": source_label,
                "contact_name": contact_name,
                "contact_company": contact_company,
                "contact_can_refer": can_refer,
                "contact_linkedin_url": contact_linkedin_url,
                "relationship_note": relationship_note,
            }
        )
    entries.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return entries


def _save_referral_outreach_status_from_payload(application, user, payload: dict) -> tuple[dict, str]:
    contact_id = str(payload.get("contact_id") or "").strip()
    run_id = str(payload.get("run_id") or "").strip()
    job_id = str(payload.get("job_id") or "").strip()
    if not contact_id or not run_id or not job_id:
        raise ValueError("run_id, job_id, and contact_id are required")
    run = application.get_run(run_id)
    if not application.user_can_access_run(user, run):
        raise PermissionError(f"Workspace access denied for '{run.workspace_id}'.")
    contact = application.get_referral_contact(user.user_id, contact_id)
    previous_status = _get_referral_outreach_status(user, run_id=run_id, job_id=job_id, contact_id=contact_id)
    _, record = _persist_referral_outreach_status(
        application,
        user,
        run_id=run_id,
        job_id=job_id,
        contact_id=contact_id,
        outreach_status=str(payload.get("outreach_status") or ""),
        contact_snapshot=contact.to_dict(),
    )
    return record, previous_status


def _load_external_tracker_applications(user) -> list[dict]:
    metadata = dict(user.metadata or {})
    applications = metadata.get(_EXTERNAL_TRACKER_APPLICATIONS_METADATA_KEY) or []
    return [dict(item) for item in applications if isinstance(item, dict)]


def _persist_external_tracker_applications(application, user, applications: list[dict]) -> object:
    metadata = dict(user.metadata or {})
    metadata[_EXTERNAL_TRACKER_APPLICATIONS_METADATA_KEY] = [dict(item) for item in applications]
    user.metadata = metadata
    user.updated_at = datetime.now(timezone.utc).isoformat()
    application.repositories.auth_repository.upsert_user(user)
    return application.get_user(user.user_id)


def _external_tracker_application_from_detection(detection: dict, *, existing: dict | None = None) -> dict:
    normalized = (
        dict(detection)
        if str(detection.get("schema_version") or "") == "gmail_application_detection_v1"
        else normalize_gmail_application_detection(detection)
    )
    detected = normalized["detected_application"]
    source_email = normalized["source_email"]
    status = normalized["status"]
    now_iso = datetime.now(timezone.utc).isoformat()
    application_id = str((existing or {}).get("application_id") or f"external_{uuid4().hex[:16]}")
    return {
        "application_id": application_id,
        "review_id": application_id,
        "source": "gmail_detection",
        "title": detected["title"],
        "company": detected["company"],
        "application_date": detected["application_date"] or source_email["sent_at"],
        "apply_link": detected["source_url"],
        "tracker_status": legacy_tracker_status_for_application_status(status["suggested_application_status"]),
        "application_status": status["suggested_application_status"],
        "email_confirmed": status["suggested_application_status"] == "Applied",
        "rejection_note": "",
        "notes": f"Imported from Gmail email: {source_email['subject']}",
        "gmail_detection": normalized,
        "placed_in_tracker_at": str(
            (existing or {}).get("placed_in_tracker_at")
            or (existing or {}).get("created_at")
            or now_iso
        ),
        "created_at": str((existing or {}).get("created_at") or now_iso),
        "updated_at": now_iso,
    }


def _upsert_external_tracker_application_from_detection(applications: list[dict], detection: dict) -> dict:
    detection_id = _gmail_detection_id(detection)
    for index, item in enumerate(applications):
        existing_detection = item.get("gmail_detection")
        if not isinstance(existing_detection, dict):
            continue
        if _gmail_detection_id(existing_detection) != detection_id:
            continue
        updated = _external_tracker_application_from_detection(detection, existing=item)
        applications[index] = updated
        return updated
    external_application = _external_tracker_application_from_detection(detection)
    applications.append(external_application)
    return external_application


def _update_external_tracker_application(application, user, application_id: str, payload: dict) -> tuple[object, dict]:
    applications = _load_external_tracker_applications(user)
    for index, item in enumerate(applications):
        if str(item.get("application_id") or "") != application_id:
            continue
        updated = dict(item)
        if "tracker_status" in payload:
            updated["tracker_status"] = str(payload.get("tracker_status") or "").strip().lower()
            updated["application_status"] = normalize_application_status(updated["tracker_status"])
        if "application_status" in payload:
            updated["application_status"] = normalize_application_status(payload.get("application_status"))
            updated["tracker_status"] = legacy_tracker_status_for_application_status(updated["application_status"])
        if "email_confirmed" in payload:
            updated["email_confirmed"] = bool(payload.get("email_confirmed"))
        if "rejection_note" in payload:
            updated["rejection_note"] = str(payload.get("rejection_note") or "")
        if "notes" in payload:
            updated["notes"] = str(payload.get("notes") or "")
        now_iso = datetime.now(timezone.utc).isoformat()
        updated["placed_in_tracker_at"] = str(
            updated.get("placed_in_tracker_at")
            or updated.get("created_at")
            or now_iso
        )
        updated["updated_at"] = now_iso
        applications[index] = updated
        refreshed_user = _persist_external_tracker_applications(application, user, applications)
        return refreshed_user, updated
    raise KeyError(f"External tracker application '{application_id}' not found.")


def _delete_external_tracker_application(application, user, application_id: str) -> tuple[object, dict]:
    applications = _load_external_tracker_applications(user)
    for index, item in enumerate(applications):
        if str(item.get("application_id") or "") != application_id:
            continue
        deleted = dict(item)
        del applications[index]
        refreshed_user = _persist_external_tracker_applications(application, user, applications)
        return refreshed_user, deleted
    raise KeyError(f"External tracker application '{application_id}' not found.")


def _clear_tracker_email_config(application, user) -> object:
    metadata = dict(user.metadata or {})
    metadata.pop(TRACKER_EMAIL_INTEGRATION_METADATA_KEY, None)
    user.metadata = metadata
    user.updated_at = datetime.now(timezone.utc).isoformat()
    application.repositories.auth_repository.upsert_user(user)
    return application.get_user(user.user_id)


def _resolve_tracker_email_password(application, config: dict) -> str:
    return _resolve_tracker_email_secret_value(application, config, secret_key="password_secret_id")


def _resolve_tracker_email_access_token(application, config: dict) -> str:
    return _resolve_tracker_email_secret_value(application, config, secret_key="access_token_secret_id")


def _resolve_tracker_email_refresh_token(application, config: dict) -> str:
    return _resolve_tracker_email_secret_value(application, config, secret_key="refresh_token_secret_id")


def _resolve_tracker_email_secret_value(application, config: dict, *, secret_key: str) -> str:
    secret_id = str(config.get(secret_key) or "").strip()
    if not secret_id:
        return ""
    try:
        return application.resolve_secret_value(secret_id)
    except KeyError:
        return ""


def _upsert_tracker_email_password_secret(application, user, config: dict, password: str) -> str:
    return _upsert_tracker_email_secret(
        application,
        user,
        config=config,
        secret_key="password_secret_id",
        secret_value=password,
        secret_name=_tracker_email_named_secret(user, kind="password"),
        description="Password or app password for tracker email sync.",
        metadata_kind="tracker_email_password",
    )


def _upsert_tracker_email_access_token_secret(application, user, config: dict, access_token: str) -> str:
    return _upsert_tracker_email_secret(
        application,
        user,
        config=config,
        secret_key="access_token_secret_id",
        secret_value=access_token,
        secret_name=_tracker_email_named_secret(user, kind="access-token"),
        description="Google OAuth access token for tracker Gmail sync.",
        metadata_kind="tracker_email_google_access_token",
    )


def _upsert_tracker_email_refresh_token_secret(application, user, config: dict, refresh_token: str) -> str:
    return _upsert_tracker_email_secret(
        application,
        user,
        config=config,
        secret_key="refresh_token_secret_id",
        secret_value=refresh_token,
        secret_name=_tracker_email_named_secret(user, kind="refresh-token"),
        description="Google OAuth refresh token for tracker Gmail sync.",
        metadata_kind="tracker_email_google_refresh_token",
    )


def _upsert_tracker_email_secret(
    application,
    user,
    *,
    config: dict,
    secret_key: str,
    secret_value: str,
    secret_name: str,
    description: str,
    metadata_kind: str,
) -> str:
    secret = application.upsert_secret(
        {
            "secret_id": str(config.get(secret_key) or ""),
            "name": secret_name,
            "provider": "stored",
            "secret_value": secret_value,
            "description": description,
            "metadata": {
                "kind": metadata_kind,
                "user_id": user.user_id,
                "email_address": str(config.get("email_address") or ""),
                "provider_id": str(config.get("provider_id") or ""),
            },
        }
    )
    return secret.secret_id


def _tracker_email_integration_payload(application, user) -> dict:
    config = _get_tracker_email_config(user)
    has_password = bool(_resolve_tracker_email_password(application, config))
    has_access_token = bool(_resolve_tracker_email_access_token(application, config))
    has_refresh_token = bool(_resolve_tracker_email_refresh_token(application, config))
    return {
        "providers": tracker_email_provider_options(),
        "config": build_public_tracker_email_config(
            config,
            has_password=has_password,
            has_access_token=has_access_token,
            has_refresh_token=has_refresh_token,
        ),
    }


def _build_tracker_google_oauth_state(user) -> tuple[str, str]:
    nonce = uuid4().hex
    return nonce, f"{user.user_id}:{nonce}"


def _parse_tracker_google_oauth_state(state: str) -> tuple[str, str]:
    user_id, separator, nonce = str(state or "").partition(":")
    if not separator or not user_id or not nonce:
        return "", ""
    return user_id.strip(), nonce.strip()


def _normalized_document_lookup_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _ordered_run_jobs_for_document_lookup(run, job_sets: Mapping[str, list[object]]) -> list[object]:
    ordered_keys = list(run.final_job_set_keys or []) + [key for key in job_sets if key not in (run.final_job_set_keys or [])]
    ordered_jobs: list[object] = []
    seen_job_ids: set[str] = set()
    for key in ordered_keys:
        for job in job_sets.get(key, []):
            job_id = str(getattr(job, "job_id", "") or "").strip()
            if job_id and job_id in seen_job_ids:
                continue
            if job_id:
                seen_job_ids.add(job_id)
            ordered_jobs.append(job)
    return ordered_jobs


def _run_jobs_for_document_lookup(application, run) -> list[object]:
    return _ordered_run_jobs_for_document_lookup(run, application.list_job_sets(run.id))


def _match_run_job_for_document_entry(entry: dict, run_jobs: list[object]) -> object | None:
    explicit_job_id = str(entry.get("job_id") or "").strip()
    if explicit_job_id:
        for job in run_jobs:
            if str(getattr(job, "job_id", "") or "").strip() == explicit_job_id:
                return job

    raw_text = " ".join(
        str(entry.get(key) or "")
        for key in ("file_name", "relative_path", "path", "artifact_id", "source_artifact_id")
    ).lower()
    compact_text = _normalized_document_lookup_token(raw_text)
    best_match = None
    best_score = 0

    for job in run_jobs:
        job_id = str(getattr(job, "job_id", "") or "").strip()
        title = str(getattr(job, "title", "") or "").strip()
        company = str(getattr(job, "company", "") or "").strip()
        score = 0
        compact_job_id = _normalized_document_lookup_token(job_id)
        compact_title = _normalized_document_lookup_token(title)
        compact_company = _normalized_document_lookup_token(company)

        if job_id and job_id.lower() in raw_text:
            score = max(score, 120)
        if compact_job_id and compact_job_id in compact_text:
            score = max(score, 110)
        if compact_title and compact_title in compact_text:
            score += 30
        if compact_company and compact_company in compact_text:
            score += 24
        if compact_title and compact_company and compact_title in compact_text and compact_company in compact_text:
            score += 30

        if score > best_score:
            best_match = job
            best_score = score

    return best_match if best_score >= 60 else None


def _enrich_artifact_entry_with_job_context(entry: dict, run_jobs: list[object]) -> dict:
    matched_job = _match_run_job_for_document_entry(entry, run_jobs)
    if matched_job is None:
        return entry

    metadata = dict(entry.get("metadata") or {})
    job_id = str(metadata.get("job_id") or entry.get("job_id") or getattr(matched_job, "job_id", "") or "").strip()
    job_title = str(metadata.get("job_title") or entry.get("job_title") or getattr(matched_job, "title", "") or "").strip()
    company = str(metadata.get("company") or entry.get("company") or getattr(matched_job, "company", "") or "").strip()
    if job_id and not metadata.get("job_id"):
        metadata["job_id"] = job_id
    if job_title and not metadata.get("job_title"):
        metadata["job_title"] = job_title
    if company and not metadata.get("company"):
        metadata["company"] = company
    return {
        **entry,
        "job_id": job_id,
        "job_title": job_title,
        "company": company,
        "metadata": metadata,
    }


def _collect_artifact_entries(
    application,
    user,
    *,
    workspace_id: str = "",
    run_id: str = "",
    run_record=None,
    workspace_record=None,
    run_jobs: list[object] | None = None,
    run_records: list[object] | None = None,
    workspace_records: dict[str, object] | None = None,
    job_sets_by_run: dict[str, dict[str, list[object]]] | None = None,
    artifacts_by_run: dict[str, list[object]] | None = None,
    access_checked: bool = False,
) -> list[dict]:
    if run_id:
        run = run_record if str(getattr(run_record, "id", "") or "") == run_id else None
        if run is None:
            try:
                run = application.get_run(run_id)
            except KeyError:
                return []
        if workspace_id and run.workspace_id != workspace_id:
            return []
        if not access_checked and not application.user_can_access_run(user, run):
            return []
        workspace = (
            workspace_record
            if str(getattr(workspace_record, "id", "") or "") == run.workspace_id
            else None
        )
        if workspace is None:
            try:
                workspace = application.get_workspace(run.workspace_id)
            except KeyError:
                workspace = None
        workspaces = {run.workspace_id: workspace} if workspace is not None else {}
        runs = [run]
    elif run_records is not None and workspace_records is not None:
        workspaces = workspace_records
        runs = run_records
    else:
        workspaces, runs = _collect_authorized_runs(application, user, workspace_id=workspace_id)
    snapshot = (
        _load_run_read_snapshot(
            application,
            runs,
            include_artifacts=True,
            preserve_job_sets=False,
        )
        if artifacts_by_run is None and job_sets_by_run is None and not (run_id and run_jobs is not None)
        else None
    )
    resolved_job_sets_by_run = (
        {}
        if run_id and run_jobs is not None
        else (job_sets_by_run or (snapshot or {}).get("job_sets") or _load_job_sets_by_run(application, runs))
    )
    resolved_artifacts_by_run = (
        artifacts_by_run
        or (snapshot or {}).get("artifacts")
        or _load_artifacts_by_run(application, runs)
    )
    entries: list[dict] = []
    for run in runs:
        workspace = workspaces.get(run.workspace_id)
        resolved_run_jobs = (
            run_jobs
            if run_id and run_jobs is not None
            else _ordered_run_jobs_for_document_lookup(
                run,
                resolved_job_sets_by_run.get(run.id, {}),
            )
        )
        artifacts = resolved_artifacts_by_run.get(run.id, [])
        for artifact in artifacts:
            entries.extend(
                _enrich_artifact_entry_with_job_context(entry, resolved_run_jobs)
                for entry in _expand_artifact_entries(run, workspace, artifact)
            )
    entries.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return entries


_CANDIDATE_ASSET_METADATA_KEY = "candidate_assets"
_WORKSPACE_CV_RUNTIME_SETTING_KEYS = (
    "workspace_cv_text",
    "workspace_cv_asset_path",
    "workspace_cv_asset_object_key",
    "workspace_cv_asset_docx_path",
    "workspace_cv_asset_docx_object_key",
    "workspace_cv_asset_display_name",
    "workspace_cv_asset_extension",
    "workspace_cv_asset_mime_type",
)


def _candidate_asset_download_url(asset_id: str) -> str:
    return f"/documents/assets/{asset_id}/download"


def _bulk_export_download_url(bundle_id: str) -> str:
    return f"/documents/bulk-exports/{bundle_id}/download"


def _candidate_asset_storage_dir(user) -> Path:
    return Path("user_config") / "candidate_assets" / str(user.user_id)


def _candidate_asset_bundle_dir(user) -> Path:
    target = _candidate_asset_storage_dir(user) / "bulk_exports"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _load_candidate_assets(user) -> list[dict]:
    metadata = dict(user.metadata or {})
    assets = metadata.get(_CANDIDATE_ASSET_METADATA_KEY) or []
    normalized: list[dict] = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        if str(asset.get("schema_version") or "") == "candidate_asset_descriptor_v1":
            normalized.append(deepcopy(asset))
        else:
            normalized.append(normalize_candidate_asset_descriptor(asset))
    return normalized


def _get_candidate_asset_by_id(user, asset_id: str) -> dict:
    target_asset_id = str(asset_id or "").strip()
    for asset in _load_candidate_assets(user):
        if str(asset.get("asset_id") or "").strip() == target_asset_id:
            return asset
    raise ValueError(f"Workspace CV asset '{target_asset_id}' was not found.")


def _candidate_asset_file_path(application, asset: dict) -> Path | None:
    file_payload = dict(asset.get("file") or {})
    raw_path = str(file_payload.get("path") or asset.get("path") or "").strip()
    object_key = str(file_payload.get("object_key") or "").strip()
    if object_key:
        return materialize_object(
            application.object_storage,
            object_key,
            filename=str(asset.get("display_name") or Path(raw_path).name or ""),
        )
    return Path(raw_path) if raw_path else None


def _resolve_workspace_cv_binding(application, user, asset_id: str) -> tuple[dict[str, str], dict]:
    asset = _get_candidate_asset_by_id(user, asset_id)
    asset_kind = str(asset.get("asset_kind") or "").strip().lower()
    if asset_kind != "workspace_cv":
        raise ValueError(f"Asset '{asset_id}' is not a workspace CV.")

    metadata = dict(asset.get("metadata") or {})
    file_payload = dict(asset.get("file") or {})
    processing_status = str(metadata.get("status") or "").strip().lower()
    if processing_status in {"uploaded", "queued", "processing"}:
        raise ValueError(f"Workspace CV asset '{asset_id}' is still processing.")
    if processing_status == "failed":
        raise ValueError(f"Workspace CV asset '{asset_id}' failed processing.")
    object_key = str(file_payload.get("object_key") or "").strip()
    raw_path = str(file_payload.get("path") or asset.get("path") or "").strip()
    cv_text = str(metadata.get("source_text") or "").strip()
    if object_key and cv_text:
        try:
            if not application.object_storage.exists(object_key):
                raise ValueError(f"Workspace CV asset '{asset_id}' is missing its source file.")
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"Workspace CV asset '{asset_id}' is missing its source file.") from exc
    elif not object_key and (not raw_path or not Path(raw_path).is_file()):
        raise ValueError(f"Workspace CV asset '{asset_id}' is missing its source file.")

    if not cv_text:
        if object_key:
            try:
                source_bytes = application.object_storage.get(object_key)
            except Exception as exc:
                raise ValueError(f"Workspace CV asset '{asset_id}' is missing its source file.") from exc
            cv_text = str(
                extract_document_text(
                    str(asset.get("display_name") or Path(raw_path).name or "workspace-cv"),
                    source_bytes,
                    allow_ocr=False,
                ).get("text")
                or ""
            )
        else:
            cv_text = extract_cv_text_from_path(raw_path)
    if not cv_text:
        raise ValueError(f"Workspace CV asset '{asset_id}' does not contain readable text.")

    companion_key = str(metadata.get("word_companion_object_key") or "").strip()
    display_name = str(asset.get("display_name") or Path(raw_path).name or asset_id)
    return (
        {
            "workspace_cv_text": cv_text,
            "workspace_cv_asset_path": "",
            "workspace_cv_asset_object_key": object_key,
            "workspace_cv_asset_docx_path": "",
            "workspace_cv_asset_docx_object_key": companion_key,
            "workspace_cv_asset_display_name": display_name,
            "workspace_cv_asset_extension": str(
                file_payload.get("extension") or Path(display_name).suffix.lower().lstrip(".")
            ),
            "workspace_cv_asset_mime_type": str(
                file_payload.get("mime_type") or mimetypes.guess_type(display_name)[0] or ""
            ),
        },
        deepcopy(asset),
    )


def _prepare_workspace_builder_payload_with_cv(
    application,
    payload: dict,
    user,
    *,
    existing_workspace=None,
) -> tuple[dict, dict[str, str]]:
    try:
        user = application.get_user(user.user_id)
    except Exception:
        pass
    builder_payload = deepcopy(dict(payload or {}))
    flow_id = str(
        builder_payload.get("flow_id")
        or getattr(existing_workspace, "metadata", {}).get("automation_flow")
        or getattr(existing_workspace, "settings", {}).get("automation_flow")
        or ""
    ).strip()
    if flow_id and flow_id != "tailored_documents":
        return builder_payload, {}

    settings = dict(builder_payload.get("settings") or {})
    asset_id = str(settings.get("workspace_cv_asset_id") or builder_payload.get("workspace_cv_asset_id") or "").strip()
    if not asset_id and existing_workspace is not None:
        asset_id = str(getattr(existing_workspace, "settings", {}).get("workspace_cv_asset_id") or "").strip()
        if asset_id:
            settings["workspace_cv_asset_id"] = asset_id

    if (flow_id or "tailored_documents") == "tailored_documents":
        if asset_id:
            try:
                runtime_settings, workspace_cv_asset = _resolve_workspace_cv_binding(application, user, asset_id)
            except ValueError as exc:
                message = str(exc)
                if "was not found" in message:
                    field_error_code = "workspace_cv_asset_unresolved"
                    field_error_message = "Select an accessible workspace CV before saving or running this workspace."
                elif "is not a workspace CV" in message:
                    field_error_code = "workspace_cv_asset_invalid_kind"
                    field_error_message = "workspace_cv_asset_id must reference an uploaded workspace CV."
                elif "missing its source file" in message:
                    field_error_code = "workspace_cv_asset_missing_file"
                    field_error_message = "The selected workspace CV is no longer available in durable storage."
                else:
                    field_error_code = "workspace_cv_asset_unreadable"
                    field_error_message = "The selected workspace CV does not contain readable text."
                raise BackendValidationError(
                    "workspace_validation_failed",
                    "Workspace validation failed.",
                    details={
                        "phase": "save",
                        "workspace_id": str(
                            builder_payload.get("workspace_id")
                            or getattr(existing_workspace, "id", "")
                            or ""
                        ).strip(),
                        "flow_id": flow_id or "tailored_documents",
                        "source_ids": [
                            str(item).strip()
                            for item in builder_payload.get("source_ids") or []
                            if str(item).strip()
                        ],
                        "module_ids": [
                            str(item).strip()
                            for item in builder_payload.get("module_ids") or []
                            if str(item).strip()
                        ],
                        "field_errors": [
                            {
                                "field": "workspace_cv_asset_id",
                                "code": field_error_code,
                                "message": field_error_message,
                            }
                        ],
                        "source_results": [],
                    },
                ) from exc
            settings.update(runtime_settings)
            builder_payload["workspace_cv_asset"] = workspace_cv_asset
            metadata = dict(builder_payload.get("metadata") or {})
            metadata["workspace_cv_asset"] = workspace_cv_asset
            builder_payload["metadata"] = metadata

    builder_payload["settings"] = settings
    return builder_payload, {
        key: str(settings.get(key) or "")
        for key in _WORKSPACE_CV_RUNTIME_SETTING_KEYS
        if str(settings.get(key) or "")
    }


def _persist_workspace_runtime_settings(application, workspace, runtime_settings: dict[str, str]):
    if not runtime_settings:
        return workspace
    workspace_payload = workspace.to_dict()
    merged_settings = dict(workspace_payload.get("settings") or {})
    merged_settings.update(runtime_settings)
    workspace_payload["settings"] = merged_settings
    return application.upsert_workspace(workspace_payload)


def _persist_candidate_assets(application, user, assets: list[dict]) -> object:
    metadata = dict(user.metadata or {})
    metadata[_CANDIDATE_ASSET_METADATA_KEY] = [
        deepcopy(asset)
        if str(asset.get("schema_version") or "") == "candidate_asset_descriptor_v1"
        else normalize_candidate_asset_descriptor(asset)
        for asset in assets
        if isinstance(asset, dict)
    ]
    user.metadata = metadata
    user.updated_at = datetime.now(timezone.utc).isoformat()
    application.repositories.auth_repository.upsert_user(user)
    return application.get_user(user.user_id)


def _upsert_candidate_asset(application, user, payload: dict) -> dict:
    assets = _load_candidate_assets(user)
    normalized = normalize_candidate_asset_descriptor(payload)
    for index, asset in enumerate(assets):
        if asset["asset_id"] == normalized["asset_id"]:
            assets[index] = normalized
            _persist_candidate_assets(application, user, assets)
            return normalized
    assets.append(normalized)
    _persist_candidate_assets(application, user, assets)
    return normalized


def _candidate_asset_stored_content_hash(asset: dict) -> str:
    metadata = dict(asset.get("metadata") or {})
    return str(metadata.get("content_sha256") or "").strip()


def _candidate_asset_is_ready(asset: dict) -> bool:
    metadata = dict(asset.get("metadata") or {})
    return (
        str(metadata.get("status") or "").strip().lower() == CV_STATUS_READY
        and bool(str(metadata.get("source_text") or "").strip())
    )


def _dedupe_workspace_cv_assets_for_display(
    assets: list[dict],
    *,
    referenced_asset_ids: set[str],
) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for asset in assets:
        asset_id = str(asset.get("asset_id") or "").strip()
        asset_kind = str(asset.get("asset_kind") or "").strip()
        origin = str(asset.get("source", {}).get("origin") or "upload").strip()
        if not asset_id or asset_kind != "workspace_cv" or origin != "upload":
            continue
        content_hash = _candidate_asset_stored_content_hash(asset)
        if not content_hash:
            continue
        grouped.setdefault(content_hash, []).append(asset)

    duplicate_asset_ids: set[str] = set()
    for duplicate_group in grouped.values():
        if len(duplicate_group) < 2:
            continue
        canonical = next(
            (
                asset
                for asset in duplicate_group
                if str(asset.get("asset_id") or "").strip() in referenced_asset_ids
            ),
            duplicate_group[0],
        )
        canonical_id = str(canonical.get("asset_id") or "").strip()
        for asset in duplicate_group:
            asset_id = str(asset.get("asset_id") or "").strip()
            if asset_id and asset_id != canonical_id:
                duplicate_asset_ids.add(asset_id)

    return [
        asset
        for asset in assets
        if str(asset.get("asset_id") or "").strip() not in duplicate_asset_ids
    ]


def _update_candidate_asset_section_decisions(
    application,
    user,
    asset_id: str,
    raw_decisions: Any,
) -> dict:
    target_asset_id = str(asset_id or "").strip()
    if not target_asset_id:
        raise ValueError("asset_id is required.")
    assets = _load_candidate_assets(user)
    for index, asset in enumerate(assets):
        if str(asset.get("asset_id") or "").strip() != target_asset_id:
            continue
        if str(asset.get("asset_kind") or "").strip().lower() != "workspace_cv":
            raise ValueError("Section decisions are only supported for workspace CV assets.")
        metadata = dict(asset.get("metadata") or {})
        metadata["cv_section_decisions"] = _normalize_cv_section_decisions(raw_decisions)
        asset["metadata"] = metadata
        assets[index] = asset
        refreshed_user = _persist_candidate_assets(application, user, assets)
        refreshed_asset = _get_candidate_asset_by_id(refreshed_user, target_asset_id)
        workspace_names = {
            workspace.id: workspace.name
            for workspace in application.list_workspaces()
            if application.user_can_access_workspace(refreshed_user, workspace.id)
        }
        shared_profile = dict((refreshed_user.metadata or {}).get("profile") or {})
        return _candidate_asset_to_document_item(refreshed_asset, workspace_names, shared_profile)
    raise KeyError(f"Candidate asset '{target_asset_id}' not found.")


def _store_candidate_asset_upload(
    application,
    user,
    *,
    filename: str,
    file_bytes: bytes,
    asset_kind: str,
    display_name: str = "",
    workspace_id: str = "",
    role: str = "",
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    timings_ms: dict[str, float | None] | None = None,
) -> dict:
    def record_duration(stage: str, started: float) -> None:
        if timings_ms is None:
            return
        duration_ms = round((perf_counter() - started) * 1000, 2)
        previous = timings_ms.get(stage)
        timings_ms[stage] = round((float(previous) if previous is not None else 0.0) + duration_ms, 2)

    content_hash = sha256(file_bytes).hexdigest()
    dedupe_started = perf_counter()
    try:
        for existing in _load_candidate_assets(user):
            if str(existing.get("asset_kind") or "").strip() != asset_kind:
                continue
            if _candidate_asset_stored_content_hash(existing) != content_hash:
                continue
            return normalize_candidate_asset_descriptor(existing)
    finally:
        record_duration("dedupe_lookup", dedupe_started)

    asset_id = f"asset_{uuid4().hex[:16]}"
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    extension = Path(filename or "").suffix.lower().lstrip(".")
    object_key = build_private_object_key(
        namespace="users",
        owner_id=user.user_id,
        category=asset_kind,
        object_id=asset_id,
        filename=filename or f"{asset_id}.bin",
    )
    uploaded_keys: list[str] = []
    storage_started = perf_counter()
    try:
        application.object_storage.put(
            object_key,
            file_bytes,
            content_type=content_type,
            metadata={"user_id": str(user.user_id), "asset_id": asset_id, "asset_kind": asset_kind},
        )
        uploaded_keys.append(object_key)
    finally:
        record_duration("r2_storage", storage_started)
    normalized_metadata = dict(metadata or {})
    normalized_metadata["content_sha256"] = content_hash
    try:
        if asset_kind == "workspace_cv" and extension != "docx":
            source_text = str(normalized_metadata.get("source_text") or "").strip()
            if source_text:
                word_companion_bytes = create_word_companion_bytes(source_text, title=display_name or filename)
                word_companion_name = f"{Path(filename or asset_id).stem or asset_id}.docx"
                word_companion_key = build_private_object_key(
                    namespace="users",
                    owner_id=user.user_id,
                    category=asset_kind,
                    object_id=f"{asset_id}-word-companion",
                    filename=word_companion_name,
                )
                companion_storage_started = perf_counter()
                try:
                    application.object_storage.put(
                        word_companion_key,
                        word_companion_bytes,
                        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        metadata={"user_id": str(user.user_id), "asset_id": asset_id},
                    )
                    uploaded_keys.append(word_companion_key)
                finally:
                    record_duration("r2_storage", companion_storage_started)
                normalized_metadata.update(
                    {
                        "word_companion_path": "",
                        "word_companion_object_key": word_companion_key,
                        "word_companion_mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    }
                )

        turso_started = perf_counter()
        try:
            return _upsert_candidate_asset(
                application,
                user,
                {
                    "asset_id": asset_id,
                    "asset_kind": asset_kind,
                    "display_name": display_name or filename or asset_id,
                    "workspace_id": workspace_id,
                    "asset_role": role or asset_kind,
                    "source_origin": "upload",
                    "path": "",
                    "object_key": object_key,
                    "download_url": _candidate_asset_download_url(asset_id),
                    "mime_type": content_type,
                    "extension": extension,
                    "metadata": {
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "tags": list(tags or []),
                        **normalized_metadata,
                    },
                },
            )
        finally:
            record_duration("turso_write", turso_started)
    except Exception:
        for uploaded_key in reversed(uploaded_keys):
            try:
                application.object_storage.delete(uploaded_key)
            except Exception:
                pass
        raise


def _document_group_for_asset_kind(asset_kind: str) -> tuple[str, str]:
    normalized_kind = str(asset_kind or "").strip().lower()
    if normalized_kind == "generated_cv":
        return "generated_cvs", "Generated CVs"
    if normalized_kind == APPLIED_CV_ASSET_KIND:
        return "applied_cvs", "Applied CVs"
    if normalized_kind == "workspace_cv":
        return "uploaded_cvs", "Uploaded CVs"
    if normalized_kind == "master_career_profile":
        return "career_profiles", "Master Career Profiles"
    if normalized_kind in {"cover_letter", "motivation_letter"}:
        return "generated_letters", "Generated Letters"
    if normalized_kind == "bundle_export":
        return "exported_bundles", "Exported Bundles"
    return "supporting_documents", "Supporting Documents"


def _document_type_for_asset_kind(asset_kind: str) -> str:
    normalized_kind = str(asset_kind or "").strip().lower()
    if normalized_kind == "workspace_cv":
        return "Original CV"
    if normalized_kind == "master_career_profile":
        return "Master Career Profile"
    if normalized_kind == APPLIED_CV_ASSET_KIND:
        return APPLIED_CV_DOCUMENT_TYPE
    if normalized_kind == "generated_cv":
        return "Tailored CV"
    if normalized_kind in {"cover_letter", "motivation_letter"}:
        return "Cover letter"
    if normalized_kind == "recommendation_letter":
        return "Recommendation letter"
    if "transcript" in normalized_kind:
        return "Transcript"
    if "certificate" in normalized_kind or "certification" in normalized_kind:
        return "Certificate"
    if normalized_kind == "uploaded_document":
        return "Supporting document"
    return "Other"


def _clean_int(value, *, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except Exception:
        return default


def _evaluate_ats_export_gate_payload(payload: dict, *, export_anyway: bool = False) -> dict:
    return evaluate_ats_export_gate(payload, export_anyway=export_anyway)


def _evaluate_ats_export_gate_for_document(document: dict, *, export_anyway: bool = False) -> dict:
    metadata = dict(document.get("metadata") or {})
    nested_gate = metadata.get("ats_export_gate") if isinstance(metadata.get("ats_export_gate"), dict) else {}
    gate_metadata = dict((nested_gate or {}).get("metadata") or {})
    for metadata_key in (
        "artifact_id",
        "cv_asset_id",
        "workspace_cv_asset_id",
        "model",
        "scorer_model",
        "prompt_version",
        "present_requirements",
        "covered_requirements",
        "matched_requirements",
    ):
        if metadata.get(metadata_key) is not None and metadata_key not in gate_metadata:
            gate_metadata[metadata_key] = metadata.get(metadata_key)
    if metadata.get("ats_stop_reason") and "stop_reason" not in gate_metadata:
        gate_metadata["stop_reason"] = metadata.get("ats_stop_reason")
    if metadata.get("ats_attempt_history") and "attempt_history" not in gate_metadata:
        gate_metadata["attempt_history"] = metadata.get("ats_attempt_history")
    payload = {
        **dict(nested_gate or {}),
        "target_score": metadata.get("ats_target_score")
        or metadata.get("target_score")
        or (nested_gate or {}).get("target_score")
        or 90,
        "best_score": metadata.get("ats_best_score")
        or metadata.get("best_score")
        or metadata.get("ats_score")
        or metadata.get("score")
        or (nested_gate or {}).get("best_score")
        or 0,
        "attempt_count": metadata.get("ats_attempt_count")
        or metadata.get("attempt_count")
        or (nested_gate or {}).get("attempt_count")
        or 0,
        "max_attempts": metadata.get("ats_max_attempts")
        or metadata.get("max_attempts")
        or (nested_gate or {}).get("max_attempts")
        or 3,
        "gate_state": metadata.get("ats_gate_state")
        or metadata.get("gate_state")
        or (nested_gate or {}).get("gate_state")
        or "not_started",
        "can_export_final": metadata.get("ats_can_export_final")
        if metadata.get("ats_can_export_final") is not None
        else metadata.get("can_export_final")
        if metadata.get("can_export_final") is not None
        else (nested_gate or {}).get("can_export_final"),
        "export_anyway_allowed": metadata.get("ats_export_anyway_allowed")
        if metadata.get("ats_export_anyway_allowed") is not None
        else metadata.get("export_anyway_allowed")
        if metadata.get("export_anyway_allowed") is not None
        else (nested_gate or {}).get("export_anyway_allowed"),
        "missing_requirements": metadata.get("missing_requirements")
        or metadata.get("ats_missing_requirements")
        or (nested_gate or {}).get("missing_requirements")
        or [],
        "last_warning": metadata.get("ats_last_warning")
        or metadata.get("last_warning")
        or (nested_gate or {}).get("last_warning")
        or "",
        "metadata": gate_metadata,
    }
    return _evaluate_ats_export_gate_payload(payload, export_anyway=export_anyway)


def _document_requires_ats_gate(document: dict) -> bool:
    document_type = str(document.get("document_type") or "").casefold()
    asset_kind = str(document.get("asset_kind") or "").casefold()
    if document_type == "tailored cv" or asset_kind == "generated_cv":
        return True
    return False


def _assert_document_export_allowed(document: dict, *, export_anyway: bool = False) -> None:
    if not _document_requires_ats_gate(document):
        return
    gate = _evaluate_ats_export_gate_for_document(document, export_anyway=export_anyway)
    if not gate["can_export_final"]:
        raise AtsExportBlockedError(gate)


def _document_display_status(item: dict) -> str:
    if bool(item.get("final_export_blocked")):
        return "export_blocked"
    return str(
        item.get("status")
        or (item.get("application_document") or {}).get("status")
        or "ready"
    ).strip() or "ready"


def _document_group_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")[:80]


def _build_document_library_grouping(item: dict) -> dict:
    related_application = dict(item.get("related_application") or {})
    job_id = str(related_application.get("job_id") or item.get("job_id") or "").strip()
    job_title = str(related_application.get("title") or item.get("job_title") or "").strip()
    company = str(related_application.get("company") or item.get("company") or "").strip()
    run_id = str(item.get("run_id") or "").strip()
    workspace_id = str(item.get("workspace_id") or "").strip()
    workspace_name = str(item.get("workspace_name") or workspace_id or "").strip()
    display_status = _document_display_status(item)

    if job_id or job_title or company:
        if job_title and company:
            group_label = f"{job_title} at {company}"
        elif job_title:
            group_label = job_title
        elif company:
            group_label = company
        else:
            group_label = job_id or "Application"
        group_token = job_id or _document_group_token(f"{company} {job_title}") or str(item.get("document_id") or "application")
        return {
            "group_id": f"application::{run_id or 'manual'}::{group_token}",
            "group_label": group_label,
            "group_kind": "application",
            "display_status": display_status,
        }
    if run_id:
        return {
            "group_id": f"run::{run_id}",
            "group_label": f"Run {run_id} outputs",
            "group_kind": "run",
            "display_status": display_status,
        }
    if workspace_id:
        return {
            "group_id": f"workspace_library::{workspace_id}",
            "group_label": f"Reusable assets for {workspace_name or workspace_id}",
            "group_kind": "workspace_library",
            "display_status": display_status,
        }
    return {
        "group_id": "shared_library",
        "group_label": "Reusable candidate assets",
        "group_kind": "shared_library",
        "display_status": display_status,
    }


def _document_group_payloads(entries: list[dict]) -> list[dict]:
    grouped: dict[str, dict] = {}
    for item in entries:
        group_id = str(item.get("group_id") or item.get("document_id") or "").strip()
        if not group_id:
            continue
        if group_id not in grouped:
            grouped[group_id] = {
                "group_id": group_id,
                "group_label": str(item.get("group_label") or ""),
                "group_kind": str(item.get("group_kind") or ""),
                "workspace_id": str(item.get("workspace_id") or ""),
                "workspace_name": str(item.get("workspace_name") or ""),
                "run_id": str(item.get("run_id") or ""),
                "job_id": str(item.get("job_id") or ""),
                "job_title": str(item.get("job_title") or ""),
                "company": str(item.get("company") or ""),
                "count": 0,
                "latest_created_at": str(item.get("created_at") or ""),
                "status_counts": {},
            }
        group = grouped[group_id]
        group["count"] += 1
        created_at = str(item.get("created_at") or "")
        if created_at and created_at > str(group.get("latest_created_at") or ""):
            group["latest_created_at"] = created_at
        status_key = str(item.get("display_status") or item.get("status") or "ready")
        status_counts = dict(group.get("status_counts") or {})
        status_counts[status_key] = int(status_counts.get(status_key) or 0) + 1
        group["status_counts"] = status_counts
    return list(grouped.values())


def _attach_application_document_contract(item: dict) -> dict:
    document_type = _document_type_for_asset_kind(str(item.get("asset_kind") or ""))
    metadata = dict(item.get("metadata") or {})
    metadata["source_origin"] = item.get("source_origin")
    payload = {
        **item,
        "document_type": document_type,
        "document_name": item.get("display_name"),
        "title": item.get("job_title"),
        "path": item.get("relative_path"),
        "metadata": metadata,
    }
    normalized = normalize_application_document(payload)
    gate = _evaluate_ats_export_gate_for_document({**item, "document_type": normalized["document_type"]})
    document_item = {
        **item,
        "job_id": str(
            normalized["related_application"].get("job_id")
            or item.get("job_id")
            or metadata.get("job_id")
            or ""
        ),
        "job_title": str(
            normalized["related_application"].get("title")
            or item.get("job_title")
            or metadata.get("job_title")
            or ""
        ),
        "company": str(
            normalized["related_application"].get("company")
            or item.get("company")
            or metadata.get("company")
            or ""
        ),
        "status": normalized["status"],
        "document_type": normalized["document_type"],
        "related_application": dict(normalized["related_application"]),
        "application_document": normalized,
        "ats_export_gate": gate,
        "final_export_blocked": _document_requires_ats_gate({**item, "document_type": normalized["document_type"]})
        and not gate["can_export_final"],
    }
    return {
        **document_item,
        "kind_group_id": str(item.get("group_id") or ""),
        "kind_group_label": str(item.get("group_label") or ""),
        **_build_document_library_grouping(document_item),
    }


def _document_id_for_artifact(run_id: str, artifact_id: str) -> str:
    return f"artifact::{run_id}::{artifact_id}"


def _document_id_for_candidate_asset(asset_id: str) -> str:
    return f"asset::{asset_id}"


def _artifact_asset_kind(entry: dict) -> str:
    metadata = dict(entry.get("metadata") or {})
    documented_kind = str(
        metadata.get("document_asset_kind")
        or metadata.get("asset_kind")
        or ""
    ).strip().lower()
    if documented_kind:
        return documented_kind
    artifact_type = str(entry.get("artifact_type") or "").strip().lower()
    if artifact_type == APPLIED_CV_ASSET_KIND:
        return APPLIED_CV_ASSET_KIND
    hints = " ".join(
        str(entry.get(key) or "").lower()
        for key in ("artifact_type", "file_name", "relative_path", "source_artifact_type")
    )
    if bool(entry.get("is_cv")):
        return "generated_cv"
    if "cover" in hints or "motivation" in hints or "anschreiben" in hints or "email" in hints:
        return "cover_letter"
    if "bundle" in hints or "package" in hints or "stage5" in hints:
        return "bundle_export"
    return "uploaded_document"


def _artifact_entry_is_user_facing_document(entry: dict) -> bool:
    artifact_type = str(entry.get("artifact_type") or "").strip().lower()
    source_artifact_type = str(entry.get("source_artifact_type") or "").strip().lower()
    if artifact_type in {"documents_json", "documents_xlsx"} or source_artifact_type in {
        "documents_json",
        "documents_xlsx",
    }:
        return False
    hints = " ".join(
        str(entry.get(key) or "").lower()
        for key in ("artifact_type", "file_name", "relative_path", "source_artifact_type")
    )
    if "email" in hints:
        return False
    if bool(entry.get("is_cv")):
        return True
    return any(
        keyword in hints
        for keyword in (
            "cover",
            "motivation",
            "anschreiben",
            "certificate",
            "certification",
            "recommendation",
            "reference",
            "transcript",
            "zeugnis",
        )
    )


def _artifact_entry_to_document_item(entry: dict) -> dict:
    asset_kind = _artifact_asset_kind(entry)
    group_id, group_label = _document_group_for_asset_kind(asset_kind)
    metadata = dict(entry.get("metadata") or {})
    raw_display_name = str(
        metadata.get("document_display_name")
        or metadata.get("document_name")
        or entry.get("file_name")
        or ""
    ).strip()
    display_name = raw_display_name
    if not str(metadata.get("document_display_name") or metadata.get("document_name") or "").strip():
        if asset_kind in {"generated_cv", APPLIED_CV_ASSET_KIND, "cover_letter", "motivation_letter"}:
            display_name = str(_document_type_for_asset_kind(asset_kind) or raw_display_name or "Document").strip()
    return _attach_application_document_contract({
        "document_id": _document_id_for_artifact(entry["run_id"], entry["artifact_id"]),
        "asset_id": "",
        "asset_kind": asset_kind,
        "group_id": group_id,
        "group_label": group_label,
        "display_name": display_name,
        "workspace_id": str(entry.get("workspace_id") or ""),
        "workspace_name": str(entry.get("workspace_name") or ""),
        "run_id": str(entry.get("run_id") or ""),
        "job_id": str(entry.get("job_id") or ""),
        "job_title": str(entry.get("job_title") or ""),
        "company": str(entry.get("company") or ""),
        "status": str(entry.get("status") or "ready"),
        "created_at": str(entry.get("created_at") or ""),
        "source_origin": "generated_run",
        "download_url": str(entry.get("download_url") or ""),
        "preview_url": str(entry.get("download_url") or ""),
        "relative_path": str(entry.get("relative_path") or ""),
        "file_name": str(entry.get("file_name") or ""),
        "content_type": str(entry.get("content_type") or ""),
        "tags": [],
        "metadata": metadata,
        "is_generated": True,
    })


def _candidate_asset_to_document_item(
    asset: dict,
    workspace_names: dict[str, str],
    shared_profile: dict[str, Any],
) -> dict:
    asset_kind = str(asset.get("asset_kind") or "uploaded_document")
    group_id, group_label = _document_group_for_asset_kind(asset_kind)
    workspace_id = str(asset.get("workspace_binding", {}).get("workspace_id") or "")
    metadata = dict(asset.get("metadata") or {})
    preview_profile: dict[str, Any] = {}
    if asset_kind == "workspace_cv":
        cv_text = str(metadata.get("source_text") or "").strip()
        preview_profile = _build_workspace_cv_preview_profile(
            cv_text,
            shared_profile,
            asset_display_name=str(asset.get("display_name") or ""),
            parsed_profile=dict(metadata.get("parsed_profile") or {}),
            section_decisions=_normalize_cv_section_decisions(metadata.get("cv_section_decisions") or []),
        )
    return _attach_application_document_contract({
        "document_id": _document_id_for_candidate_asset(str(asset.get("asset_id") or "")),
        "asset_id": str(asset.get("asset_id") or ""),
        "asset_kind": asset_kind,
        "group_id": group_id,
        "group_label": group_label,
        "display_name": str(asset.get("display_name") or ""),
        "workspace_id": workspace_id,
        "workspace_name": workspace_names.get(workspace_id, workspace_id),
        "run_id": str(asset.get("source", {}).get("run_id") or ""),
        "job_id": str(metadata.get("job_id") or asset.get("job_id") or ""),
        "job_title": "",
        "company": "",
        "status": str(metadata.get("status") or "ready"),
        "created_at": str(metadata.get("created_at") or ""),
        "source_origin": str(asset.get("source", {}).get("origin") or "upload"),
        "download_url": str(asset.get("file", {}).get("download_url") or ""),
        "preview_url": str(asset.get("file", {}).get("download_url") or ""),
        "relative_path": str(asset.get("file", {}).get("path") or ""),
        "file_name": Path(str(asset.get("file", {}).get("path") or asset.get("path") or "")).name,
        "content_type": str(asset.get("file", {}).get("mime_type") or ""),
        "tags": list(metadata.get("tags") or []),
        "metadata": metadata,
        "is_generated": str(asset.get("source", {}).get("origin") or "upload") != "upload",
        "preview_profile": preview_profile,
    })


def _collect_document_entries(
    application,
    user,
    *,
    workspace_id: str = "",
    run_id: str = "",
    asset_kind: str = "",
    run_record=None,
    workspace_record=None,
    run_jobs: list[object] | None = None,
    run_records: list[object] | None = None,
    workspace_records: dict[str, object] | None = None,
    job_sets_by_run: dict[str, dict[str, list[object]]] | None = None,
    artifacts_by_run: dict[str, list[object]] | None = None,
    access_checked: bool = False,
) -> list[dict]:
    asset_kind_filter = str(asset_kind or "").strip().lower()
    raw_profile = dict((user.metadata or {}).get("profile") or {})
    shared_profile = {
        "name": str(raw_profile.get("name") or user.display_name or user.email.split("@")[0]),
        "role_title": str(raw_profile.get("role_title") or ""),
        "industry": str(raw_profile.get("industry") or ""),
        "email": str(raw_profile.get("email") or user.email),
        "location": str(raw_profile.get("location") or ""),
        "website": str(raw_profile.get("website") or ""),
        "linkedin_url": str(raw_profile.get("linkedin_url") or ""),
        "github_url": str(raw_profile.get("github_url") or ""),
        "summary": str(raw_profile.get("summary") or ""),
        "competencies": list(raw_profile.get("competencies") or []),
        "languages": list(raw_profile.get("languages") or []),
        "projects": list(raw_profile.get("projects") or []),
        "custom_sections": list(raw_profile.get("custom_sections") or []),
        "recent_experience": list(raw_profile.get("recent_experience") or []),
        "education": list(raw_profile.get("education") or []),
        "photo_data_url": str(raw_profile.get("photo_data_url") or ""),
        "avatar_url": str(raw_profile.get("avatar_url") or ""),
    }
    run_artifacts_requested = not (
        asset_kind_filter in {"workspace_cv", "master_career_profile"} and not run_id
    )
    entries = []
    if run_artifacts_requested:
        entries = [
            _artifact_entry_to_document_item(entry)
            for entry in _collect_artifact_entries(
                application,
                user,
                workspace_id=workspace_id,
                run_id=run_id,
                run_record=run_record,
                workspace_record=workspace_record,
                run_jobs=run_jobs,
                run_records=run_records,
                workspace_records=workspace_records,
                job_sets_by_run=job_sets_by_run,
                artifacts_by_run=artifacts_by_run,
                access_checked=access_checked,
            )
            if _artifact_entry_is_user_facing_document(entry)
        ]

    candidate_assets_requested = not run_id
    if candidate_assets_requested:
        accessible_workspaces = [
            workspace
            for workspace in (
                list(workspace_records.values())
                if workspace_records is not None
                else application.list_workspaces()
            )
            if application.user_can_access_workspace(user, workspace.id)
        ]
        workspaces = {
            workspace.id: workspace.name
            for workspace in accessible_workspaces
        }
        referenced_asset_ids = {
            str(getattr(workspace, "settings", {}).get("workspace_cv_asset_id") or "").strip()
            for workspace in accessible_workspaces
            if str(getattr(workspace, "settings", {}).get("workspace_cv_asset_id") or "").strip()
        }
        candidate_assets = _dedupe_workspace_cv_assets_for_display(
            _load_candidate_assets(user),
            referenced_asset_ids=referenced_asset_ids,
        )
        for asset in candidate_assets:
            asset_workspace_id = str(asset.get("workspace_binding", {}).get("workspace_id") or "")
            if workspace_id and asset_workspace_id and asset_workspace_id != workspace_id:
                continue
            asset_for_item = deepcopy(asset)
            asset_metadata = dict(asset_for_item.get("metadata") or {})
            processing = dict(asset_metadata.get("cv_processing") or {})
            processing_job_id = str(processing.get("job_id") or "").strip()
            persisted_status = str(asset_metadata.get("status") or "").strip().lower()
            if (
                processing_job_id
                and persisted_status not in {"ready", "failed"}
                and str(asset_for_item.get("asset_kind") or "").strip().lower() == "workspace_cv"
            ):
                try:
                    processing_run = application.get_run(processing_job_id)
                    if processing_run.status == RUN_STATUS_RUNNING and str(asset_metadata.get("status") or "") not in {"ready", "failed"}:
                        asset_metadata["status"] = "processing"
                    elif processing_run.status == RUN_STATUS_QUEUED and str(asset_metadata.get("status") or "") not in {"ready", "failed"}:
                        asset_metadata["status"] = "queued"
                    elif processing_run.status == RUN_STATUS_FAILED and str(asset_metadata.get("status") or "") != "ready":
                        asset_metadata["status"] = "failed"
                    asset_for_item["metadata"] = asset_metadata
                except Exception:
                    pass
            entries.append(_candidate_asset_to_document_item(asset_for_item, workspaces, shared_profile))
    if asset_kind_filter:
        entries = [item for item in entries if str(item.get("asset_kind") or "").lower() == asset_kind_filter]
    entries.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return entries


def _resolve_candidate_asset_download(application, user, asset_id: str) -> tuple[str, str]:
    for asset in _load_candidate_assets(user):
        if asset["asset_id"] != asset_id:
            continue
        materialized_path = _candidate_asset_file_path(application, asset)
        file_path = str(materialized_path or "")
        download_name = str(asset.get("display_name") or Path(file_path).name or asset_id)
        return file_path, download_name
    raise KeyError(f"Candidate asset '{asset_id}' not found.")


def _find_document_entry(application, user, document_id: str) -> dict:
    for item in _collect_document_entries(application, user):
        if str(item.get("document_id") or "") == str(document_id or ""):
            return item
    raise KeyError(f"Document '{document_id}' not found.")


def _document_file_extension(document: dict) -> str:
    for key in ("relative_path", "path", "file_name", "display_name", "document_name", "download_url", "document_id"):
        suffix = Path(str(document.get(key) or "")).suffix.lower()
        if suffix:
            return suffix
    content_type = str(document.get("content_type") or "").strip().lower()
    if content_type == "application/pdf":
        return ".pdf"
    if content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return ".docx"
    if content_type.startswith("text/"):
        return ".txt"
    return ""


def _document_is_application_cv(document: dict) -> bool:
    asset_kind = str(document.get("asset_kind") or "").strip().lower()
    document_type = str(document.get("document_type") or "").strip().lower()
    return bool(str(document.get("run_id") or "").strip() and str(document.get("job_id") or "").strip()) and (
        asset_kind in {"generated_cv", APPLIED_CV_ASSET_KIND}
        or document_type in {"tailored cv", APPLIED_CV_DOCUMENT_TYPE.lower()}
    )


def _document_export_preference_rank(document: dict) -> int:
    extension = _document_file_extension(document)
    if _document_is_application_cv(document):
        return {".pdf": 0, ".docx": 1, ".txt": 2}.get(extension, 3)
    return 0


def _prefer_pdf_application_cv_documents(documents: list[dict]) -> list[dict]:
    preferred_by_key: dict[tuple[str, str, str, str], dict] = {}
    for document in documents:
        if not _document_is_application_cv(document):
            continue
        key = (
            str(document.get("run_id") or ""),
            str(document.get("job_id") or ""),
            str(document.get("asset_kind") or ""),
            str(document.get("document_type") or ""),
        )
        existing = preferred_by_key.get(key)
        if existing is None or _document_export_preference_rank(document) < _document_export_preference_rank(existing):
            preferred_by_key[key] = document
    preferred_ids = {str(item.get("document_id") or "") for item in preferred_by_key.values()}
    result: list[dict] = []
    emitted_preferred: set[tuple[str, str, str, str]] = set()
    for document in documents:
        if not _document_is_application_cv(document):
            result.append(document)
            continue
        key = (
            str(document.get("run_id") or ""),
            str(document.get("job_id") or ""),
            str(document.get("asset_kind") or ""),
            str(document.get("document_type") or ""),
        )
        if key in emitted_preferred:
            continue
        if str(document.get("document_id") or "") in preferred_ids:
            result.append(document)
            emitted_preferred.add(key)
    return result


def _resolve_document_selection(
    application,
    user,
    document_id: str,
    *,
    export_anyway: bool = False,
) -> tuple[str, str]:
    document = _find_document_entry(application, user, document_id)
    _assert_document_export_allowed(document, export_anyway=export_anyway)
    kind, _, remainder = str(document_id or "").partition("::")
    file_path = ""
    fallback_name = ""
    if kind == "artifact":
        run_id, _, artifact_id = remainder.partition("::")
        if not run_id or not artifact_id:
            raise KeyError(f"Document '{document_id}' not found.")
        file_path, fallback_name = _resolve_artifact_download(application, run_id, artifact_id)
    elif kind == "asset":
        file_path, fallback_name = _resolve_candidate_asset_download(application, user, remainder)
    else:
        raise KeyError(f"Document '{document_id}' not found.")

    preferred_name = str(document.get("display_name") or document.get("document_name") or "").strip()
    if not preferred_name:
        return file_path, fallback_name
    fallback_path = Path(fallback_name or "")
    target_path = Path(file_path or "")
    preferred_path = Path(preferred_name).name or fallback_path.name or "document"
    if Path(preferred_path).suffix:
        return file_path, preferred_path
    resolved_suffix = fallback_path.suffix or target_path.suffix
    if resolved_suffix:
        return file_path, f"{preferred_path}{resolved_suffix}"
    return file_path, preferred_path


def _safe_zip_entry_name(original_name: str, *, used_names: set[str]) -> str:
    candidate = Path(original_name or "document").name or "document"
    stem = Path(candidate).stem or "document"
    suffix = Path(candidate).suffix
    counter = 1
    while candidate in used_names:
        candidate = f"{stem}_{counter}{suffix}"
        counter += 1
    used_names.add(candidate)
    return candidate


def _create_bulk_export_bundle(
    application,
    user,
    document_ids: list[str],
    *,
    label: str = "",
    export_anyway: bool = False,
) -> dict:
    if not document_ids:
        raise ValueError("At least one document is required for bulk export.")
    bundle_id = f"bundle_{uuid4().hex[:16]}"
    bundle_path = _candidate_asset_bundle_dir(user) / f"{bundle_id}.zip"
    written_count = 0
    used_names: set[str] = set()
    selected_documents: list[dict] = []
    for document_id in document_ids:
        document = _find_document_entry(application, user, document_id)
        _assert_document_export_allowed(document, export_anyway=export_anyway)
        selected_documents.append(document)
    selected_documents = _prefer_pdf_application_cv_documents(selected_documents)
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for document in selected_documents:
            document_id = str(document.get("document_id") or "")
            file_path, file_name = _resolve_document_selection(
                application,
                user,
                document_id,
                export_anyway=export_anyway,
            )
            target = Path(file_path)
            if not target.exists() or not target.is_file():
                continue
            archive.write(target, arcname=_safe_zip_entry_name(file_name, used_names=used_names))
            written_count += 1
    if written_count == 0:
        try:
            bundle_path.unlink(missing_ok=True)
        except TypeError:
            if bundle_path.exists():
                bundle_path.unlink()
        raise ValueError("None of the selected documents could be exported.")
    bundle_name = f"{label.strip() or 'application_documents'}_{datetime.now(timezone.utc).date().isoformat()}.zip"
    return {
        "bundle_id": bundle_id,
        "file_name": bundle_name,
        "document_count": written_count,
        "download_url": _bulk_export_download_url(bundle_id),
        "path": str(bundle_path.resolve()),
    }


def _rejection_reason_labels() -> dict[str, str]:
    definitions = phase0_contract_catalog()["rejected_job_review"]["reason_definitions"]
    return {str(item["code"]): str(item["label"]) for item in definitions}


def _rejected_focus_for_reason(reason_code: str) -> str:
    mapping = {
        "keyword_mismatch": "targeting",
        "seniority_mismatch": "filters",
        "language_mismatch": "filters",
        "location_mismatch": "targeting",
        "duplicate": "sources",
        "source_validation_failed": "sources",
        "manual_rejection": "review",
        "unknown": "review",
    }
    return mapping.get(str(reason_code or ""), "review")


def _workflow_supports_requeue(application, run) -> bool:
    workflow = application.repositories.workspace_repository.get_workflow_template(run.workflow_template_id)
    return any(
        stage.stage_type == "applications.generate.documents"
        or bool((stage.metadata or {}).get("supports_requeue"))
        for stage in workflow.stages
    )


def _upsert_rejected_review_override(
    application,
    *,
    run_id: str,
    job_id: str,
    reviewer: str,
    reason_summary: str,
    source_stage: str,
    notes: str,
    requeue_run_id: str,
) -> dict:
    existing_review = next(
        (review for review in application.list_reviews(run_id=run_id, limit=1000, offset=0) if review.job_id == job_id),
        None,
    )
    review_metadata = dict(existing_review.metadata or {}) if existing_review else {}
    now_iso = datetime.now(timezone.utc).isoformat()
    review_metadata.update(
        {
            "rejection_override_state": "requested",
            "rejection_override_requested_at": now_iso,
            "rejection_override_requested_by": reviewer,
            "rejection_override_notes": notes,
            "requeue_run_id": requeue_run_id,
            "rejected_source_stage": source_stage,
            "reason_summary": reason_summary,
        }
    )
    review_payload = {
        "job_id": job_id,
        "status": "rejected",
        "decision": "rejected",
        "reviewer": reviewer,
        "notes": reason_summary or notes,
        "metadata": review_metadata,
    }
    review = application.upsert_review(
        run_id=run_id,
        payload=review_payload,
        review_id=existing_review.review_id if existing_review else "",
    )
    return review.to_dict()


def _collect_rejected_job_entries(
    application,
    user,
    *,
    workspace_id: str = "",
    run_id: str = "",
    run_record=None,
    workspace_record=None,
    review_records: list[object] | None = None,
    run_blobs: dict[str, object] | None = None,
    access_checked: bool = False,
) -> list[dict]:
    if run_id:
        run = run_record if str(getattr(run_record, "id", "") or "") == run_id else None
        if run is None:
            try:
                run = application.get_run(run_id)
            except KeyError:
                return []
        if workspace_id and run.workspace_id != workspace_id:
            return []
        if not access_checked and not application.user_can_access_run(user, run):
            return []
        workspace = (
            workspace_record
            if str(getattr(workspace_record, "id", "") or "") == run.workspace_id
            else None
        )
        if workspace is None:
            try:
                workspace = application.get_workspace(run.workspace_id)
            except KeyError:
                workspace = None
        workspaces = {run.workspace_id: workspace} if workspace is not None else {}
        runs = [run]
    else:
        workspaces, runs = _collect_authorized_runs(application, user, workspace_id=workspace_id)
    reviews_by_run = (
        {run_id: review_records}
        if run_id and review_records is not None
        else _load_reviews_by_run(application, runs)
    )
    reason_labels = _rejection_reason_labels()
    entries: list[dict] = []
    requeue_run_cache: dict[str, object | None] = {}
    for run in runs:
        if run_id and run.id != run_id:
            continue
        workspace = workspaces.get(run.workspace_id)
        reviews_by_job = {
            review.job_id: review
            for review in reviews_by_run.get(run.id, [])
        }
        blobs = (
            run_blobs
            if run_id and run_blobs is not None
            else application.repositories.job_store.load_all_blobs(run.id)
        )
        seen_job_ids: set[str] = set()
        for blob_key, value in blobs.items():
            if not isinstance(value, list):
                continue
            blob_key_text = str(blob_key)
            if blob_key_text.endswith("_rejected"):
                source_stage = blob_key_text.removesuffix("_rejected")
            elif blob_key_text.endswith("_dropped_duplicates"):
                source_stage = blob_key_text.removesuffix("_dropped_duplicates")
            else:
                continue
            for payload in value:
                if not isinstance(payload, dict):
                    continue
                job_id = str(payload.get("job_id") or "")
                if not job_id or job_id in seen_job_ids:
                    continue
                seen_job_ids.add(job_id)
                review = reviews_by_job.get(job_id)
                review_meta = dict(review.metadata or {}) if review else {}
                normalized = normalize_rejected_job_review(
                    {
                        "job_id": job_id,
                        "run_id": run.id,
                        "workspace_id": run.workspace_id,
                        "status": "rejected",
                        "reason_summary": str(
                            payload.get("local_filter_reason")
                            or payload.get("stage2_filter_reason")
                            or payload.get("stage3_filter_reason")
                            or payload.get("reason_summary")
                            or payload.get("reason")
                            or payload.get("dedupe_reason")
                            or (review.notes if review else "")
                        ),
                        "details": payload.get("local_filter_reasons")
                        or payload.get("stage2_filter_reasons")
                        or payload.get("stage3_filter_reasons")
                        or payload.get("details")
                        or ([str(payload.get("dedupe_reason"))] if payload.get("dedupe_reason") else [])
                        or [],
                        "source_stage": source_stage,
                        "updated_at": review.updated_at if review else run.updated_at,
                        "apply_link": payload.get("apply_link") or payload.get("link") or payload.get("source_url"),
                        "workspace_editor": f"/workspaces?workspace_id={run.workspace_id}&edit={run.workspace_id}&focus="
                        f"{_rejected_focus_for_reason(review_meta.get('reason_code') or '')}",
                        "override_state": review_meta.get("rejection_override_state"),
                        "override_requested_at": review_meta.get("rejection_override_requested_at"),
                        "override_requested_by": review_meta.get("rejection_override_requested_by"),
                        "override_notes": review_meta.get("rejection_override_notes"),
                        "metadata": review_meta,
                    }
                )
                reason_code = normalized["rejection"]["reason_code"]
                requeue_run_id = str(review_meta.get("requeue_run_id") or "")
                requeue_run = None
                if requeue_run_id:
                    if requeue_run_id not in requeue_run_cache:
                        try:
                            requeue_run_cache[requeue_run_id] = application.get_run(requeue_run_id)
                        except KeyError:
                            requeue_run_cache[requeue_run_id] = None
                    requeue_run = requeue_run_cache.get(requeue_run_id)
                entries.append(
                    {
                        "rejected_id": f"rejected::{run.id}::{job_id}::{source_stage}",
                        "review_id": review.review_id if review else "",
                        "run_id": run.id,
                        "workspace_id": run.workspace_id,
                        "workspace_name": workspace.name if workspace else run.workspace_id,
                        "job_id": job_id,
                        "title": str(payload.get("title") or ""),
                        "company": str(payload.get("company") or ""),
                        "apply_link": str(payload.get("apply_link") or payload.get("link") or payload.get("source_url") or ""),
                        "reason_code": reason_code,
                        "reason_label": reason_labels.get(reason_code, reason_code),
                        "reason_summary": normalized["rejection"]["reason_summary"],
                        "details": list(normalized["rejection"]["details"]),
                        "source_stage": normalized["rejection"]["source_stage"],
                        "recorded_at": normalized["rejection"]["recorded_at"],
                        "override_state": normalized["override"]["state"],
                        "override_requested_at": normalized["override"]["requested_at"],
                        "override_requested_by": normalized["override"]["requested_by"],
                        "override_notes": normalized["override"]["notes"],
                        "requeue_run_id": requeue_run_id,
                        "requeue_run_status": str(getattr(requeue_run, "status", "") or ""),
                        "requeue_run_finished_at": str(getattr(requeue_run, "finished_at", "") or ""),
                        "requeue_run_url": f"/runs/{requeue_run_id}" if requeue_run_id else "",
                        "workspace_editor_url": (
                            f"/workspaces?workspace_id={run.workspace_id}&edit={run.workspace_id}"
                            f"&focus={_rejected_focus_for_reason(reason_code)}"
                        ),
                        "can_requeue": _workflow_supports_requeue(application, run),
                    }
                )
        for review in reviews_by_job.values():
            if review.job_id in seen_job_ids:
                continue
            if review.status != "rejected" and review.decision != "rejected":
                continue
            job_payload = application._find_job_payload(run.id, review.job_id)  # noqa: SLF001
            review_meta = dict(review.metadata or {})
            normalized = normalize_rejected_job_review(
                {
                    "job_id": review.job_id,
                    "run_id": run.id,
                    "workspace_id": run.workspace_id,
                    "status": "rejected",
                    "reason_summary": review.notes,
                    "source_stage": review_meta.get("rejected_source_stage") or "manual_review",
                    "updated_at": review.updated_at,
                    "apply_link": job_payload.get("apply_link") or job_payload.get("link") or job_payload.get("source_url"),
                    "workspace_editor": (
                        f"/workspaces?workspace_id={run.workspace_id}&edit={run.workspace_id}&focus=review"
                    ),
                    "override_state": review_meta.get("rejection_override_state"),
                    "override_requested_at": review_meta.get("rejection_override_requested_at"),
                    "override_requested_by": review_meta.get("rejection_override_requested_by"),
                    "override_notes": review_meta.get("rejection_override_notes"),
                    "metadata": review_meta,
                }
            )
            reason_code = normalized["rejection"]["reason_code"]
            requeue_run_id = str(review_meta.get("requeue_run_id") or "")
            requeue_run = None
            if requeue_run_id:
                if requeue_run_id not in requeue_run_cache:
                    try:
                        requeue_run_cache[requeue_run_id] = application.get_run(requeue_run_id)
                    except KeyError:
                        requeue_run_cache[requeue_run_id] = None
                requeue_run = requeue_run_cache.get(requeue_run_id)
            entries.append(
                {
                    "rejected_id": f"rejected::{run.id}::{review.job_id}::manual_review",
                    "review_id": review.review_id,
                    "run_id": run.id,
                    "workspace_id": run.workspace_id,
                    "workspace_name": workspace.name if workspace else run.workspace_id,
                    "job_id": review.job_id,
                    "title": str(job_payload.get("title") or ""),
                    "company": str(job_payload.get("company") or ""),
                    "apply_link": str(job_payload.get("apply_link") or job_payload.get("link") or job_payload.get("source_url") or ""),
                    "reason_code": reason_code,
                    "reason_label": reason_labels.get(reason_code, reason_code),
                    "reason_summary": normalized["rejection"]["reason_summary"],
                    "details": list(normalized["rejection"]["details"]),
                    "source_stage": normalized["rejection"]["source_stage"],
                    "recorded_at": normalized["rejection"]["recorded_at"],
                    "override_state": normalized["override"]["state"],
                    "override_requested_at": normalized["override"]["requested_at"],
                    "override_requested_by": normalized["override"]["requested_by"],
                    "override_notes": normalized["override"]["notes"],
                    "requeue_run_id": requeue_run_id,
                    "requeue_run_status": str(getattr(requeue_run, "status", "") or ""),
                    "requeue_run_finished_at": str(getattr(requeue_run, "finished_at", "") or ""),
                    "requeue_run_url": f"/runs/{requeue_run_id}" if requeue_run_id else "",
                    "workspace_editor_url": (
                        f"/workspaces?workspace_id={run.workspace_id}&edit={run.workspace_id}&focus=review"
                    ),
                    "can_requeue": _workflow_supports_requeue(application, run),
                }
            )
    entries.sort(key=lambda item: str(item.get("recorded_at") or item.get("override_requested_at") or ""), reverse=True)
    return entries


_DASHBOARD_APPLICATION_OUTCOME_SEGMENTS = [
    {"label": "Applied", "color": "#38bdf8"},
    {"label": "Interviewing", "color": "#f59e0b"},
    {"label": "Offer", "color": "#22c55e"},
    {"label": "Rejected", "color": "#f97316"},
    {"label": "Withdrawn", "color": "#94a3b8"},
]
_DASHBOARD_SOURCE_KIND_COLORS = ["#0f766e", "#14b8a6", "#38bdf8", "#f59e0b", "#f97316"]
_DASHBOARD_ACTIVE_RUN_STATUSES = {"planned", "queued", "running", "cancel_requested"}
_DASHBOARD_TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled"}
_DASHBOARD_REFERRAL_STAGE_INDEX = {
    "Not contacted": 0,
    "Contacted": 1,
    "Replied": 2,
    "Referral offered": 3,
    "No referral": 2,
}
_DASHBOARD_SUBMITTED_APPLICATION_STATUSES = {"Applied", "Interviewing", "Offer", "Rejected", "Withdrawn"}
_DASHBOARD_RESPONSE_APPLICATION_STATUSES = {"Interviewing", "Offer", "Rejected"}
_DASHBOARD_INTERVIEW_APPLICATION_STATUSES = {"Interviewing", "Offer"}


def _dashboard_item_value(item, field: str, default=None):
    if isinstance(item, dict):
        return item.get(field, default)
    return getattr(item, field, default)


def _dashboard_labelize(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "").replace("_", " ").replace("-", " ")).strip()
    return re.sub(r"\b\w", lambda match: match.group(0).upper(), text)


def _dashboard_numeric_value(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        return float(text)
    except Exception:
        return 0.0


def _dashboard_parse_timestamp(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _dashboard_run_duration_ms(run) -> float | None:
    start = (
        _dashboard_parse_timestamp(getattr(run, "started_at", ""))
        or _dashboard_parse_timestamp(getattr(run, "queued_at", ""))
        or _dashboard_parse_timestamp(getattr(run, "created_at", ""))
    )
    end = _dashboard_parse_timestamp(getattr(run, "finished_at", ""))
    if start is None or end is None or end <= start:
        return None
    return (end - start).total_seconds() * 1000


def _dashboard_failed_stage_result(run):
    stage_results = list(getattr(run, "stage_results", []) or [])
    for result in reversed(stage_results):
        status = str(_dashboard_item_value(result, "status", "") or "").strip().lower()
        if status == "failed":
            return result
    return None


def _dashboard_failure_stage_key(run) -> str:
    failed_stage = _dashboard_failed_stage_result(run)
    key = str(
        _dashboard_item_value(failed_stage, "stage_id", "")
        or getattr(run, "current_stage_id", "")
        or "unknown"
    ).strip()
    return key or "unknown"


def _dashboard_failure_message(run) -> str:
    failed_stage = _dashboard_failed_stage_result(run)
    message = str(
        _dashboard_item_value(failed_stage, "error", "")
        or getattr(run, "last_error", "")
        or ""
    ).strip()
    return message or "Run failed without a saved error message."


def _dashboard_is_source_stage(stage_id: str) -> bool:
    return stage_id.startswith("source_") or stage_id == "source_search"


def _dashboard_is_merge_stage(stage_id: str) -> bool:
    return "merge" in stage_id


def _dashboard_is_screen_stage(stage_id: str) -> bool:
    return "screen" in stage_id


def _dashboard_is_approval_stage(stage_id: str) -> bool:
    return "prioritize" in stage_id


def _dashboard_is_apply_stage(stage_id: str) -> bool:
    return "generate" in stage_id or "package" in stage_id


def _dashboard_run_pipeline(run) -> dict[str, float]:
    stage_results = list(getattr(run, "stage_results", []) or [])
    discovered_from_sources = 0.0
    discovered_from_merge = 0.0
    screened = 0.0
    screen_approved = 0.0
    approved = 0.0
    applied = 0.0

    for result in stage_results:
        stage_id = str(_dashboard_item_value(result, "stage_id", "") or "").strip()
        metrics = _dashboard_item_value(result, "metrics", {}) or {}
        jobs_found = _dashboard_numeric_value(_dashboard_item_value(metrics, "jobs_found", 0))
        jobs_ingested = _dashboard_numeric_value(_dashboard_item_value(metrics, "jobs_ingested", 0))
        merged_jobs = _dashboard_numeric_value(_dashboard_item_value(metrics, "merged_jobs", 0))
        approved_jobs = _dashboard_numeric_value(_dashboard_item_value(metrics, "approved", 0))
        rejected_jobs = _dashboard_numeric_value(_dashboard_item_value(metrics, "rejected", 0))
        generated_jobs = _dashboard_numeric_value(_dashboard_item_value(metrics, "generated_jobs", 0))
        packaged_jobs = _dashboard_numeric_value(_dashboard_item_value(metrics, "packaged_jobs", 0))

        if _dashboard_is_source_stage(stage_id):
            discovered_from_sources += jobs_found + jobs_ingested
        if _dashboard_is_merge_stage(stage_id):
            discovered_from_merge = max(discovered_from_merge, merged_jobs)
        if _dashboard_is_screen_stage(stage_id):
            screen_approved += approved_jobs
            screened_total = approved_jobs + rejected_jobs
            screened += screened_total or approved_jobs
        if _dashboard_is_approval_stage(stage_id):
            approved += approved_jobs
        if _dashboard_is_apply_stage(stage_id):
            applied += generated_jobs + packaged_jobs

    return {
        "discovered": discovered_from_merge or discovered_from_sources,
        "screened": screened,
        "approved": approved or screen_approved,
        "applied": applied,
    }


def _dashboard_days_since(value: object, *, now: datetime) -> int:
    timestamp = _dashboard_parse_timestamp(value)
    if timestamp is None:
        return 0
    return max(0, int((now - timestamp).total_seconds() // 86400))


def _dashboard_median(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return round((ordered[middle - 1] + ordered[middle]) / 2)


def _dashboard_job_source_label(job) -> str:
    if job is None:
        return "Unknown source"
    extra_fields = dict(getattr(job, "extra_fields", {}) or {})
    explicit_label = str(
        getattr(job, "source_type", "")
        or extra_fields.get("source_label")
        or extra_fields.get("source_name")
        or extra_fields.get("source_kind")
        or getattr(job, "portal", "")
        or ""
    ).strip()
    if explicit_label:
        return _dashboard_labelize(explicit_label)
    source_url = str(
        getattr(job, "apply_link", "")
        or getattr(job, "link", "")
        or getattr(job, "source_url", "")
        or ""
    ).strip()
    hostname = str(urlparse(source_url).hostname or "").strip().lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]
    return hostname or "Unknown source"


def _dashboard_job_role_label(job) -> str:
    if job is None:
        return "Unknown role"
    role_label = str(
        getattr(job, "role_category_name", "")
        or getattr(job, "title", "")
        or ""
    ).strip()
    return _dashboard_labelize(role_label) if role_label else "Unknown role"


def _dashboard_tracker_items(application, user, runs: list[object]) -> tuple[list[dict], int]:
    history_rows = application.repositories.review_store.list_application_status_history(
        user_id=user.user_id,
        limit=10000,
        offset=0,
    )
    history_by_review: dict[str, list[dict]] = {}
    for history_row in history_rows:
        review_id = str(history_row.get("review_id") or "").strip()
        if review_id:
            history_by_review.setdefault(review_id, []).append(dict(history_row))

    tracker_items: list[dict] = []
    waiting_review_count = 0
    snapshot = _load_run_read_snapshot(
        application,
        runs,
        include_reviews=True,
        preserve_job_sets=False,
        review_jobs_only=True,
    )
    job_sets_by_run = snapshot["job_sets"]
    reviews_by_run = snapshot["reviews"]
    for run in runs:
        jobs_by_id: dict[str, object] = {}
        for jobs in job_sets_by_run.get(run.id, {}).values():
            for job in jobs:
                jobs_by_id[job.job_id] = job
        for review in reviews_by_run.get(run.id, []):
            review_status = str(getattr(review, "status", "") or "").strip().lower()
            if review_status in {"waiting_review", "pending"}:
                waiting_review_count += 1
            review_meta = dict(getattr(review, "metadata", {}) or {})
            raw_tracker_status = str(review_meta.get("tracker_status") or "")
            if getattr(review, "decision", "") != "approved" and not raw_tracker_status:
                continue
            tracker_status = raw_tracker_status or "not_applied"
            application_status = normalize_application_status(
                review_meta.get("application_status") or tracker_status,
                default="Not applied",
            )
            job = jobs_by_id.get(review.job_id)
            tracker_items.append(
                {
                    "id": review.review_id,
                    "applicationStatus": application_status,
                    "applicationDate": str(review_meta.get("application_date") or review_meta.get("applied_at") or ""),
                    "createdAt": str(review.created_at or ""),
                    "updatedAt": str(review.updated_at or ""),
                    "sourceLabel": _dashboard_job_source_label(job),
                    "roleLabel": _dashboard_job_role_label(job),
                    "statusHistory": history_by_review.get(review.review_id, []),
                }
            )

    for external in _load_external_tracker_applications(user):
        application_id = str(external.get("application_id") or external.get("review_id") or "").strip()
        raw_tracker_status = str(external.get("tracker_status") or "")
        application_status = normalize_application_status(
            external.get("application_status") or raw_tracker_status,
            default="Unknown",
        )
        source_label = str(external.get("source_label") or external.get("source") or "Gmail").strip()
        role_label = str(
            external.get("role_category_name")
            or external.get("role")
            or external.get("title")
            or ""
        ).strip()
        tracker_items.append(
            {
                "id": application_id,
                "applicationStatus": application_status,
                "applicationDate": str(external.get("application_date") or ""),
                "createdAt": str(external.get("created_at") or ""),
                "updatedAt": str(external.get("updated_at") or external.get("created_at") or ""),
                "sourceLabel": _dashboard_labelize(source_label) if source_label else "Unknown source",
                "roleLabel": _dashboard_labelize(role_label) if role_label else "Unknown role",
                "statusHistory": history_by_review.get(application_id, []),
            }
        )

    for item in tracker_items:
        history = list(item.get("statusHistory") or [])
        submitted_history = [
            row for row in history if normalize_application_status(row.get("to_status")) in _DASHBOARD_SUBMITTED_APPLICATION_STATUSES
        ]
        response_history = [
            row for row in history if normalize_application_status(row.get("to_status")) in _DASHBOARD_RESPONSE_APPLICATION_STATUSES
        ]
        interview_history = [
            row for row in history if normalize_application_status(row.get("to_status")) in _DASHBOARD_INTERVIEW_APPLICATION_STATUSES
        ]
        offer_history = [
            row for row in history if normalize_application_status(row.get("to_status")) == "Offer"
        ]
        current_status_history = [
            row
            for row in history
            if normalize_application_status(row.get("to_status")) == item["applicationStatus"]
        ]
        fallback_submitted_at = (
            item["applicationDate"]
            or item["updatedAt"]
            if item["applicationStatus"] in _DASHBOARD_SUBMITTED_APPLICATION_STATUSES
            else ""
        )
        item["submittedAt"] = (
            str(submitted_history[0].get("changed_at") or "")
            if submitted_history
            else fallback_submitted_at
        )
        item["responseAt"] = (
            str(response_history[-1].get("changed_at") or "")
            if response_history
            else item["updatedAt"] if item["applicationStatus"] in _DASHBOARD_RESPONSE_APPLICATION_STATUSES else ""
        )
        item["interviewAt"] = (
            str(interview_history[-1].get("changed_at") or "")
            if interview_history
            else item["updatedAt"] if item["applicationStatus"] in _DASHBOARD_INTERVIEW_APPLICATION_STATUSES else ""
        )
        item["offerAt"] = (
            str(offer_history[-1].get("changed_at") or "")
            if offer_history
            else item["updatedAt"] if item["applicationStatus"] == "Offer" else ""
        )
        item["statusChangedAt"] = (
            str(current_status_history[-1].get("changed_at") or "")
            if current_status_history
            else item["updatedAt"] or item["createdAt"]
        )
        item.pop("statusHistory", None)
    return tracker_items, waiting_review_count


def _dashboard_in_period(value: object, *, start: datetime, end: datetime) -> bool:
    timestamp = _dashboard_parse_timestamp(value)
    return timestamp is not None and start <= timestamp < end


def _dashboard_period_summary(
    tracker_items: list[dict],
    outreach_records: list[dict],
    *,
    start: datetime,
    end: datetime,
) -> dict[str, int]:
    return {
        "applications": sum(
            1 for item in tracker_items if _dashboard_in_period(item.get("submittedAt"), start=start, end=end)
        ),
        "responses": sum(
            1 for item in tracker_items if _dashboard_in_period(item.get("responseAt"), start=start, end=end)
        ),
        "interviews": sum(
            1 for item in tracker_items if _dashboard_in_period(item.get("interviewAt"), start=start, end=end)
        ),
        "offers": sum(
            1 for item in tracker_items if _dashboard_in_period(item.get("offerAt"), start=start, end=end)
        ),
        "referralUpdates": sum(
            1 for record in outreach_records if _dashboard_in_period(record.get("updated_at"), start=start, end=end)
        ),
    }


def _dashboard_role_recommendation(
    *,
    label: str,
    applications: int,
    responses: int,
    application_share: float,
    response_rate: float,
    average_response_rate: float,
) -> str:
    if label == "Unknown role":
        return "Needs cleaner data"
    if applications <= 1:
        return "Test more"
    if application_share >= 0.30 and responses == 0:
        return "Reduce effort"
    if applications >= 3 and response_rate < (average_response_rate * 0.5):
        return "Reduce effort"
    if responses > 0 and response_rate >= average_response_rate + 0.10:
        return "Increase focus"
    return "Keep applying"


def _dashboard_role_strategy_summary(roles: list[dict], *, total_applications: int, average_response_rate: float) -> str:
    if not roles or total_applications <= 0:
        return "Role strategy will appear after applications have role labels and outcomes."

    known_roles = [role for role in roles if role["label"] != "Unknown role"]
    comparable_roles = known_roles or roles
    top_volume = max(comparable_roles, key=lambda role: (role["applications"], role["responses"], role["label"]))
    response_roles = [role for role in comparable_roles if role["responses"] > 0]
    best_response = (
        max(response_roles, key=lambda role: (role["responseRate"], role["responses"], role["applications"], role["label"]))
        if response_roles
        else None
    )
    reduce_candidates = [
        role
        for role in comparable_roles
        if role["label"] != "Unknown role"
        and role["applications"] >= 2
        and role["responses"] == 0
        and role["applicationShare"] >= 0.20
    ]
    reduce_role = max(reduce_candidates, key=lambda role: (role["applicationShare"], role["applications"], role["label"])) if reduce_candidates else None

    if len(comparable_roles) == 1:
        only_role = comparable_roles[0]
        if only_role["responses"]:
            return (
                f"{only_role['label']} is the only submitted role target and is producing a "
                f"{round(only_role['responseRate'] * 100)}% response rate. Keep it as the baseline, "
                "then test adjacent roles in small batches."
            )
        return (
            f"{only_role['label']} is the only submitted role target so far and has no employer responses yet. "
            "Keep applications tightly matched and add another role only as a controlled test."
        )

    if best_response and reduce_role and best_response["label"] != reduce_role["label"]:
        return (
            f"{best_response['label']} is producing the strongest response rate at "
            f"{round(best_response['responseRate'] * 100)}%, while {reduce_role['label']} has "
            f"{round(reduce_role['applicationShare'] * 100)}% of applications with no responses. "
            f"Focus the next batch on {best_response['label']} or similar roles and reduce "
            f"{reduce_role['label']} unless the fit is unusually strong."
        )

    if best_response:
        return (
            f"{best_response['label']} is the strongest role target at "
            f"{round(best_response['responseRate'] * 100)}% response rate. "
            f"{top_volume['label']} has the largest application share at "
            f"{round(top_volume['applicationShare'] * 100)}%. Prioritize roles with response rates above "
            f"the overall {round(average_response_rate * 100)}% baseline."
        )

    return (
        f"Applications are spread across {len(comparable_roles)} role targets, but none has employer responses yet. "
        f"{top_volume['label']} has the largest share at {round(top_volume['applicationShare'] * 100)}%; "
        "keep the next batch focused on the strongest-fit role and watch for first responses before expanding."
    )


def _dashboard_role_strategy(tracker_items: list[dict]) -> dict:
    role_map: dict[str, dict] = {}
    for item in tracker_items:
        status = item.get("applicationStatus")
        if status not in _DASHBOARD_SUBMITTED_APPLICATION_STATUSES:
            continue
        label = str(item.get("roleLabel") or "Unknown role").strip() or "Unknown role"
        summary = role_map.setdefault(
            label,
            {
                "label": label,
                "applications": 0,
                "responses": 0,
                "interviews": 0,
                "offers": 0,
                "rejected": 0,
                "withdrawn": 0,
            },
        )
        summary["applications"] += 1
        if status in _DASHBOARD_RESPONSE_APPLICATION_STATUSES:
            summary["responses"] += 1
        if status in _DASHBOARD_INTERVIEW_APPLICATION_STATUSES:
            summary["interviews"] += 1
        if status == "Offer":
            summary["offers"] += 1
        if status == "Rejected":
            summary["rejected"] += 1
        if status == "Withdrawn":
            summary["withdrawn"] += 1

    total_applications = sum(role["applications"] for role in role_map.values())
    total_responses = sum(role["responses"] for role in role_map.values())
    average_response_rate = total_responses / total_applications if total_applications else 0
    roles = []
    for summary in role_map.values():
        applications = int(summary["applications"])
        responses = int(summary["responses"])
        application_share = applications / total_applications if total_applications else 0
        response_rate = responses / applications if applications else 0
        roles.append(
            {
                **summary,
                "applicationShare": application_share,
                "responseRate": response_rate,
                "interviewRate": summary["interviews"] / applications if applications else 0,
                "recommendation": _dashboard_role_recommendation(
                    label=summary["label"],
                    applications=applications,
                    responses=responses,
                    application_share=application_share,
                    response_rate=response_rate,
                    average_response_rate=average_response_rate,
                ),
            }
        )
    roles.sort(
        key=lambda role: (
            -role["offers"],
            -role["interviews"],
            -role["responses"],
            -role["applications"],
            role["label"].casefold(),
        )
    )
    return {
        "summary": _dashboard_role_strategy_summary(
            roles,
            total_applications=total_applications,
            average_response_rate=average_response_rate,
        ),
        "totalApplications": total_applications,
        "averageResponseRate": average_response_rate,
        "roles": roles[:8],
    }


def _dashboard_candidate_insights(
    *,
    tracker_items: list[dict],
    waiting_review_count: int,
    aggregated_pipeline: dict[str, float],
    contacts: list[object],
    outreach_records: list[dict],
) -> dict:
    now = datetime.now(timezone.utc)
    current_period_start = now - timedelta(days=7)
    previous_period_start = now - timedelta(days=14)
    status_counts: dict[str, int] = {}
    for item in tracker_items:
        status = str(item.get("applicationStatus") or "Unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

    aging_definitions = [
        ("Ready to apply", "Not applied", 3, "Submit applications while the roles are still fresh."),
        ("Awaiting response", "Applied", 14, "Follow up where an application has gone quiet."),
        ("Interviewing", "Interviewing", 7, "Keep interview notes and follow-ups current."),
    ]
    pipeline_aging = []
    for label, status, stale_after_days, detail in aging_definitions:
        matching_items = [item for item in tracker_items if item.get("applicationStatus") == status]
        ages = [
            _dashboard_days_since(
                item.get("submittedAt") if status == "Applied" else item.get("statusChangedAt"),
                now=now,
            )
            for item in matching_items
        ]
        pipeline_aging.append(
            {
                "label": label,
                "status": status,
                "count": len(matching_items),
                "staleCount": sum(1 for age in ages if age >= stale_after_days),
                "medianAgeDays": _dashboard_median(ages),
                "staleAfterDays": stale_after_days,
                "detail": detail,
            }
        )

    submitted_count = sum(
        status_counts.get(status, 0) for status in _DASHBOARD_SUBMITTED_APPLICATION_STATUSES
    )
    response_count = sum(
        status_counts.get(status, 0) for status in _DASHBOARD_RESPONSE_APPLICATION_STATUSES
    )
    interview_count = sum(
        status_counts.get(status, 0) for status in _DASHBOARD_INTERVIEW_APPLICATION_STATUSES
    )
    approved_count = status_counts.get("Not applied", 0) + submitted_count
    discovered_count = max(int(aggregated_pipeline.get("discovered") or 0), approved_count)
    funnel_counts = [
        ("Discovered", discovered_count, "#0f766e"),
        ("Approved", approved_count, "#14b8a6"),
        ("Submitted", submitted_count, "#38bdf8"),
        ("Employer responses", response_count, "#f59e0b"),
        ("Interviews", interview_count, "#a855f7"),
        ("Offers", status_counts.get("Offer", 0), "#22c55e"),
    ]
    funnel = []
    previous_value = 0
    for index, (label, value, color) in enumerate(funnel_counts):
        funnel.append(
            {
                "label": label,
                "value": value,
                "color": color,
                "conversionRate": 1 if index == 0 and value else (value / previous_value if previous_value else 0),
            }
        )
        previous_value = value

    source_map: dict[str, dict] = {}
    for item in tracker_items:
        label = str(item.get("sourceLabel") or "Unknown source")
        summary = source_map.setdefault(
            label,
            {
                "label": label,
                "tracked": 0,
                "applied": 0,
                "responses": 0,
                "interviews": 0,
                "offers": 0,
            },
        )
        summary["tracked"] += 1
        status = item.get("applicationStatus")
        if status in _DASHBOARD_SUBMITTED_APPLICATION_STATUSES:
            summary["applied"] += 1
        if status in _DASHBOARD_RESPONSE_APPLICATION_STATUSES:
            summary["responses"] += 1
        if status in _DASHBOARD_INTERVIEW_APPLICATION_STATUSES:
            summary["interviews"] += 1
        if status == "Offer":
            summary["offers"] += 1
    source_effectiveness = []
    for summary in source_map.values():
        source_effectiveness.append(
            {
                **summary,
                "responseRate": summary["responses"] / summary["applied"] if summary["applied"] else 0,
            }
        )
    source_effectiveness.sort(
        key=lambda item: (
            -item["offers"],
            -item["interviews"],
            -item["responses"],
            -item["applied"],
            item["label"].casefold(),
        )
    )
    role_strategy = _dashboard_role_strategy(tracker_items)

    no_source_count = sum(1 for item in tracker_items if item.get("sourceLabel") == "Unknown source")
    missing_application_dates = sum(
        1
        for item in tracker_items
        if item.get("applicationStatus") in _DASHBOARD_SUBMITTED_APPLICATION_STATUSES
        and not _dashboard_parse_timestamp(item.get("applicationDate"))
    )
    unknown_status_count = status_counts.get("Unknown", 0)
    expected_fields = max(1, len(tracker_items) * 2)
    issue_count = unknown_status_count + missing_application_dates + no_source_count
    data_quality = {
        "confidence": round(max(0, 1 - (issue_count / expected_fields)) * 100),
        "issueCount": issue_count,
        "unknownStatuses": unknown_status_count,
        "missingApplicationDates": missing_application_dates,
        "missingSources": no_source_count,
    }

    not_contacted_count = len(contacts) - len(
        {
            str(record.get("contact_id") or "")
            for record in outreach_records
            if str(record.get("contact_id") or "") and record.get("outreach_status") != "Not contacted"
        }
    )
    stale_contacted_count = sum(
        1
        for record in outreach_records
        if record.get("outreach_status") == "Contacted"
        and _dashboard_days_since(record.get("updated_at"), now=now) >= 7
    )
    stale_applied_count = next(
        (item["staleCount"] for item in pipeline_aging if item["status"] == "Applied"),
        0,
    )
    action_candidates = [
        {
            "id": "waiting_reviews",
            "title": "Review discovered jobs",
            "count": waiting_review_count,
            "detail": "Decide which newly discovered jobs should move forward.",
            "priority": "high",
            "icon": "fact_check",
            "to": "/runs",
            "actionLabel": "Review jobs",
        },
        {
            "id": "ready_to_apply",
            "title": "Submit ready applications",
            "count": status_counts.get("Not applied", 0),
            "detail": "Approved jobs are ready for your final application step.",
            "priority": "high",
            "icon": "send",
            "to": "/tracker",
            "actionLabel": "Open tracker",
        },
        {
            "id": "stale_applications",
            "title": "Follow up on quiet applications",
            "count": stale_applied_count,
            "detail": "These applications have waited at least 14 days for a response.",
            "priority": "high",
            "icon": "notification_important",
            "to": "/tracker",
            "actionLabel": "Review follow-ups",
        },
        {
            "id": "interviews",
            "title": "Keep interviews moving",
            "count": status_counts.get("Interviewing", 0),
            "detail": "Review interview notes, scheduling, and next follow-ups.",
            "priority": "medium",
            "icon": "calendar_month",
            "to": "/tracker",
            "actionLabel": "View interviews",
        },
        {
            "id": "referral_outreach",
            "title": "Contact saved referral candidates",
            "count": max(0, not_contacted_count),
            "detail": "Saved contacts are still waiting for a first message.",
            "priority": "medium",
            "icon": "outgoing_mail",
            "to": "/referrals",
            "actionLabel": "Open referrals",
        },
        {
            "id": "referral_follow_up",
            "title": "Follow up with referral contacts",
            "count": stale_contacted_count,
            "detail": "These contacts were messaged at least seven days ago.",
            "priority": "medium",
            "icon": "mark_email_unread",
            "to": "/referrals",
            "actionLabel": "Review outreach",
        },
        {
            "id": "data_cleanup",
            "title": "Improve dashboard accuracy",
            "count": issue_count,
            "detail": "Resolve unknown statuses, dates, or source attribution.",
            "priority": "low",
            "icon": "rule",
            "to": "/tracker",
            "actionLabel": "Clean up tracker",
        },
    ]
    action_plan = [item for item in action_candidates if item["count"] > 0][:6]
    if not action_plan:
        action_plan = [
            {
                "id": "caught_up",
                "title": "You are caught up",
                "count": 0,
                "detail": "No dashboard action currently needs your attention.",
                "priority": "low",
                "icon": "task_alt",
                "to": "/tracker",
                "actionLabel": "Open tracker",
            }
        ]

    return {
        "actionPlan": action_plan,
        "funnel": {"stages": funnel},
        "pipelineAging": pipeline_aging,
        "roleStrategy": role_strategy,
        "sourceEffectiveness": source_effectiveness[:6],
        "weeklySummary": {
            "windowDays": 7,
            "current": _dashboard_period_summary(
                tracker_items,
                outreach_records,
                start=current_period_start,
                end=now,
            ),
            "previous": _dashboard_period_summary(
                tracker_items,
                outreach_records,
                start=previous_period_start,
                end=current_period_start,
            ),
        },
        "dataQuality": data_quality,
    }


def _dashboard_analytics_payload(application, user, workspaces: dict[str, object], runs: list[object]) -> dict:
    terminal_runs = [
        run for run in runs if str(getattr(run, "status", "") or "").strip() in _DASHBOARD_TERMINAL_RUN_STATUSES
    ]
    completed_runs = [
        run for run in terminal_runs if str(getattr(run, "status", "") or "").strip() == "completed"
    ]
    failed_runs = [run for run in runs if str(getattr(run, "status", "") or "").strip() == "failed"]
    active_runs = [
        run for run in runs if str(getattr(run, "status", "") or "").strip() in _DASHBOARD_ACTIVE_RUN_STATUSES
    ]
    run_durations = [value for value in (_dashboard_run_duration_ms(run) for run in terminal_runs) if value is not None]

    failure_breakdown_map: dict[str, int] = {}
    for run in failed_runs:
        key = _dashboard_labelize(_dashboard_failure_stage_key(run))
        failure_breakdown_map[key] = failure_breakdown_map.get(key, 0) + 1
    failure_breakdown = [
        {"stage": stage, "count": count}
        for stage, count in sorted(failure_breakdown_map.items(), key=lambda item: (-item[1], item[0]))
    ]

    aggregated_pipeline = {"discovered": 0.0, "screened": 0.0, "approved": 0.0, "applied": 0.0}
    tracker_items, waiting_review_count = _dashboard_tracker_items(application, user, runs)
    application_status_map: dict[str, int] = {}
    for run in runs:
        pipeline = _dashboard_run_pipeline(run)
        for key, value in pipeline.items():
            aggregated_pipeline[key] += value

    for tracker_item in tracker_items:
        application_status = str(tracker_item.get("applicationStatus") or "Unknown")
        application_status_map[application_status] = application_status_map.get(application_status, 0) + 1

    pipeline_data = [
        {"label": "Discovered", "value": int(aggregated_pipeline["discovered"]), "color": "#0f766e"},
        {"label": "Screened", "value": int(aggregated_pipeline["screened"]), "color": "#14b8a6"},
        {"label": "Approved", "value": int(aggregated_pipeline["approved"]), "color": "#38bdf8"},
        {"label": "Applied", "value": int(aggregated_pipeline["applied"]), "color": "#f59e0b"},
    ]
    application_outcomes = [
        {
            **segment,
            "value": application_status_map.get(segment["label"], 0),
        }
        for segment in _DASHBOARD_APPLICATION_OUTCOME_SEGMENTS
    ]

    contacts = _referral_contacts_from_user(user)
    source_kind_map: dict[str, int] = {}
    for contact in contacts:
        source_kind = _dashboard_labelize(str(getattr(contact, "source_kind", "manual") or "manual").strip() or "manual")
        source_kind_map[source_kind] = source_kind_map.get(source_kind, 0) + 1
    contact_sources = [
        {
            "label": label,
            "value": value,
            "color": _DASHBOARD_SOURCE_KIND_COLORS[index % len(_DASHBOARD_SOURCE_KIND_COLORS)],
        }
        for index, (label, value) in enumerate(
            sorted(source_kind_map.items(), key=lambda item: (-item[1], item[0]))
        )
    ]

    highest_referral_stage_by_contact = {
        str(getattr(contact, "contact_id", "") or "").strip(): 0
        for contact in contacts
        if str(getattr(contact, "contact_id", "") or "").strip()
    }
    no_referral_contacts: set[str] = set()
    outreach_records = _load_referral_outreach_records(user)
    for record in outreach_records:
        contact_id = str(record.get("contact_id") or "").strip()
        if not contact_id or contact_id not in highest_referral_stage_by_contact:
            continue
        outreach_status = normalize_referral_outreach_status(record.get("outreach_status"))
        stage_index = _DASHBOARD_REFERRAL_STAGE_INDEX.get(outreach_status, 0)
        if outreach_status == "No referral":
            no_referral_contacts.add(contact_id)
        highest_referral_stage_by_contact[contact_id] = max(
            highest_referral_stage_by_contact.get(contact_id, 0),
            stage_index,
        )

    contact_stage_indexes = list(highest_referral_stage_by_contact.values())
    outreach_funnel = [
        {
            "label": "Not contacted",
            "value": sum(1 for stage_index in contact_stage_indexes if stage_index == 0),
            "color": "#94a3b8",
        },
        {
            "label": "Contacted",
            "value": sum(1 for stage_index in contact_stage_indexes if stage_index >= 1),
            "color": "#38bdf8",
        },
        {
            "label": "Replied",
            "value": sum(1 for stage_index in contact_stage_indexes if stage_index >= 2),
            "color": "#14b8a6",
        },
        {
            "label": "Referral offered",
            "value": sum(1 for stage_index in contact_stage_indexes if stage_index >= 3),
            "color": "#22c55e",
        },
    ]

    recent_failures = []
    for run in sorted(
        failed_runs,
        key=lambda item: str(item.finished_at or item.updated_at or item.created_at or ""),
        reverse=True,
    )[:5]:
        workspace = workspaces.get(run.workspace_id)
        recent_failures.append(
            {
                "id": run.id,
                "workspaceName": workspace.name if workspace else run.workspace_id,
                "timestamp": run.finished_at or run.updated_at or run.created_at or "",
                "stage": _dashboard_labelize(_dashboard_failure_stage_key(run)),
                "errorText": _dashboard_failure_message(run),
            }
        )

    average_duration_ms = (sum(run_durations) / len(run_durations)) if run_durations else 0
    candidate_insights = _dashboard_candidate_insights(
        tracker_items=tracker_items,
        waiting_review_count=waiting_review_count,
        aggregated_pipeline=aggregated_pipeline,
        contacts=contacts,
        outreach_records=outreach_records,
    )
    return {
        "waitingReviewCount": waiting_review_count,
        "automation": {
            "totalRuns": len(runs),
            "terminalRuns": len(terminal_runs),
            "completedRuns": len(completed_runs),
            "failedRuns": len(failed_runs),
            "activeRuns": len(active_runs),
            "successRate": (len(completed_runs) / len(terminal_runs)) if terminal_runs else 0,
            "averageDurationMs": average_duration_ms,
            "failureBreakdown": failure_breakdown,
        },
        "pipeline": {"data": pipeline_data},
        "outcomes": {
            "total": sum(segment["value"] for segment in application_outcomes),
            "unknown": application_status_map.get("Unknown", 0),
            "trackerTotal": len(tracker_items),
            "submittedTotal": sum(
                application_status_map.get(status, 0) for status in _DASHBOARD_SUBMITTED_APPLICATION_STATUSES
            ),
            "segments": application_outcomes,
        },
        "referrals": {
            "totalContacts": len(contacts),
            "noReferralCount": len(no_referral_contacts),
            "trackedOutreachItems": len(outreach_records),
            "contactSources": contact_sources,
            "outreachFunnel": outreach_funnel,
        },
        "recentFailures": recent_failures,
        "candidateInsights": candidate_insights,
    }


def _empty_dashboard_analytics() -> dict:
    return {
        "outcomes": {
            "total": 0,
            "unknown": 0,
            "trackerTotal": 0,
            "submittedTotal": 0,
            "segments": [{**segment, "value": 0} for segment in _DASHBOARD_APPLICATION_OUTCOME_SEGMENTS],
        },
        "referrals": {
            "totalContacts": 0,
            "noReferralCount": 0,
            "trackedOutreachItems": 0,
            "contactSources": [],
            "outreachFunnel": [
                {"label": "Not contacted", "value": 0, "color": "#94a3b8"},
                {"label": "Contacted", "value": 0, "color": "#38bdf8"},
                {"label": "Replied", "value": 0, "color": "#14b8a6"},
                {"label": "Referral offered", "value": 0, "color": "#22c55e"},
            ],
        },
        "candidateInsights": {
            "actionPlan": [],
            "funnel": {"stages": []},
            "pipelineAging": [],
            "roleStrategy": {
                "summary": "",
                "totalApplications": 0,
                "averageResponseRate": 0,
                "roles": [],
            },
            "sourceEffectiveness": [],
            "weeklySummary": {
                "windowDays": 7,
                "current": {},
                "previous": {},
            },
            "dataQuality": {
                "confidence": 100,
                "issueCount": 0,
                "unknownStatuses": 0,
                "missingApplicationDates": 0,
                "missingSources": 0,
            },
        },
    }


def _dashboard_payload(application, user, *, mode: str = "") -> dict:
    workspaces, runs = _collect_authorized_runs(application, user)
    summary_only = str(mode or "").strip().lower() == "summary"
    analytics = (
        {"waitingReviewCount": 0, **_empty_dashboard_analytics()}
        if summary_only
        else _dashboard_analytics_payload(application, user, workspaces, runs)
    )
    running_workers = 0
    if not summary_only:
        running_workers = len(application.list_workers(limit=100, offset=0, status="running"))
    today_iso = datetime.now(timezone.utc).date().isoformat()
    completed_today = sum(
        1
        for run in runs
        if run.status == "completed" and str(run.finished_at or run.updated_at).startswith(today_iso)
    )
    recent_runs = []
    for run in sorted(runs, key=lambda item: str(item.updated_at or item.created_at), reverse=True)[:10]:
        workspace = workspaces.get(run.workspace_id)
        current_stage = run.current_stage_id or (run.stage_results[-1].stage_id if run.stage_results else "")
        recent_runs.append(
            {
                "id": run.id,
                "workspace_id": run.workspace_id,
                "workspace_name": workspace.name if workspace else run.workspace_id,
                "status": run.status,
                "current_stage": current_stage or "not_started",
                "attempt_count": run.attempt_count,
                "max_attempts": run.max_attempts,
                "updated_at": run.updated_at,
            }
        )
    return {
        "cards": [
            {"label": "Queued Runs", "value": sum(1 for run in runs if run.status == "queued")},
            {"label": "Running Workers", "value": running_workers},
            {
                "label": "Jobs Waiting Review",
                "value": analytics["waitingReviewCount"],
            },
            {"label": "Completed Today", "value": completed_today},
        ],
        "recent_runs": recent_runs,
        "analytics": {key: value for key, value in analytics.items() if key != "waitingReviewCount"},
        "meta": {
            "mode": "summary" if summary_only else "full",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def _current_period_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _quota_limit_for_user(plan_id: str, quota_type: str, quota_overrides: dict[str, object] | None = None) -> int:
    if str(os.getenv("RUNR_DISABLE_QUOTAS") or "").strip().lower() in {"1", "true", "yes", "on"}:
        return -1
    if isinstance(quota_overrides, dict) and quota_type in quota_overrides:
        try:
            return int(quota_overrides[quota_type])
        except (TypeError, ValueError):
            pass
    return int(get_quota(plan_id, quota_type))


def _auth_repository(application):
    return application.repositories.auth_repository


def _resolve_user_clerk_user_id(application, user) -> str:
    lookup = getattr(_auth_repository(application), "get_user_clerk_user_id", None)
    if callable(lookup):
        try:
            return str(lookup(user.user_id) or "").strip()
        except KeyError:
            return ""
    return ""


def _lookup_subscription_record(application, user_id: str) -> dict[str, object] | None:
    lookup = getattr(_auth_repository(application), "get_current_subscription_by_user_id", None)
    if not callable(lookup):
        return None
    try:
        record = lookup(user_id)
    except KeyError:
        return None
    return dict(record or {})


def _serialize_authenticated_user(
    application,
    user,
    *,
    auth_method: str,
    clerk_user_id: str = "",
    role: str = "user",
    plan_id: str = DEFAULT_PLAN_ID,
    quota_overrides: dict[str, object] | None = None,
) -> dict[str, object]:
    payload = user.to_dict()
    payload["display_name"] = _public_user_display_name(user)
    payload["email"] = _public_user_email(user)
    public_metadata = {
        "role": normalize_clerk_role(role),
        "plan_id": normalize_plan_id(plan_id),
        "quota_overrides": dict(quota_overrides or {}),
    }
    payload["role"] = public_metadata["role"]
    payload["plan_id"] = public_metadata["plan_id"]
    payload["clerk_user_id"] = str(clerk_user_id or _resolve_user_clerk_user_id(application, user) or "").strip()
    payload["publicMetadata"] = public_metadata
    payload["auth_method"] = str(auth_method or "").strip()
    return payload


def _lookup_user_by_email(application, email_address: str):
    normalized_email = str(email_address or "").strip()
    if not normalized_email:
        raise KeyError("Missing user email address.")
    repository = _auth_repository(application)
    lookup = getattr(repository, "get_user_by_email", None)
    if not callable(lookup):
        raise KeyError("The configured auth repository does not support email lookups.")
    return lookup(normalized_email)


def _claim_string(raw_claims: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = raw_claims.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                return normalized
        elif isinstance(value, (int, float)):
            return str(value)
    return ""


def _claim_display_name(raw_claims: dict[str, Any], email_address: str) -> str:
    explicit_name = _claim_string(raw_claims, "name", "full_name", "fullName", "username", "preferred_username")
    if explicit_name:
        return explicit_name
    first_name = _claim_string(raw_claims, "given_name", "first_name", "firstName")
    last_name = _claim_string(raw_claims, "family_name", "last_name", "lastName")
    joined_name = " ".join(part for part in (first_name, last_name) if part).strip()
    if joined_name:
        return joined_name
    if "@" in email_address:
        return email_address.split("@", 1)[0].strip()
    return ""


def _claim_email_address(raw_claims: dict[str, Any], clerk_user_id: str) -> str:
    explicit_email = _claim_string(raw_claims, "email", "email_address", "primary_email_address")
    if explicit_email:
        return explicit_email
    email_addresses = raw_claims.get("email_addresses")
    if isinstance(email_addresses, list):
        for item in email_addresses:
            if isinstance(item, str) and item.strip():
                return item.strip()
            if isinstance(item, dict):
                candidate = _claim_string(item, "email_address", "emailAddress")
                if candidate:
                    return candidate
    return ""


def _provision_user_from_clerk_claims(application, claims) -> UserRecord:
    normalized_clerk_user_id = str(getattr(claims, "clerk_user_id", "") or "").strip()
    if not normalized_clerk_user_id:
        raise KeyError("Missing Clerk user identifier.")
    raw_claims = dict(getattr(claims, "raw_claims", {}) or {})
    email_address = _claim_email_address(raw_claims, normalized_clerk_user_id)
    display_name = _claim_display_name(raw_claims, email_address)
    role_value = ROLE_ADMIN if normalize_clerk_role(getattr(claims, "role", "user")) == "admin" else "user"
    try:
        user = _lookup_user_by_email(application, email_address) if email_address else None
    except KeyError:
        user = None
    if user is None:
        user = UserRecord(
            user_id=normalized_clerk_user_id,
            email=email_address,
            display_name=display_name,
            role=role_value,
            created_at=utc_plus_seconds(0),
            updated_at=utc_plus_seconds(0),
            metadata={"provisioned_from": "clerk_session_claims"},
        )
    else:
        user.email = email_address or user.email
        user.display_name = display_name or user.display_name
        user.role = role_value
        user.is_active = True
        user.updated_at = datetime.now(timezone.utc).isoformat()
        user.metadata = {
            **(user.metadata or {}),
            "provisioned_from": "clerk_session_claims",
        }
    repository = _auth_repository(application)
    repository.upsert_user(user)
    set_clerk_id = getattr(repository, "set_user_clerk_user_id", None)
    if callable(set_clerk_id):
        set_clerk_id(user.user_id, normalized_clerk_user_id)
    refreshed_user = application.get_user(user.user_id)
    refreshed_user.role = role_value
    return refreshed_user


def _provision_user_from_clerk(application, clerk_user_id: str):
    normalized_clerk_user_id = str(clerk_user_id or "").strip()
    if not normalized_clerk_user_id:
        raise KeyError("Missing Clerk user identifier.")
    clerk_user_payload = get_clerk_user(normalized_clerk_user_id)
    email_address = get_clerk_primary_email_address(clerk_user_payload)
    display_name = get_clerk_display_name(clerk_user_payload)
    public_metadata = _ensure_clerk_plan_defaults(
        normalized_clerk_user_id,
        dict(
            clerk_user_payload.get("public_metadata")
            or clerk_user_payload.get("publicMetadata")
            or {}
        ),
    )
    role_value = ROLE_ADMIN if public_metadata["role"] == "admin" else "user"
    try:
        user = _lookup_user_by_email(application, email_address) if email_address else None
    except KeyError:
        user = None
    if user is None:
        user = UserRecord(
            user_id=normalized_clerk_user_id,
            email=email_address,
            display_name=display_name,
            role=role_value,
            created_at=utc_plus_seconds(0),
            updated_at=utc_plus_seconds(0),
            metadata={},
        )
    else:
        user.email = email_address or user.email
        user.display_name = display_name or user.display_name
        user.role = role_value
        user.is_active = True
        user.updated_at = datetime.now(timezone.utc).isoformat()
    repository = _auth_repository(application)
    repository.upsert_user(user)
    set_clerk_id = getattr(repository, "set_user_clerk_user_id", None)
    if callable(set_clerk_id):
        set_clerk_id(user.user_id, normalized_clerk_user_id)
    refreshed_user = application.get_user(user.user_id)
    refreshed_user.role = role_value
    return refreshed_user


def _lookup_user_by_clerk_subject(application, clerk_user_id: str, *, claims=None):
    normalized_clerk_user_id = str(clerk_user_id or "").strip()
    if not normalized_clerk_user_id:
        raise KeyError("Missing Clerk user identifier.")
    repository = _auth_repository(application)
    lookup = getattr(repository, "get_user_by_clerk_user_id", None)
    if callable(lookup):
        try:
            return lookup(normalized_clerk_user_id)
        except KeyError:
            pass
    try:
        return application.get_user(normalized_clerk_user_id)
    except KeyError as exc:
        try:
            return _provision_user_from_clerk(application, normalized_clerk_user_id)
        except Exception as provision_exc:
            if claims is not None:
                try:
                    return _provision_user_from_clerk_claims(application, claims)
                except Exception:
                    pass
            raise KeyError(f"User for Clerk subject '{normalized_clerk_user_id}' not found.") from provision_exc


def _build_clerk_auth_context(application, token_value: str):
    claims = verify_session_token(token_value)
    user = _lookup_user_by_clerk_subject(application, claims.clerk_user_id, claims=claims)
    plan_id = normalize_plan_id(claims.plan_id or DEFAULT_PLAN_ID)
    role = normalize_clerk_role(claims.role or user.role)
    user.role = role
    synthetic_token = build_synthetic_token(
        user_id=user.user_id,
        auth_method="clerk_jwt",
        role=role,
        session_id=claims.session_id,
        expires_at=claims.expires_at,
        metadata={
            "clerk_user_id": claims.clerk_user_id,
            "plan_id": plan_id,
        },
    )
    return SimpleNamespace(
        user=user,
        token=synthetic_token,
        auth_method="clerk_jwt",
        clerk_user_id=claims.clerk_user_id,
        role=role,
        plan_id=plan_id,
        quota_overrides=dict(claims.quota_overrides or {}),
        session_id=claims.session_id,
        authorized_party=str(getattr(claims, "authorized_party", "") or ""),
    )


def _build_legacy_auth_context(application, token_value: str):
    user, legacy_token = application.authenticate_access_token(token_value)
    subscription_record = _lookup_subscription_record(application, user.user_id) or {}
    plan_id = normalize_plan_id(subscription_record.get("plan_id") or DEFAULT_PLAN_ID)
    role = normalize_clerk_role(user.role)
    return SimpleNamespace(
        user=user,
        token=legacy_token,
        auth_method="api_token",
        clerk_user_id=_resolve_user_clerk_user_id(application, user),
        role=role,
        plan_id=plan_id,
        quota_overrides={},
        session_id="",
    )


def _decode_jwt_payload_unverified(token_value: str) -> dict[str, Any]:
    parts = str(token_value or "").split(".")
    if len(parts) != 3:
        return {}
    try:
        payload_segment = parts[1]
        padding_length = (-len(payload_segment)) % 4
        decoded = base64.urlsafe_b64decode(f"{payload_segment}{'=' * padding_length}").decode("utf-8")
        payload = json.loads(decoded or "{}")
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _token_looks_like_clerk_jwt(token_value: str) -> bool:
    claims = _decode_jwt_payload_unverified(token_value)
    if not claims:
        return False
    issuer = str(claims.get("iss") or "").strip().lower()
    subject = str(claims.get("sub") or "").strip()
    session_id = str(claims.get("sid") or "").strip()
    return (
        "clerk" in issuer
        or subject.startswith("user_")
        or bool(session_id and claims.get("exp"))
    )


def _auth_context_cache_key(token_value: str) -> str:
    return sha256(str(token_value or "").encode("utf-8")).hexdigest()


def _auth_context_cache_expiry(token_value: str, *, now: float | None = None) -> float:
    timestamp = time.time() if now is None else float(now)
    expires_at = 0.0
    claims = _decode_jwt_payload_unverified(token_value)
    try:
        expires_at = float(claims.get("exp") or 0.0)
    except (TypeError, ValueError):
        expires_at = 0.0
    ttl_expiry = timestamp + _AUTH_CONTEXT_CACHE_TTL_SECONDS
    if expires_at:
        return max(timestamp, min(ttl_expiry, expires_at - 5))
    return ttl_expiry


def _prune_auth_context_cache(now: float) -> None:
    expired_keys = [
        cache_key
        for cache_key, (expires_at, _context) in _AUTH_CONTEXT_CACHE.items()
        if expires_at <= now
    ]
    for cache_key in expired_keys:
        _AUTH_CONTEXT_CACHE.pop(cache_key, None)
    overflow_count = len(_AUTH_CONTEXT_CACHE) - _AUTH_CONTEXT_CACHE_MAX_ENTRIES
    if overflow_count <= 0:
        return
    for cache_key, _value in sorted(_AUTH_CONTEXT_CACHE.items(), key=lambda item: item[1][0])[:overflow_count]:
        _AUTH_CONTEXT_CACHE.pop(cache_key, None)


def _get_cached_auth_context(token_value: str) -> SimpleNamespace | None:
    now = time.time()
    cache_key = _auth_context_cache_key(token_value)
    with _AUTH_CONTEXT_CACHE_LOCK:
        cached = _AUTH_CONTEXT_CACHE.get(cache_key)
        if cached is None:
            return None
        expires_at, context = cached
        if expires_at <= now:
            _AUTH_CONTEXT_CACHE.pop(cache_key, None)
            return None
        return deepcopy(context)


def _store_cached_auth_context(token_value: str, context: SimpleNamespace) -> None:
    now = time.time()
    expires_at = _auth_context_cache_expiry(token_value, now=now)
    if expires_at <= now:
        return
    cache_key = _auth_context_cache_key(token_value)
    with _AUTH_CONTEXT_CACHE_LOCK:
        _prune_auth_context_cache(now)
        _AUTH_CONTEXT_CACHE[cache_key] = (expires_at, deepcopy(context))


def _clear_auth_context_cache() -> None:
    with _AUTH_CONTEXT_CACHE_LOCK:
        _AUTH_CONTEXT_CACHE.clear()


def _log_auth_resolution_timing(
    *,
    token_shape: str,
    outcome: str,
    auth_method: str = "",
    duration_ms: float,
    fallback_attempted: bool = False,
    error_type: str = "",
    cache_hit: bool = False,
) -> None:
    logging.getLogger("backend.auth").info(
        json.dumps(
            {
                "event": "auth_resolution_timing",
                "token_shape": token_shape,
                "outcome": outcome,
                "auth_method": auth_method,
                "duration_ms": round(float(duration_ms or 0), 2),
                "fallback_attempted": bool(fallback_attempted),
                "error_type": str(error_type or ""),
                "cache_hit": bool(cache_hit),
            },
            separators=(",", ":"),
        )
    )


def _resolve_auth_context(application, token_value: str):
    normalized_token = str(token_value or "").strip()
    if not normalized_token:
        raise PermissionError("Missing bearer token.")
    auth_logger = logging.getLogger("backend.auth")
    if normalized_token.count(".") == 2:
        started_at = perf_counter()
        clerk_like_jwt = _token_looks_like_clerk_jwt(normalized_token)
        if clerk_like_jwt:
            cached_context = _get_cached_auth_context(normalized_token)
            if cached_context is not None:
                _log_auth_resolution_timing(
                    token_shape="jwt",
                    outcome="success",
                    auth_method="clerk_jwt",
                    duration_ms=(perf_counter() - started_at) * 1000,
                    cache_hit=True,
                )
                return cached_context
        try:
            context = _build_clerk_auth_context(application, normalized_token)
            if clerk_like_jwt:
                _store_cached_auth_context(normalized_token, context)
            _log_auth_resolution_timing(
                token_shape="jwt",
                outcome="success",
                auth_method="clerk_jwt",
                duration_ms=(perf_counter() - started_at) * 1000,
            )
            return context
        except Exception as clerk_exc:
            if clerk_like_jwt:
                _log_auth_resolution_timing(
                    token_shape="jwt",
                    outcome="failed",
                    auth_method="clerk_jwt",
                    duration_ms=(perf_counter() - started_at) * 1000,
                    fallback_attempted=False,
                    error_type=type(clerk_exc).__name__,
                )
                raise PermissionError(str(clerk_exc)) from clerk_exc
            try:
                legacy_context = _build_legacy_auth_context(application, normalized_token)
            except Exception:
                _log_auth_resolution_timing(
                    token_shape="jwt",
                    outcome="failed",
                    auth_method="legacy_api_token",
                    duration_ms=(perf_counter() - started_at) * 1000,
                    fallback_attempted=True,
                    error_type=type(clerk_exc).__name__,
                )
                raise PermissionError(str(clerk_exc)) from clerk_exc
            auth_logger.warning(
                "Accepted legacy api_token fallback for %s while Clerk JWT verification failed: %s",
                legacy_context.user.user_id,
                clerk_exc,
            )
            _log_auth_resolution_timing(
                token_shape="jwt",
                outcome="success",
                auth_method="legacy_api_token",
                duration_ms=(perf_counter() - started_at) * 1000,
                fallback_attempted=True,
            )
            return legacy_context

    started_at = perf_counter()
    legacy_context = _build_legacy_auth_context(application, normalized_token)
    auth_logger.warning(
        "Accepted legacy api_token fallback for %s during Clerk migration window.",
        legacy_context.user.user_id,
    )
    _log_auth_resolution_timing(
        token_shape="opaque",
        outcome="success",
        auth_method="legacy_api_token",
        duration_ms=(perf_counter() - started_at) * 1000,
    )
    return legacy_context


def _quota_usage_snapshot(
    application,
    *,
    user_id: str,
    plan_id: str,
    quota_overrides: dict[str, object] | None = None,
) -> dict[str, object]:
    repository = _auth_repository(application)
    list_quota_usage = getattr(repository, "list_quota_usage", None)
    if not callable(list_quota_usage):
        raise ValueError("The configured auth repository does not support quota usage persistence.")
    period = _current_period_key()
    usage_counts = dict(list_quota_usage(user_id, period) or {})
    quotas: dict[str, dict[str, object]] = {}
    for quota_type in get_plan(plan_id).get("quotas", {}).keys():
        limit = _quota_limit_for_user(plan_id, quota_type, quota_overrides)
        used = int(usage_counts.get(quota_type) or 0)
        quotas[quota_type] = {
            "used": used,
            "limit": limit,
            "remaining": -1 if limit == -1 else max(0, limit - used),
            "is_unlimited": limit == -1,
        }
    return {
        "period": period,
        "quotas": quotas,
    }


def _subscription_response_payload(
    application,
    *,
    user_id: str,
    plan_id: str,
    quota_overrides: dict[str, object] | None = None,
) -> dict[str, object]:
    subscription_record = _lookup_subscription_record(application, user_id) or {}
    normalized_plan_id = normalize_plan_id(subscription_record.get("plan_id") or plan_id)
    return {
        "plan_id": normalized_plan_id,
        "plan": get_plan(normalized_plan_id),
        "subscription": {
            "subscription_id": str(subscription_record.get("subscription_id") or ""),
            "status": str(
                subscription_record.get("status") or ("active" if normalized_plan_id != DEFAULT_PLAN_ID else "inactive")
            ),
            "billing_provider": str(subscription_record.get("billing_provider") or "creem"),
            "creem_subscription_id": str(subscription_record.get("creem_subscription_id") or ""),
            "creem_customer_id": str(subscription_record.get("creem_customer_id") or ""),
            "current_period_start": str(subscription_record.get("current_period_start") or ""),
            "current_period_end": str(subscription_record.get("current_period_end") or ""),
            "cancelled_at": str(subscription_record.get("cancelled_at") or ""),
        },
        "usage": _quota_usage_snapshot(
            application,
            user_id=user_id,
            plan_id=normalized_plan_id,
            quota_overrides=quota_overrides,
        ),
        "scrapeops_usage": application.get_scrapeops_user_usage_summary(
            user_id=user_id,
            plan_id=normalized_plan_id,
            quota_overrides=quota_overrides,
        ),
    }


def _configured_paid_plan_product_ids() -> list[str]:
    product_ids: list[str] = []
    for plan_id in PLANS:
        plan = get_plan(plan_id)
        if int(plan.get("price_eur") or 0) <= 0:
            continue
        product_id = str(plan.get("creem_product_id") or "").strip()
        if product_id and product_id not in product_ids:
            product_ids.append(product_id)
    return product_ids


def _configured_paid_plan_labels() -> str:
    labels: list[str] = []
    for plan_id, plan in PLANS.items():
        if int(plan.get("price_eur") or 0) <= 0:
            continue
        label = str(plan.get("display_name") or plan_id).strip() or plan_id
        if label not in labels:
            labels.append(label)
    return ", ".join(labels) if labels else "Paid plans"


def _normalize_promo_code(value: Any) -> str:
    normalized = str(value or "").strip().upper()
    if not normalized:
        raise ValueError("promo code is required")
    if not _PROMO_CODE_PATTERN.fullmatch(normalized):
        raise ValueError("promo code must be 3-256 characters of uppercase letters and numbers only")
    return normalized


def _parse_optional_iso_datetime(value: Any, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid ISO 8601 date-time.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _parse_promo_discount_amount(amount_type: str, raw_amount: Any) -> int:
    normalized_type = str(amount_type or "").strip().lower()
    if normalized_type not in {"percent", "fixed"}:
        raise ValueError("amount_type must be either 'percent' or 'fixed'.")
    normalized_amount = str(raw_amount or "").strip()
    if not normalized_amount:
        raise ValueError("amount is required")
    try:
        parsed_amount = Decimal(normalized_amount)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("amount must be a valid number") from exc
    if parsed_amount <= 0:
        raise ValueError("amount must be greater than zero")
    if normalized_type == "percent":
        if parsed_amount != parsed_amount.to_integral_value():
            raise ValueError("percent discounts must use a whole number")
        percent_value = int(parsed_amount)
        if percent_value < 1 or percent_value > 100:
            raise ValueError("percent discounts must be between 1 and 100")
        return percent_value
    cents = int((parsed_amount * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if cents < 1:
        raise ValueError("fixed discounts must be at least 0.01")
    return cents


def _parse_promo_redemption_limit(value: Any) -> int:
    normalized = str(value or "").strip()
    if not normalized:
        return 0
    try:
        parsed = int(normalized)
    except ValueError as exc:
        raise ValueError("max_redemptions must be an integer") from exc
    if parsed < 0:
        raise ValueError("max_redemptions cannot be negative")
    return parsed


def _promo_discount_label(discount: Mapping[str, Any]) -> str:
    amount_type = str(discount.get("amount_type") or "").strip().lower()
    amount = int(discount.get("amount") or 0)
    if amount_type == "fixed":
        return f"EUR {amount / 100:.2f}"
    return f"{amount}%"


def _admin_promo_code_payload(discount: Mapping[str, Any]) -> dict[str, Any]:
    starts_at = str(discount.get("starts_at") or "").strip()
    expires_at = str(discount.get("expires_at") or "").strip()
    redemption_limit = int(discount.get("max_redemptions") or 0)
    return {
        "discount_id": str(discount.get("discount_id") or "").strip(),
        "code": str(discount.get("code") or "").strip(),
        "name": str(discount.get("name") or "").strip(),
        "discount": _promo_discount_label(discount),
        "starts_at": starts_at,
        "expires_at": expires_at,
        "status": str(discount.get("status_formatted") or discount.get("status") or "").strip(),
        "redemption_limit": redemption_limit if redemption_limit > 0 else "Unlimited",
        "scope": _configured_paid_plan_labels(),
        "created_at": str(discount.get("created_at") or "").strip(),
    }


def _create_admin_promo_code(payload: Mapping[str, Any]) -> dict[str, Any]:
    product_ids = _configured_paid_plan_product_ids()
    if not product_ids:
        raise ValueError("Creem paid-plan products are not configured for promo codes.")
    name = str(payload.get("name") or "").strip()
    code = _normalize_promo_code(payload.get("code"))
    if not name:
        name = code
    amount_type = str(payload.get("amount_type") or "").strip().lower()
    amount = _parse_promo_discount_amount(amount_type, payload.get("amount") or payload.get("amount_value"))
    starts_at = _parse_optional_iso_datetime(payload.get("starts_at"), field_name="starts_at")
    expires_at = _parse_optional_iso_datetime(payload.get("expires_at"), field_name="expires_at")
    if starts_at and expires_at:
        starts_at_dt = datetime.fromisoformat(starts_at.replace("Z", "+00:00"))
        expires_at_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        if starts_at_dt >= expires_at_dt:
            raise ValueError("expires_at must be later than starts_at")
    created_discount = create_creem_discount(
        name=name,
        code=code,
        amount=amount,
        amount_type=amount_type,
        starts_at=starts_at,
        expires_at=expires_at,
        max_redemptions=_parse_promo_redemption_limit(payload.get("max_redemptions")),
        duration="once",
        product_ids=product_ids,
    )
    return _admin_promo_code_payload(created_discount)


def _list_admin_promo_codes(*, limit: int, offset: int) -> dict[str, Any]:
    page_size = max(1, int(limit))
    page_number = max(1, (max(0, int(offset)) // page_size) + 1)
    listing = list_creem_discounts(page_number=page_number, page_size=page_size)
    discounts = [
        _admin_promo_code_payload(item)
        for item in listing.get("discounts") or []
        if isinstance(item, dict)
    ]
    return {
        "promo_codes": discounts,
        "meta": {
            "current_page": int((listing.get("meta") or {}).get("current_page") or page_number),
            "per_page": int((listing.get("meta") or {}).get("per_page") or page_size),
            "total": int((listing.get("meta") or {}).get("total") or len(discounts)),
        },
    }


def _primary_email_domain(email_address: str) -> str:
    local_part, delimiter, domain = str(email_address or "").strip().partition("@")
    if not delimiter or not local_part or not domain:
        return ""
    return domain.lower()


def _months_between(started_at: str, ended_at: str) -> int:
    try:
        start_dt = datetime.fromisoformat(str(started_at or "").strip()).astimezone(timezone.utc)
        end_dt = datetime.fromisoformat(str(ended_at or "").strip()).astimezone(timezone.utc)
    except Exception:
        return 0
    if end_dt <= start_dt:
        return 0
    return max(0, int((end_dt - start_dt).days / 30))


def _ensure_clerk_plan_defaults(clerk_user_id: str, public_metadata: dict[str, object]) -> dict[str, object]:
    normalized_role = normalize_clerk_role(public_metadata.get("role"))
    normalized_plan_id = normalize_plan_id(public_metadata.get("plan_id") or DEFAULT_PLAN_ID)
    quota_overrides = public_metadata.get("quota_overrides")
    normalized_quota_overrides = dict(quota_overrides) if isinstance(quota_overrides, dict) else {}
    if (
        public_metadata.get("role") != normalized_role
        or public_metadata.get("plan_id") != normalized_plan_id
        or quota_overrides != normalized_quota_overrides
    ):
        update_clerk_user_metadata(
            clerk_user_id,
            public_metadata={
                "role": normalized_role,
                "plan_id": normalized_plan_id,
                "quota_overrides": normalized_quota_overrides,
            },
        )
    return {
        "role": normalized_role,
        "plan_id": normalized_plan_id,
        "quota_overrides": normalized_quota_overrides,
    }


def _handle_clerk_webhook_event(application, event_payload: dict[str, object]) -> dict[str, object]:
    event_type = str(event_payload.get("type") or "").strip()
    event_data = dict(event_payload.get("data") or {})
    clerk_user_id = str(event_data.get("id") or "").strip()
    if not event_type or not clerk_user_id:
        raise ValueError("Clerk webhook payload is missing the event type or user id.")

    repository = _auth_repository(application)
    email_address = get_clerk_primary_email_address(event_data)
    display_name = get_clerk_display_name(event_data)
    public_metadata = _ensure_clerk_plan_defaults(
        clerk_user_id,
        dict(event_data.get("public_metadata") or event_data.get("publicMetadata") or {}),
    )
    role_value = ROLE_ADMIN if public_metadata["role"] == "admin" else "user"

    if event_type == "user.created":
        try:
            user = repository.get_user_by_clerk_user_id(clerk_user_id)
        except Exception:
            if email_address:
                try:
                    user = _lookup_user_by_email(application, email_address)
                except Exception:
                    user = None
            else:
                user = None
        if user is None:
            user = UserRecord(
                user_id=clerk_user_id,
                email=email_address,
                display_name=display_name,
                role=role_value,
                created_at=utc_plus_seconds(0),
                updated_at=utc_plus_seconds(0),
                metadata={},
            )
        else:
            user.email = email_address or user.email
            user.display_name = display_name or user.display_name
            user.role = role_value
            user.is_active = True
        application.repositories.auth_repository.upsert_user(user)
        set_clerk_id = getattr(repository, "set_user_clerk_user_id", None)
        if callable(set_clerk_id):
            set_clerk_id(user.user_id, clerk_user_id)
        application.emit_event(
            "user_signed_up",
            user_id=user.user_id,
            source=get_clerk_signup_source(event_data),
            payload={
                "user_id": user.user_id,
                "email_domain": _primary_email_domain(email_address),
                "clerk_user_id": clerk_user_id,
            },
        )
        return {"status": "ok", "event_type": event_type, "user_id": user.user_id}

    if event_type == "user.updated":
        user = _lookup_user_by_clerk_subject(application, clerk_user_id)
        if email_address:
            user.email = email_address
        if display_name:
            user.display_name = display_name
        user.role = role_value
        user.updated_at = datetime.now(timezone.utc).isoformat()
        application.repositories.auth_repository.upsert_user(user)
        return {"status": "ok", "event_type": event_type, "user_id": user.user_id}

    if event_type == "user.deleted":
        user = _lookup_user_by_clerk_subject(application, clerk_user_id)
        user.is_active = False
        user.updated_at = datetime.now(timezone.utc).isoformat()
        application.repositories.auth_repository.upsert_user(user)
        cancel_subscriptions = getattr(repository, "cancel_subscriptions_for_user", None)
        if callable(cancel_subscriptions):
            cancel_subscriptions(user.user_id, cancelled_at=datetime.now(timezone.utc).isoformat())
        return {"status": "ok", "event_type": event_type, "user_id": user.user_id}

    return {"status": "ignored", "event_type": event_type}


def _creem_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _creem_text(payload: Mapping[str, Any], *names: str) -> str:
    for name in names:
        value = payload.get(name)
        if value is not None:
            return str(value or "").strip()
    return ""


def _creem_object_id(value: Any) -> str:
    if isinstance(value, Mapping):
        return _creem_text(value, "id", "customer_id", "product_id")
    return str(value or "").strip()


def _creem_event_time(value: Any) -> str:
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp = timestamp / 1000
        return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
    normalized = str(value or "").strip()
    return normalized or utc_plus_seconds(0)


def _creem_nested_mapping(container: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = container.get(key)
    return dict(value) if isinstance(value, Mapping) else {}


def _creem_subscription_object(event_object: Mapping[str, Any]) -> dict[str, Any]:
    if _creem_text(event_object, "object") == "subscription":
        return dict(event_object)
    nested = _creem_nested_mapping(event_object, "subscription")
    if nested:
        return nested
    return {}


def _creem_checkout_object(event_object: Mapping[str, Any]) -> dict[str, Any]:
    if _creem_text(event_object, "object") == "checkout":
        return dict(event_object)
    nested = _creem_nested_mapping(event_object, "checkout")
    if nested:
        return nested
    return {}


def _creem_metadata(*payloads: Mapping[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for payload in payloads:
        item = payload.get("metadata")
        if isinstance(item, Mapping):
            metadata.update(dict(item))
    return metadata


def _creem_product_id(
    metadata: Mapping[str, Any],
    subscription: Mapping[str, Any],
    checkout: Mapping[str, Any],
    order: Mapping[str, Any],
) -> str:
    from_metadata = _creem_text(metadata, "product_id", "productId", "creem_product_id")
    if from_metadata:
        return from_metadata
    for source in (subscription, checkout, order):
        product = source.get("product")
        product_id = _creem_object_id(product)
        if product_id:
            return product_id
    for item in subscription.get("items") or []:
        if isinstance(item, Mapping):
            product_id = _creem_text(item, "product_id", "productId")
            if product_id:
                return product_id
    return ""


def _creem_customer_details(
    subscription: Mapping[str, Any],
    checkout: Mapping[str, Any],
    order: Mapping[str, Any],
    event_object: Mapping[str, Any],
) -> tuple[str, str]:
    for source in (subscription, checkout, event_object, order):
        customer = source.get("customer")
        if isinstance(customer, Mapping):
            return _creem_text(customer, "id", "customer_id"), _creem_text(customer, "email")
        customer_id = str(customer or "").strip()
        if customer_id:
            return customer_id, ""
    return "", ""


def _insert_creem_subscription_event(
    repository,
    *,
    event_id: str,
    user_id: str,
    event_type: str,
    plan_id: str,
    previous_plan_id: str,
    provider_event_name: str,
    occurred_at: str,
    payload: dict[str, object],
) -> None:
    repository.insert_subscription_event(
        {
            "event_id": event_id or f"subevt_{uuid4().hex[:16]}",
            "user_id": user_id,
            "event_type": event_type,
            "plan_id": plan_id,
            "previous_plan_id": previous_plan_id,
            "billing_provider": "creem",
            "provider_event_name": provider_event_name,
            "occurred_at": occurred_at,
            "payload": payload,
        }
    )


def _confirm_creem_checkout_redirect(application, context, raw_query: str) -> dict[str, object]:
    normalized_query = str(raw_query or "").strip().lstrip("?")
    verify_creem_redirect_signature(normalized_query)
    params = dict(parse_qsl(normalized_query, keep_blank_values=False))
    checkout_id = str(params.get("checkout_id") or "").strip()
    product_id = str(params.get("product_id") or "").strip()
    plan_id = normalize_plan_id(get_plan_for_product_id(product_id) or params.get("plan_id") or DEFAULT_PLAN_ID)
    requested_plan_id = normalize_plan_id(params.get("plan_id") or plan_id)
    if plan_id == DEFAULT_PLAN_ID:
        raise ValueError("Creem checkout product is not configured for a paid Runr plan.")
    if requested_plan_id != plan_id:
        raise ValueError("Creem checkout product does not match the requested Runr plan.")

    metadata = {
        "user_id": context.user.user_id,
        "plan_id": plan_id,
        "clerk_user_id": context.clerk_user_id,
    }
    customer_id = str(params.get("customer_id") or "").strip()
    subscription_id = str(params.get("subscription_id") or "").strip()
    customer = {
        "id": customer_id,
        "email": context.user.email,
    }
    if not customer.get("email"):
        customer["email"] = context.user.email
    if customer_id and not customer.get("id"):
        customer["id"] = customer_id

    checkout_object = {
        "id": checkout_id,
        "object": "checkout",
        "request_id": str(params.get("request_id") or "").strip(),
        "status": "completed",
        "product": product_id,
        "customer": customer,
        "metadata": metadata,
    }
    if subscription_id:
        checkout_object["subscription"] = {
            "id": subscription_id,
            "object": "subscription",
            "product": product_id,
            "customer": customer,
            "status": "active",
            "metadata": metadata,
        }
    occurred_at = utc_plus_seconds(0)
    current_subscription = _lookup_subscription_record(application, context.user.user_id) or {}
    previous_plan_id = normalize_plan_id(current_subscription.get("plan_id") or DEFAULT_PLAN_ID)
    repository = _auth_repository(application)
    if subscription_id:
        repository.upsert_subscription(
            {
                "subscription_id": subscription_id,
                "user_id": context.user.user_id,
                "plan_id": plan_id,
                "status": "active",
                "billing_provider": "creem",
                "creem_subscription_id": subscription_id,
                "creem_customer_id": customer_id,
                "creem_order_id": str(params.get("order_id") or "").strip(),
                "current_period_start": str(current_subscription.get("current_period_start") or occurred_at),
                "current_period_end": str(current_subscription.get("current_period_end") or ""),
                "cancelled_at": "",
                "created_at": str(current_subscription.get("created_at") or occurred_at),
                "updated_at": occurred_at,
            }
        )
    _insert_creem_subscription_event(
        repository,
        event_id=str(params.get("checkout_id") or checkout_id or f"creem_redirect_{uuid4().hex[:12]}"),
        user_id=context.user.user_id,
        event_type="checkout_completed",
        plan_id=plan_id,
        previous_plan_id=previous_plan_id,
        provider_event_name="checkout.redirect_confirmed",
        occurred_at=occurred_at,
        payload={"checkout": checkout_object},
    )
    if context.clerk_user_id:
        update_user_plan_in_clerk(context.clerk_user_id, plan_id)
    if compare_plan_tiers(previous_plan_id, plan_id) < 0:
        reset_quota_usage = getattr(repository, "reset_quota_usage", None)
        if callable(reset_quota_usage):
            reset_quota_usage(context.user.user_id, _current_period_key())
    return {"status": "ok", "event_type": "checkout.redirect_confirmed", "user_id": context.user.user_id, "plan_id": plan_id}


def _handle_creem_webhook_event(
    application,
    *,
    event_name: str,
    payload: dict[str, object],
) -> dict[str, object]:
    repository = _auth_repository(application)
    event_object = _creem_mapping(payload.get("object")) or _creem_mapping(payload.get("data"))
    subscription = _creem_subscription_object(event_object)
    checkout = _creem_checkout_object(event_object)
    order = _creem_nested_mapping(event_object, "order")
    metadata = _creem_metadata(checkout, subscription, event_object)
    occurred_at = _creem_event_time(
        subscription.get("updated_at")
        or event_object.get("updated_at")
        or payload.get("created_at")
        or subscription.get("created_at")
        or event_object.get("created_at")
    )
    user_id = _creem_text(metadata, "user_id", "userId", "reference_id", "referenceId")
    customer_id, customer_email = _creem_customer_details(subscription, checkout, order, event_object)
    if not user_id:
        if customer_email:
            try:
                user_id = _lookup_user_by_email(application, customer_email).user_id
            except Exception:
                user_id = ""
    if not user_id:
        raise ValueError("Unable to resolve a local user for the Creem webhook payload.")

    current_subscription = _lookup_subscription_record(application, user_id) or {}
    product_id = _creem_product_id(metadata, subscription, checkout, order)
    plan_id = normalize_plan_id(
        _creem_text(metadata, "plan_id", "planId")
        or get_plan_for_product_id(product_id)
        or current_subscription.get("plan_id")
        or DEFAULT_PLAN_ID
    )
    subscription_id = _creem_text(subscription, "id", "subscription_id") or _creem_text(
        event_object,
        "subscription_id",
        "subscription",
    )
    order_id = _creem_object_id(order) or _creem_text(event_object, "order_id", "order")
    status = _creem_text(subscription, "status") or {
        "checkout.completed": "active",
        "subscription.active": "active",
        "subscription.paid": "active",
        "subscription.trialing": "trialing",
        "subscription.update": "active",
        "subscription.scheduled_cancel": "scheduled_cancel",
        "subscription.past_due": "past_due",
        "subscription.paused": "paused",
        "subscription.expired": "expired",
        "subscription.canceled": "canceled",
    }.get(event_name, "active")
    subscription_record = {
        "subscription_id": subscription_id,
        "user_id": user_id,
        "plan_id": plan_id,
        "status": status,
        "billing_provider": "creem",
        "creem_subscription_id": subscription_id,
        "creem_customer_id": customer_id,
        "creem_order_id": order_id,
        "current_period_start": str(
            subscription.get("current_period_start_date")
            or subscription.get("current_period_start")
            or subscription.get("created_at")
            or current_subscription.get("current_period_start")
            or ""
        ),
        "current_period_end": str(
            subscription.get("current_period_end_date")
            or subscription.get("current_period_end")
            or subscription.get("next_transaction_date")
            or subscription.get("canceled_at")
            or current_subscription.get("current_period_end")
            or ""
        ),
        "cancelled_at": str(subscription.get("canceled_at") or current_subscription.get("cancelled_at") or ""),
        "created_at": str(current_subscription.get("created_at") or subscription.get("created_at") or occurred_at),
        "updated_at": str(subscription.get("updated_at") or occurred_at),
    }

    user = application.get_user(user_id)
    clerk_user_id = _resolve_user_clerk_user_id(application, user)
    previous_plan_id = normalize_plan_id(current_subscription.get("plan_id") or DEFAULT_PLAN_ID)
    provider_event_id = str(payload.get("id") or f"creem_{uuid4().hex[:16]}").strip()
    event_type = {
        "checkout.completed": "checkout_completed",
        "subscription.active": "subscription_started",
        "subscription.trialing": "subscription_started",
        "subscription.paid": "subscription_paid",
        "subscription.update": "subscription_changed",
        "subscription.scheduled_cancel": "subscription_scheduled_cancel",
        "subscription.past_due": "subscription_past_due",
        "subscription.paused": "subscription_paused",
        "subscription.expired": "subscription_cancelled",
        "subscription.canceled": "subscription_cancelled",
    }.get(event_name)

    if not event_type:
        return {"status": "ignored", "event_type": event_name}

    if subscription_id:
        repository.upsert_subscription(subscription_record)

    _insert_creem_subscription_event(
        repository,
        event_id=provider_event_id,
        user_id=user_id,
        event_type=event_type,
        plan_id=plan_id,
        previous_plan_id=previous_plan_id,
        provider_event_name=event_name,
        occurred_at=occurred_at,
        payload=payload,
    )

    grant_access_events = {"checkout.completed", "subscription.active", "subscription.trialing", "subscription.paid"}
    revoke_access_events = {"subscription.canceled", "subscription.expired", "subscription.paused"}
    if event_name in grant_access_events:
        if clerk_user_id:
            update_user_plan_in_clerk(clerk_user_id, plan_id)
        if compare_plan_tiers(previous_plan_id, plan_id) < 0:
            reset_quota_usage = getattr(repository, "reset_quota_usage", None)
            if callable(reset_quota_usage):
                reset_quota_usage(user_id, _current_period_key())
        if event_name in {"subscription.active", "subscription.trialing", "checkout.completed"}:
            application.emit_event(
                "subscription_started",
                user_id=user_id,
                source="creem",
                payload={
                    "user_id": user_id,
                    "plan_id": plan_id,
                    "price_eur": int(get_plan(plan_id).get("price_eur") or 0),
                    "creem_subscription_id": subscription_id,
                },
            )
    elif event_name in {"subscription.update", "subscription.scheduled_cancel", "subscription.past_due"}:
        if clerk_user_id and previous_plan_id != plan_id:
            update_user_plan_in_clerk(clerk_user_id, plan_id)
        if previous_plan_id != plan_id:
            direction = "upgrade" if compare_plan_tiers(previous_plan_id, plan_id) < 0 else "downgrade"
            application.emit_event(
                "subscription_changed",
                user_id=user_id,
                source="creem",
                payload={
                    "user_id": user_id,
                    "previous_plan_id": previous_plan_id,
                    "new_plan_id": plan_id,
                    "direction": direction,
                },
            )
    elif event_name in revoke_access_events:
        if clerk_user_id:
            update_user_plan_in_clerk(clerk_user_id, DEFAULT_PLAN_ID)
        if event_name in {"subscription.canceled", "subscription.expired"}:
            application.emit_event(
                "subscription_cancelled",
                user_id=user_id,
                source="creem",
                payload={
                    "user_id": user_id,
                    "plan_id": plan_id,
                    "months_active": _months_between(
                        str(current_subscription.get("created_at") or subscription.get("created_at") or ""),
                        str(subscription.get("updated_at") or occurred_at),
                    ),
                    "cancellation_reason": status,
                },
            )

    return {"status": "ok", "event_type": event_name, "user_id": user_id}


def _review_application_status_sql(payload_column: str) -> str:
    return f"""
        COALESCE(
            NULLIF(json_extract({payload_column}, '$.metadata.application_status'), ''),
            CASE lower(COALESCE(json_extract({payload_column}, '$.metadata.tracker_status'), ''))
                WHEN 'applied' THEN 'Applied'
                WHEN 'email_confirmed' THEN 'Applied'
                WHEN 'interview_invited' THEN 'Interviewing'
                WHEN 'interviewing' THEN 'Interviewing'
                WHEN 'rejected' THEN 'Rejected'
                WHEN 'offer' THEN 'Offer'
                WHEN 'withdrawn' THEN 'Withdrawn'
                WHEN 'not_applied' THEN 'Not applied'
                ELSE 'Unknown'
            END
        )
    """.strip()


def _admin_analytics_snapshot_queries() -> dict[str, str]:
    review_application_status = _review_application_status_sql("r.payload_json")
    review_application_status_for_best_sources = _review_application_status_sql("reviews.payload_json")
    return {
        "automation_success_rate": """
            WITH run_enrichment AS (
                SELECT
                    runs.id AS run_id,
                    runs.status,
                    COALESCE(
                        NULLIF(json_extract(runs.metadata_json, '$.run_kind'), ''),
                        CASE
                            WHEN EXISTS (
                                SELECT 1
                                FROM json_each(runs.run_input_overrides_json, '$.manual_urls_inline')
                            ) THEN 'quick_apply'
                            ELSE 'standard'
                        END
                    ) AS run_kind,
                    COALESCE(
                        NULLIF(json_extract(runs.run_plan_json, '$.workspace_snapshot.metadata.automation_flow'), ''),
                        NULLIF(json_extract(runs.run_plan_json, '$.workspace_snapshot.settings.automation_flow'), ''),
                        NULLIF(json_extract(runs.metadata_json, '$.workspace_type'), ''),
                        'unknown'
                    ) AS automation_flow
                FROM runs
            )
            SELECT
                automation_flow,
                run_kind,
                COUNT(*) AS total_runs,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS successful_runs,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_runs,
                ROUND(
                    100.0 * SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
                    2
                ) AS success_rate_pct
            FROM run_enrichment
            GROUP BY automation_flow, run_kind
            ORDER BY total_runs DESC, automation_flow, run_kind
        """,
        "stage_failure_rate_by_type": """
            SELECT
                stage_type,
                COUNT(*) AS total_stage_executions,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_stage_executions,
                ROUND(
                    100.0 * SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
                    2
                ) AS failure_rate_pct,
                SUM(COALESCE(CAST(json_extract(metrics_json, '$.failures') AS INTEGER), 0)) AS metric_failures,
                SUM(COALESCE(CAST(json_extract(metrics_json, '$.rejected') AS INTEGER), 0)) AS metric_rejected
            FROM run_stage_results
            GROUP BY stage_type
            ORDER BY failed_stage_executions DESC, total_stage_executions DESC, stage_type
        """,
        "jobs_by_source": """
            WITH configured_sources AS (
                SELECT
                    runs.id AS run_id,
                    COALESCE(
                        NULLIF(json_extract(source.value, '$.connector_id'), ''),
                        NULLIF(json_extract(source.value, '$.id'), ''),
                        'unknown'
                    ) AS configured_source
                FROM runs
                LEFT JOIN json_each(runs.run_plan_json, '$.workspace_snapshot.sources') AS source
            ),
            observed_jobs AS (
                SELECT
                    run_jobs.run_id,
                    COALESCE(
                        NULLIF(run_jobs.source_type, ''),
                        NULLIF(run_jobs.portal, ''),
                        NULLIF(json_extract(run_jobs.payload_json, '$.source_type'), ''),
                        NULLIF(json_extract(run_jobs.payload_json, '$.portal'), ''),
                        'unknown'
                    ) AS source,
                    COUNT(*) AS jobs_count
                FROM run_jobs
                GROUP BY run_jobs.run_id, source
            )
            SELECT
                observed_jobs.source,
                COUNT(DISTINCT observed_jobs.run_id) AS run_count,
                SUM(observed_jobs.jobs_count) AS job_count,
                COUNT(DISTINCT configured_sources.configured_source) AS configured_source_variants
            FROM observed_jobs
            LEFT JOIN configured_sources ON configured_sources.run_id = observed_jobs.run_id
            GROUP BY observed_jobs.source
            ORDER BY job_count DESC, observed_jobs.source
        """,
        "screening_funnel": """
            WITH funnel_stages AS (
                SELECT
                    CASE
                        WHEN stage_type IN (
                            'jobs.acquire.search_listings',
                            'jobs.acquire.company_sites',
                            'jobs.acquire.job_boards',
                            'jobs.ingest.curated_urls',
                            'legacy.linkedin.acquire',
                            'legacy.blue_collar.stage1'
                        ) THEN 'acquired'
                        WHEN stage_type IN (
                            'jobs.merge.dedupe'
                        ) THEN 'deduped'
                        WHEN stage_type IN (
                            'jobs.screen.filter',
                            'legacy.white_collar.local_filter',
                            'legacy.blue_collar.stage2'
                        ) THEN 'screened_approved'
                        WHEN stage_type IN (
                            'jobs.prioritize.rank',
                            'legacy.white_collar.rank',
                            'legacy.blue_collar.stage3'
                        ) THEN 'prioritized_approved'
                        WHEN stage_type IN (
                            'applications.generate.documents',
                            'legacy.white_collar.docs',
                            'profiles.generate.reusable',
                            'legacy.blue_collar.stage4',
                            'applications.package.export',
                            'legacy.blue_collar.stage5'
                        ) THEN 'documents_generated'
                        ELSE 'other'
                    END AS funnel_stage,
                    SUM(
                        COALESCE(CAST(json_extract(metrics_json, '$.jobs_found') AS INTEGER), 0)
                        + COALESCE(CAST(json_extract(metrics_json, '$.jobs_ingested') AS INTEGER), 0)
                        + COALESCE(CAST(json_extract(metrics_json, '$.merged_jobs') AS INTEGER), 0)
                        + COALESCE(CAST(json_extract(metrics_json, '$.approved') AS INTEGER), 0)
                    ) AS stage_volume
                FROM run_stage_results
                GROUP BY funnel_stage
            ),
            review_stage AS (
                SELECT
                    'review_approved' AS funnel_stage,
                    COUNT(*) AS stage_volume
                FROM reviews
                WHERE lower(status) = 'approved'
            )
            SELECT funnel_stage, stage_volume
            FROM (
                SELECT funnel_stage, stage_volume FROM funnel_stages
                UNION ALL
                SELECT funnel_stage, stage_volume FROM review_stage
            )
            WHERE funnel_stage <> 'other'
            ORDER BY
                CASE funnel_stage
                    WHEN 'acquired' THEN 1
                    WHEN 'deduped' THEN 2
                    WHEN 'screened_approved' THEN 3
                    WHEN 'prioritized_approved' THEN 4
                    WHEN 'documents_generated' THEN 5
                    WHEN 'review_approved' THEN 6
                    ELSE 99
                END
        """,
        "applications_per_user": f"""
            WITH review_outcomes AS (
                SELECT
                    r.run_id,
                    {review_application_status} AS application_status
                FROM reviews AS r
            ),
            runs_by_user AS (
                SELECT
                    runs.id AS run_id,
                    runs.user_id AS user_id
                FROM runs
                WHERE runs.user_id != ''
            )
            SELECT
                users.user_id,
                COALESCE(NULLIF(json_extract(users.payload_json, '$.display_name'), ''), users.email) AS user_label,
                COUNT(DISTINCT runs_by_user.run_id) AS run_count,
                SUM(
                    CASE
                        WHEN review_outcomes.application_status IN ('Applied', 'Interviewing', 'Rejected', 'Offer', 'Withdrawn')
                            THEN 1
                        ELSE 0
                    END
                ) AS application_count,
                ROUND(
                    1.0 * SUM(
                        CASE
                            WHEN review_outcomes.application_status IN ('Applied', 'Interviewing', 'Rejected', 'Offer', 'Withdrawn')
                                THEN 1
                            ELSE 0
                        END
                    ) / NULLIF(COUNT(DISTINCT runs_by_user.run_id), 0),
                    2
                ) AS applications_per_run
            FROM users
            LEFT JOIN runs_by_user ON runs_by_user.user_id = users.user_id
            LEFT JOIN review_outcomes ON review_outcomes.run_id = runs_by_user.run_id
            GROUP BY users.user_id, user_label
            ORDER BY application_count DESC, run_count DESC, user_label
        """,
        "quick_apply_adoption": """
            WITH run_kinds AS (
                SELECT
                    runs.id AS run_id,
                    runs.user_id AS user_id,
                    COALESCE(NULLIF(json_extract(runs.metadata_json, '$.run_kind'), ''), 'standard') AS run_kind,
                    (
                        SELECT COUNT(*)
                        FROM json_each(runs.run_input_overrides_json, '$.manual_urls_inline')
                    ) AS manual_url_count
                FROM runs
                WHERE runs.user_id != ''
            )
            SELECT
                users.user_id,
                COALESCE(NULLIF(json_extract(users.payload_json, '$.display_name'), ''), users.email) AS user_label,
                COUNT(run_kinds.run_id) AS total_runs,
                SUM(CASE WHEN run_kinds.run_kind = 'quick_apply' THEN 1 ELSE 0 END) AS quick_apply_runs,
                SUM(CASE WHEN run_kinds.run_kind = 'quick_apply' THEN run_kinds.manual_url_count ELSE 0 END) AS quick_apply_urls,
                ROUND(
                    100.0 * SUM(CASE WHEN run_kinds.run_kind = 'quick_apply' THEN 1 ELSE 0 END)
                    / NULLIF(COUNT(run_kinds.run_id), 0),
                    2
                ) AS quick_apply_run_share_pct
            FROM users
            LEFT JOIN run_kinds ON run_kinds.user_id = users.user_id
            GROUP BY users.user_id, user_label
            ORDER BY quick_apply_runs DESC, total_runs DESC, user_label
        """,
        "referral_outreach_funnel": """
            WITH outreach AS (
                SELECT
                    users.user_id,
                    COALESCE(NULLIF(json_extract(outreach_entry.value, '$.outreach_status'), ''), 'Not contacted') AS outreach_status,
                    CASE
                        WHEN json_extract(outreach_entry.value, '$.contact_can_refer') IN (1, '1', 'true', 'TRUE') THEN 1
                        ELSE 0
                    END AS contact_can_refer
                FROM users
                JOIN json_each(users.payload_json, '$.metadata.referral_outreach') AS outreach_entry
            )
            SELECT
                outreach_status,
                COUNT(*) AS outreach_count,
                SUM(contact_can_refer) AS referable_contact_count,
                COUNT(DISTINCT user_id) AS user_count
            FROM outreach
            GROUP BY outreach_status
            ORDER BY
                CASE outreach_status
                    WHEN 'Not contacted' THEN 1
                    WHEN 'Contacted' THEN 2
                    WHEN 'Replied' THEN 3
                    WHEN 'Referral offered' THEN 4
                    WHEN 'No referral' THEN 5
                    ELSE 99
                END
        """,
        "repeat_failures": """
            WITH failure_events AS (
                SELECT
                    runs.workspace_id,
                    runs.user_id AS user_id,
                    run_stage_results.stage_type,
                    COALESCE(
                        NULLIF(run_stage_results.error, ''),
                        NULLIF(json_extract(runs.metadata_json, '$.preflight_error.message'), ''),
                        NULLIF(runs.last_error, ''),
                        'unknown_error'
                    ) AS error_message
                FROM run_stage_results
                JOIN runs ON runs.id = run_stage_results.run_id
                WHERE run_stage_results.status = 'failed' OR runs.status = 'failed'
            )
            SELECT
                workspace_id,
                user_id,
                stage_type,
                error_message,
                COUNT(*) AS failure_count
            FROM failure_events
            GROUP BY workspace_id, user_id, stage_type, error_message
            HAVING COUNT(*) > 1
            ORDER BY failure_count DESC, workspace_id, user_id, stage_type
        """,
        "churn_risk_users": f"""
            WITH review_outcomes AS (
                SELECT
                    reviews.run_id,
                    {review_application_status_for_best_sources} AS application_status
                FROM reviews
            ),
            user_activity AS (
                SELECT
                    users.user_id,
                    COALESCE(NULLIF(json_extract(users.payload_json, '$.display_name'), ''), users.email) AS user_label,
                    json_extract(users.payload_json, '$.created_at') AS user_created_at,
                    MAX(runs.created_at) AS last_run_at,
                    SUM(
                        CASE
                            WHEN review_outcomes.application_status IN ('Applied', 'Interviewing', 'Rejected', 'Offer', 'Withdrawn')
                                THEN 1
                            ELSE 0
                        END
                    ) AS application_count
                FROM users
                LEFT JOIN runs ON runs.user_id = users.user_id
                LEFT JOIN review_outcomes ON review_outcomes.run_id = runs.id
                WHERE users.is_active = 1
                GROUP BY users.user_id, user_label, user_created_at
            ),
            scored_users AS (
                SELECT
                    user_id,
                    user_label,
                    user_created_at,
                    last_run_at,
                    application_count,
                    CASE
                        WHEN last_run_at IS NULL THEN 'high'
                        WHEN julianday('now') - julianday(last_run_at) >= 30 AND application_count = 0 THEN 'high'
                        WHEN julianday('now') - julianday(last_run_at) >= 14 AND application_count <= 1 THEN 'medium'
                        ELSE 'low'
                    END AS churn_risk
                FROM user_activity
            )
            SELECT
                user_id,
                user_label,
                user_created_at,
                last_run_at,
                application_count,
                churn_risk
            FROM scored_users
            WHERE churn_risk <> 'low'
            ORDER BY
                CASE churn_risk
                    WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2
                    ELSE 99
                END,
                COALESCE(last_run_at, user_created_at) ASC
        """,
        "best_sources_by_outcome": f"""
            WITH review_outcomes AS (
                SELECT
                    reviews.run_id,
                    reviews.job_id,
                    {review_application_status_for_best_sources} AS application_status
                FROM reviews
            ),
            job_sources AS (
                SELECT
                    run_jobs.run_id,
                    run_jobs.job_id,
                    COALESCE(
                        NULLIF(run_jobs.source_type, ''),
                        NULLIF(run_jobs.portal, ''),
                        NULLIF(json_extract(run_jobs.payload_json, '$.source_type'), ''),
                        NULLIF(json_extract(run_jobs.payload_json, '$.portal'), ''),
                        'unknown'
                    ) AS source
                FROM run_jobs
            )
            SELECT
                job_sources.source,
                COUNT(*) AS reviewed_jobs,
                SUM(CASE WHEN review_outcomes.application_status = 'Applied' THEN 1 ELSE 0 END) AS applied_count,
                SUM(CASE WHEN review_outcomes.application_status = 'Interviewing' THEN 1 ELSE 0 END) AS interviewing_count,
                SUM(CASE WHEN review_outcomes.application_status = 'Offer' THEN 1 ELSE 0 END) AS offer_count,
                SUM(CASE WHEN review_outcomes.application_status = 'Rejected' THEN 1 ELSE 0 END) AS rejected_count,
                ROUND(
                    100.0 * SUM(
                        CASE
                            WHEN review_outcomes.application_status IN ('Applied', 'Interviewing', 'Offer') THEN 1
                            ELSE 0
                        END
                    ) / NULLIF(COUNT(*), 0),
                    2
                ) AS positive_outcome_rate_pct
            FROM job_sources
            JOIN review_outcomes
                ON review_outcomes.run_id = job_sources.run_id
               AND review_outcomes.job_id = job_sources.job_id
            GROUP BY job_sources.source
            HAVING COUNT(*) > 0
            ORDER BY positive_outcome_rate_pct DESC, reviewed_jobs DESC, job_sources.source
        """,
    }


def _database_query_rows(
    application,
    query: str,
    params: tuple[object, ...] | list[object] | None = None,
) -> list[dict]:
    repositories = getattr(application, "repositories", None)
    analytics_store = getattr(repositories, "analytics_store", None) if repositories is not None else None
    query_rows = getattr(analytics_store, "query_rows", None)
    if not callable(query_rows):
        raise RuntimeError("Admin reporting requires a query-capable analytics store.")
    return list(query_rows(query, tuple(params or ())))


def _build_admin_analytics_snapshot(application) -> dict[str, object]:
    snapshot: dict[str, object] = {"generated_at": datetime.now(timezone.utc).isoformat()}
    for metric_name, query in _admin_analytics_snapshot_queries().items():
        try:
            snapshot[metric_name] = {
                "rows": _database_query_rows(application, query),
                "error": None,
            }
        except Exception as exc:
            snapshot[metric_name] = {
                "rows": [],
                "error": str(exc),
            }
    return snapshot


def _admin_user_health_segment_queries(
    *,
    now: datetime | None = None,
) -> dict[str, tuple[str, tuple[object, ...]]]:
    resolved_now = now or datetime.now(timezone.utc)
    cutoff_3_days = (resolved_now - timedelta(days=3)).isoformat()
    cutoff_5_days = (resolved_now - timedelta(days=5)).isoformat()
    cutoff_7_days = (resolved_now - timedelta(days=7)).isoformat()
    cutoff_14_days = (resolved_now - timedelta(days=14)).isoformat()
    return {
        "no_cv_uploaded": (
            """
            SELECT users.user_id
            FROM users
            WHERE users.is_active = 1
              AND COALESCE(json_extract(users.payload_json, '$.created_at'), '') != ''
              AND json_extract(users.payload_json, '$.created_at') < ?
              AND NOT EXISTS (
                    SELECT 1
                    FROM candidate_assets
                    WHERE candidate_assets.user_id = users.user_id
                )
            ORDER BY users.user_id
            """,
            (cutoff_3_days,),
        ),
        "no_run_yet": (
            """
            SELECT users.user_id
            FROM users
            WHERE users.is_active = 1
              AND EXISTS (
                    SELECT 1
                    FROM candidate_assets
                    WHERE candidate_assets.user_id = users.user_id
                      AND lower(candidate_assets.asset_kind) = 'workspace_cv'
                )
              AND NOT EXISTS (
                    SELECT 1
                    FROM runs
                    WHERE runs.user_id = users.user_id
                )
            ORDER BY users.user_id
            """,
            (),
        ),
        "stuck_approvals": (
            """
            WITH approved_reviews AS (
                SELECT
                    runs.user_id AS user_id,
                    COUNT(*) AS approved_review_count,
                    SUM(
                        CASE
                            WHEN NULLIF(trim(COALESCE(json_extract(reviews.payload_json, '$.metadata.tracker_status'), '')), '') IS NOT NULL
                                THEN 1
                            ELSE 0
                        END
                    ) AS explicit_tracker_status_count
                FROM reviews
                JOIN runs ON runs.id = reviews.run_id
                WHERE runs.user_id != ''
                  AND (
                        lower(COALESCE(json_extract(reviews.payload_json, '$.decision'), '')) = 'approved'
                        OR lower(COALESCE(reviews.status, '')) = 'approved'
                    )
                GROUP BY runs.user_id
            )
            SELECT approved_reviews.user_id
            FROM approved_reviews
            JOIN users ON users.user_id = approved_reviews.user_id
            WHERE users.is_active = 1
              AND approved_reviews.approved_review_count >= 3
              AND approved_reviews.explicit_tracker_status_count = 0
            ORDER BY approved_reviews.user_id
            """,
            (),
        ),
        "repeated_failures": (
            """
            SELECT runs.user_id AS user_id
            FROM runs
            JOIN users ON users.user_id = runs.user_id
            WHERE users.is_active = 1
              AND runs.user_id != ''
              AND lower(COALESCE(runs.status, '')) = 'failed'
              AND COALESCE(NULLIF(runs.finished_at, ''), NULLIF(runs.updated_at, ''), runs.created_at) >= ?
            GROUP BY runs.user_id
            HAVING COUNT(*) > 3
            ORDER BY user_id
            """,
            (cutoff_7_days,),
        ),
        "gmail_stale": (
            """
            SELECT users.user_id
            FROM users
            WHERE users.is_active = 1
              AND lower(COALESCE(json_extract(users.payload_json, '$.metadata.tracker_email_integration.provider_id'), '')) = 'gmail'
              AND COALESCE(json_extract(users.payload_json, '$.metadata.tracker_email_integration.email_address'), '') != ''
              AND COALESCE(json_extract(users.payload_json, '$.metadata.tracker_email_integration.connected_at'), '') != ''
              AND COALESCE(json_extract(users.payload_json, '$.metadata.tracker_email_integration.last_sync_at'), '') != ''
              AND json_extract(users.payload_json, '$.metadata.tracker_email_integration.last_sync_at') < ?
            ORDER BY users.user_id
            """,
            (cutoff_5_days,),
        ),
        "churn_risk": (
            """
            WITH token_activity AS (
                SELECT
                    user_id,
                    MAX(COALESCE(NULLIF(json_extract(payload_json, '$.last_used_at'), ''), '')) AS last_token_used_at
                FROM api_tokens
                WHERE is_active = 1
                GROUP BY user_id
            ),
            run_activity AS (
                SELECT
                    user_id,
                    MAX(COALESCE(NULLIF(finished_at, ''), NULLIF(updated_at, ''), created_at)) AS last_run_at
                FROM runs
                WHERE user_id != ''
                GROUP BY user_id
            )
            SELECT users.user_id
            FROM users
            JOIN token_activity ON token_activity.user_id = users.user_id
            LEFT JOIN run_activity ON run_activity.user_id = users.user_id
            WHERE users.is_active = 1
              AND token_activity.last_token_used_at != ''
              AND token_activity.last_token_used_at < ?
              AND (
                    run_activity.last_run_at IS NULL
                    OR run_activity.last_run_at < ?
                )
            ORDER BY users.user_id
            """,
            (cutoff_14_days, cutoff_14_days),
        ),
    }


def _build_admin_user_health_snapshot(application) -> dict[str, object]:
    snapshot: dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "segments": {},
    }
    for segment_name, (query, params) in _admin_user_health_segment_queries().items():
        rows = _database_query_rows(application, query, params)
        user_ids = [str(row.get("user_id") or "").strip() for row in rows if str(row.get("user_id") or "").strip()]
        snapshot["segments"][segment_name] = {
            "count": len(user_ids),
            "user_ids": user_ids,
        }
    return snapshot


def build_handler(
    application,
    *,
    allowed_origins: set[str] | None = None,
    allowed_extension_origins: set[str] | None = None,
    allow_all_origins: bool = False,
):
    normalized_allowed_origins = {_normalize_origin_value(item) for item in (allowed_origins or set())}
    normalized_allowed_origins.discard("")
    normalized_allowed_extension_origins = {
        _normalize_origin_value(item) for item in (allowed_extension_origins or set())
    }
    normalized_allowed_extension_origins = {
        item for item in normalized_allowed_extension_origins if _origin_is_chrome_extension(item)
    }
    render_frontend_origin = _normalize_hostname_origin(os.getenv("RENDER_FRONTEND_EXTERNAL_HOSTNAME", ""))
    if render_frontend_origin:
        normalized_allowed_origins.add(render_frontend_origin)
    route_registry = build_route_registry()

    class BackendApiHandler(BaseHTTPRequestHandler):
        def _begin_request(self) -> None:
            self._request_started_at = perf_counter()
            self._response_started = False
            self._client_disconnected = False
            self._matched_route_name = ""
            self._response_status = 0
            self._response_bytes = 0
            self._request_error_type = ""
            self._telemetry = new_telemetry()


        def _route_shape(self) -> str:
            try:
                _, segments, _ = self._parse_request()
            except Exception:
                return "/"
            shaped: list[str] = []
            previous = ""
            for segment in segments:
                value = str(segment or "")
                lower = value.lower()
                if previous == "runs":
                    shaped.append(":run_id")
                elif previous == "workspaces":
                    shaped.append(":workspace_id")
                elif previous == "documents":
                    shaped.append(":document_id")
                elif previous == "artifacts":
                    shaped.append(":artifact_id")
                elif previous in {"users", "reviews", "secrets", "tokens"}:
                    shaped.append(":id")
                elif previous == "by-id":
                    shaped.append(":id")
                elif re.match(r"^(run|asset|doc|review|user)_[a-z0-9_-]+$", lower):
                    shaped.append(":id")
                elif re.match(r"^\d{6,}$", lower):
                    shaped.append(":id")
                elif re.match(r"^[a-f0-9]{16,}$", lower):
                    shaped.append(":id")
                elif re.match(r"^[a-z0-9_-]{32,}$", lower):
                    shaped.append(":id")
                else:
                    shaped.append(value)
                previous = value
            return "/" + "/".join(shaped) if shaped else "/"

        def _finish_request_log(self) -> None:
            started_at = getattr(self, "_request_started_at", None)
            if started_at is None:
                return
            duration_ms = round((perf_counter() - started_at) * 1000, 2)
            payload = {
                "event": "api_request_timing",
                "method": str(getattr(self, "command", "") or ""),
                "route": self._route_shape(),
                "route_name": str(getattr(self, "_matched_route_name", "") or ""),
                "status": int(getattr(self, "_response_status", 0) or 0),
                "duration_ms": duration_ms,
                "response_bytes": int(getattr(self, "_response_bytes", 0) or 0),
                "client_disconnected": bool(getattr(self, "_client_disconnected", False)),
            }
            error_type = str(getattr(self, "_request_error_type", "") or "")
            if error_type:
                payload["error_type"] = error_type
            logging.getLogger("backend.api.http").info(json.dumps(payload, separators=(",", ":")))
            tel = getattr(self, "_telemetry", None)
            if tel is not None:
                tel.route = self._route_shape()
                tel.route_name = str(getattr(self, "_matched_route_name", "") or "")
                tel.method = str(getattr(self, "command", "") or "")
                tel.payload_response_bytes = int(getattr(self, "_response_bytes", 0) or 0)
                tel.finalise()
                tel.emit()


        def _handle_client_disconnect(self, exc: BaseException) -> None:
            self._client_disconnected = True
            self.close_connection = True
            self._request_error_type = type(exc).__name__
            logging.getLogger("backend.api.http").info(
                "client_disconnect method=%s route=%s route_name=%s error_type=%s",
                str(getattr(self, "command", "") or ""),
                self._route_shape(),
                str(getattr(self, "_matched_route_name", "") or ""),
                type(exc).__name__,
            )

        def _cors_origin(self) -> str:
            origin = _normalize_origin_value(str(self.headers.get("Origin") or ""))
            if not origin:
                return ""
            if _origin_is_chrome_extension(origin):
                if (
                    self._is_assisted_apply_extension_path()
                    and origin in normalized_allowed_extension_origins
                ):
                    return origin
                return ""
            if allow_all_origins or origin in normalized_allowed_origins or _origin_is_loopback(origin):
                return origin
            return ""

        def _is_assisted_apply_extension_path(self) -> bool:
            segments = [item for item in (urlparse(self.path).path or "/").split("/") if item]
            if segments[:1] == ["v1"]:
                segments = segments[1:]
            return (
                segments[:2] == ["assisted-apply", "extension"]
                # The canonical bounded telemetry endpoint intentionally has
                # no user content. It is the only non-/extension Assisted
                # Apply route an exact extension origin may call.
                or segments == ["assisted-apply", "telemetry", "events"]
            )

        def _cors_headers(self) -> dict[str, str]:
            headers = {
                "Access-Control-Allow-Headers": "Authorization, Content-Type, X-Runr-Document-Grant",
                "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
                "Access-Control-Max-Age": "600",
                "Vary": "Origin",
            }
            allowed_origin = self._cors_origin()
            if allowed_origin:
                headers["Access-Control-Allow-Origin"] = allowed_origin
            return headers

        def _enforce_origin_policy(self) -> None:
            request_origin = _normalize_origin_value(str(self.headers.get("Origin") or ""))
            if request_origin and not self._cors_origin():
                raise PermissionError(f"Origin '{request_origin}' is not allowed.")

        def _send_json(self, payload, status: int = 200, *, headers: dict[str, str] | None = None) -> None:
            if getattr(self, "_client_disconnected", False) or getattr(self, "_response_started", False):
                return
            body = _json_bytes(payload)
            self._response_started = True
            self._response_status = int(status)
            self._response_bytes = len(body)
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                merged_headers = self._cors_headers()
                merged_headers.update(headers or {})
                for key, value in merged_headers.items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(body)
            except _CLIENT_DISCONNECT_ERRORS as exc:
                self._handle_client_disconnect(exc)

        def _send_no_content(
            self,
            status: int = HTTPStatus.NO_CONTENT,
            *,
            headers: dict[str, str] | None = None,
        ) -> None:
            if getattr(self, "_client_disconnected", False) or getattr(self, "_response_started", False):
                return
            self._response_started = True
            self._response_status = int(status)
            self._response_bytes = 0
            try:
                self.send_response(status)
                merged_headers = self._cors_headers()
                merged_headers.update(headers or {})
                for key, value in merged_headers.items():
                    self.send_header(key, value)
                self.end_headers()
            except _CLIENT_DISCONNECT_ERRORS as exc:
                self._handle_client_disconnect(exc)

        def _send_html(self, body: str, status: int = 200, *, headers: dict[str, str] | None = None) -> None:
            if getattr(self, "_client_disconnected", False) or getattr(self, "_response_started", False):
                return
            payload = str(body or "").encode("utf-8")
            self._response_started = True
            self._response_status = int(status)
            self._response_bytes = len(payload)
            try:
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                merged_headers = self._cors_headers()
                merged_headers.update(headers or {})
                for key, value in merged_headers.items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(payload)
            except _CLIENT_DISCONNECT_ERRORS as exc:
                self._handle_client_disconnect(exc)

        def _send_error(self, status: int, code: str, message: str, *, details=None, headers: dict[str, str] | None = None) -> None:
            payload = {"error": {"code": code, "message": message}}
            if details is not None:
                payload["error"]["details"] = details
            self._send_json(payload, status=status, headers=headers)
        def _send_error(self, status: int, code: str, message: str, *, details=None, headers: dict[str, str] | None = None) -> None:
            payload = {"error": {"code": code, "message": message}}
            if details is not None:
                payload["error"]["details"] = details
            self._send_json(payload, status=status, headers=headers)

        def _send_unavailable(self, message: str = "The API is temporarily unavailable. Please try again in a few seconds.") -> None:
            """Send a structured 503 response for API restart / overload."""
            self._send_error(HTTPStatus.SERVICE_UNAVAILABLE, "api_unavailable", message, headers={"Retry-After": "5"})

        def _send_timeout(self, message: str = "The request timed out.") -> None:
            """Send a structured 408 response."""
            self._send_error(HTTPStatus.REQUEST_TIMEOUT, "request_timeout", message)

        def _send_auth_error(self, message: str = "Authentication failed.") -> None:
            """Send a structured 401 response with WWW-Authenticate header."""
            self._send_error(HTTPStatus.UNAUTHORIZED, "authentication_failed", message, headers={"WWW-Authenticate": "Bearer"})

        def _send_cancelled(self, request_id: str = "") -> None:
            """Send a structured 499 response for client-cancelled requests."""
            payload = {"error": {"code": "request_cancelled", "message": "The request was cancelled by the client."}}
            if request_id:
                payload["error"]["request_id"] = request_id
            self._send_json(payload, status=499)

        def _send_quota_exceeded(self, exc: QuotaExceededError) -> None:
            self._send_json(
                {
                    "error": "quota_exceeded",
                    "quota_type": exc.quota_type,
                    "used": exc.used,
                    "limit": exc.limit,
                    "plan_id": exc.plan_id,
                    "upgrade_url": "/pricing",
                },
                status=HTTPStatus.PAYMENT_REQUIRED,
            )

        def _read_raw_body(self) -> bytes:
            cached_body = getattr(self, "_cached_raw_body", None)
            if cached_body is not None:
                return cached_body
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length) if content_length > 0 else b""
            self._cached_raw_body = raw_body
            return raw_body

        def _read_limited_body(self, *, max_bytes: int, request_label: str) -> bytes:
            raw_content_length = str(self.headers.get("Content-Length") or "").strip()
            if not raw_content_length:
                raise ValueError(f"{request_label} requires a Content-Length header.")
            try:
                content_length = int(raw_content_length)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{request_label} has an invalid Content-Length header.") from exc
            if content_length <= 0:
                raise ValueError(f"{request_label} requires a non-empty request body.")
            if content_length > max_bytes:
                remaining = content_length
                while remaining > 0:
                    chunk = self.rfile.read(min(remaining, 1024 * 1024))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                max_megabytes = max_bytes // (1024 * 1024)
                raise RequestBodyTooLargeError(
                    f"{request_label} request must be {max_megabytes} MB or smaller."
                )
            raw_body = self.rfile.read(content_length)
            if len(raw_body) != content_length:
                raise ConnectionResetError("client disconnected before request body was complete")
            return raw_body

        def _read_json_body(self):
            raw = self._read_raw_body()
            if not raw:
                return {}
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")
            return payload

        def _parse_request(self):
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            segments = _normalize_segments([segment for segment in path.split("/") if segment])
            query = parse_qs(parsed.query)
            return path, segments, query

        def _route_context(
            self,
            method: str,
            segments: list[str],
            query: Mapping[str, list[str]],
        ) -> ApiRouteContext:
            return ApiRouteContext(
                application=application,
                handler=self,
                method=method.upper(),
                segments=tuple(segments),
                query=query,
            )

        def _dispatch_route(
            self,
            method: str,
            segments: list[str],
            query: Mapping[str, list[str]],
            *,
            auth_required: bool,
        ) -> bool:
            return route_registry.dispatch(
                self._route_context(method, segments, query),
                auth_required=auth_required,
            )

        def _request_origin(self) -> str:
            forwarded_proto = str(self.headers.get("X-Forwarded-Proto") or "").strip()
            proto = forwarded_proto or ("https" if self.server.server_port == 443 else "http")
            host = str(self.headers.get("X-Forwarded-Host") or self.headers.get("Host") or "").strip()
            if not host:
                host = f"{self.server.server_name}:{self.server.server_port}"
            return f"{proto}://{host}"

        def _request_client_origin(self) -> str:
            return _normalize_origin_value(str(self.headers.get("Origin") or ""))

        def _bearer_token(self) -> str:
            return _extract_bearer_token(self.headers.get("Authorization", ""))

        def _frontend_origin(self) -> str:
            configured_origin = str(os.getenv("APP_FRONTEND_ORIGIN") or os.getenv("FRONTEND_ORIGIN") or "").strip()
            if configured_origin:
                return configured_origin.rstrip("/")
            return self._request_origin()

        def _request_api_prefix(self) -> str:
            parsed = urlparse(self.path)
            path = parsed.path or "/"
            if path == "/v1" or path.startswith("/v1/"):
                return "/v1"
            return ""

        def _tracker_google_callback_uri(self) -> str:
            configured_redirect_uri = str(tracker_google_oauth_metadata().get("redirect_uri") or "").strip()
            if configured_redirect_uri:
                return configured_redirect_uri
            return f"{self._request_origin()}{self._request_api_prefix()}/tracker/email-integration/google/callback"

        def _pagination_meta(self, *, limit: int, offset: int, returned: int) -> dict[str, int]:
            return {"limit": int(limit), "offset": int(offset), "returned": int(returned)}

        def _send_file(self, file_path: str, *, download_name: str = "") -> None:
            if getattr(self, "_client_disconnected", False) or getattr(self, "_response_started", False):
                return
            target = Path(file_path)
            if not target.exists() or not target.is_file():
                raise KeyError(f"Artifact file '{file_path}' not found.")
            body = target.read_bytes()
            content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self._response_started = True
            self._response_status = int(HTTPStatus.OK)
            self._response_bytes = len(body)
            try:
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header(
                    "Content-Disposition",
                    f'attachment; filename="{download_name or target.name}"',
                )
                for key, value in self._cors_headers().items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(body)
            except _CLIENT_DISCONNECT_ERRORS as exc:
                self._handle_client_disconnect(exc)

        def _send_bytes(self, body: bytes, *, content_type: str, download_name: str) -> None:
            if getattr(self, "_client_disconnected", False) or getattr(self, "_response_started", False):
                return
            self._response_started = True
            self._response_status = int(HTTPStatus.OK)
            self._response_bytes = len(body)
            try:
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
                for key, value in self._cors_headers().items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(body)
            except _CLIENT_DISCONNECT_ERRORS as exc:
                self._handle_client_disconnect(exc)

        def _auth_context(self):
            cached_context = getattr(self, "_cached_auth_context", None)
            if cached_context is not None:
                return cached_context
            token_value = _extract_bearer_token(self.headers.get("Authorization", ""))
            if not token_value:
                raise PermissionError("Missing bearer token.")
            context = _resolve_auth_context(application, token_value)
            if not getattr(context.user, "is_active", True):
                raise PermissionError("User is inactive.")
            logging.getLogger("backend.auth").info(
                "Authenticated %s request for %s via %s",
                self.command,
                getattr(context.user, "user_id", ""),
                getattr(context, "auth_method", "unknown"),
            )
            self._cached_auth_context = context
            return context

        def _require_identity(self):
            context = self._auth_context()
            return context.user, context.token

        def _require_clerk_identity(self):
            context = self._auth_context()
            if getattr(context, "auth_method", "") != "clerk_jwt":
                raise PermissionError("A current Runr web session is required.")
            authorized_party = _normalize_origin_value(
                str(getattr(context, "authorized_party", "") or "")
            )
            if not authorized_party or authorized_party not in normalized_allowed_origins:
                raise PermissionError("The Clerk session authorized party is not allowed.")
            return context.user, context.token

        def _require_scope(self, required_scope: str):
            context = self._auth_context()
            user, token = context.user, context.token
            if not application.user_has_scope(token, required_scope):
                raise PermissionError(f"Missing scope: {required_scope}")
            return user, token

        def _require_admin(self):
            context = self._auth_context()
            user, token = context.user, context.token
            if str(user.role or "").strip().lower() != "admin":
                raise PermissionError("Admin access required.")
            if not application.user_has_scope(token, TOKEN_SCOPE_ADMIN):
                raise PermissionError(f"Missing scope: {TOKEN_SCOPE_ADMIN}")
            return user, token

        def _require_workspace_access(self, *, workspace_id: str, required_scope: str):
            user, token = self._require_scope(required_scope)
            if not application.user_can_access_workspace(user, workspace_id):
                raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
            return user, token

        def _require_run_access(self, *, run, required_scope: str):
            user, token = self._require_scope(required_scope)
            if not application.user_can_access_run(user, run):
                raise PermissionError(f"Run access denied for '{run.id}'.")
            return user, token

        def _authorized_workspaces(self, user):
            return [workspace for workspace in application.list_workspaces() if application.user_can_access_workspace(user, workspace.id)]

        def _authorized_runs(self, user, *, limit: int, offset: int, status: str, workspace_id: str):
            runs = application.list_runs(limit=limit, offset=offset, status=status, workspace_id=workspace_id)
            return [run for run in runs if application.user_can_access_run(user, run)]

        def _send_unauthorized(self, message: str) -> None:
            self._send_error(
                status=HTTPStatus.UNAUTHORIZED,
                code="unauthorized",
                message=message,
                headers={"WWW-Authenticate": "Bearer"},
            )

        def do_OPTIONS(self):  # noqa: N802
            self._begin_request()
            try:
                self._enforce_origin_policy()
                self._response_status = int(HTTPStatus.NO_CONTENT)
                self._response_bytes = 0
                self.send_response(HTTPStatus.NO_CONTENT)
                for key, value in self._cors_headers().items():
                    self.send_header(key, value)
                self.end_headers()
            except _CLIENT_DISCONNECT_ERRORS as exc:
                self._handle_client_disconnect(exc)
            except PermissionError as exc:
                self._send_error(HTTPStatus.FORBIDDEN, "forbidden", str(exc))
            finally:
                self._finish_request_log()

        def do_GET(self):  # noqa: N802
            self._begin_request()
            try:
                self._enforce_origin_policy()
                _, segments, query = self._parse_request()

                if self._dispatch_route("GET", segments, query, auth_required=False):
                    return
                if self._dispatch_route("GET", segments, query, auth_required=True):
                    return

                self._send_error(HTTPStatus.NOT_FOUND, "not_found", "Route not found.")
            except _CLIENT_DISCONNECT_ERRORS as exc:
                self._handle_client_disconnect(exc)
            except PermissionError as exc:
                if _is_unauthorized_permission_error(exc):
                    self._send_unauthorized(str(exc))
                else:
                    self._send_error(HTTPStatus.FORBIDDEN, "forbidden", str(exc))
            except QuotaExceededError as exc:
                self._send_quota_exceeded(exc)
            except KeyError as exc:
                self._send_error(HTTPStatus.NOT_FOUND, "not_found", str(exc))
            except BackendValidationError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, exc.error_code, str(exc), details=dict(exc.details))
            except AtsExportBlockedError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, "ats_export_blocked", str(exc), details={"gate": exc.gate})
            except ValueError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, "bad_request", str(exc))
            except Exception as exc:
                self._request_error_type = type(exc).__name__
                self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", str(exc))
            finally:
                self._finish_request_log()

        def do_POST(self):  # noqa: N802
            self._begin_request()
            try:
                _, segments, query = self._parse_request()
                is_webhook_route = segments in (["webhooks", "clerk"], ["webhooks", "creem"])
                if not is_webhook_route:
                    self._enforce_origin_policy()

                if self._dispatch_route("POST", segments, query, auth_required=False):
                    return
                if self._dispatch_route("POST", segments, query, auth_required=True):
                    return

                self._read_json_body()
                self._send_error(HTTPStatus.NOT_FOUND, "not_found", "Route not found.")
            except _CLIENT_DISCONNECT_ERRORS as exc:
                self._handle_client_disconnect(exc)
            except PermissionError as exc:
                if _is_unauthorized_permission_error(exc):
                    self._send_unauthorized(str(exc))
                else:
                    self._send_error(HTTPStatus.FORBIDDEN, "forbidden", str(exc))
            except QuotaExceededError as exc:
                self._send_quota_exceeded(exc)
            except KeyError as exc:
                self._send_error(HTTPStatus.NOT_FOUND, "not_found", str(exc))
            except BackendValidationError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, exc.error_code, str(exc), details=dict(exc.details))
            except AtsExportBlockedError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, "ats_export_blocked", str(exc), details={"gate": exc.gate})
            except RequestBodyTooLargeError as exc:
                self._send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request_too_large", str(exc))
            except ValueError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, "bad_request", str(exc))
            except Exception as exc:
                self._request_error_type = type(exc).__name__
                self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", str(exc))
            finally:
                self._finish_request_log()

        def do_PUT(self):  # noqa: N802
            self._begin_request()
            try:
                self._enforce_origin_policy()
                _, segments, query = self._parse_request()
                if self._dispatch_route("PUT", segments, query, auth_required=False):
                    return
                if self._dispatch_route("PUT", segments, query, auth_required=True):
                    return

                self._read_json_body()
                self._send_error(HTTPStatus.NOT_FOUND, "not_found", "Route not found.")
            except _CLIENT_DISCONNECT_ERRORS as exc:
                self._handle_client_disconnect(exc)
            except PermissionError as exc:
                if _is_unauthorized_permission_error(exc):
                    self._send_unauthorized(str(exc))
                else:
                    self._send_error(HTTPStatus.FORBIDDEN, "forbidden", str(exc))
            except QuotaExceededError as exc:
                self._send_quota_exceeded(exc)
            except KeyError as exc:
                self._send_error(HTTPStatus.NOT_FOUND, "not_found", str(exc))
            except BackendValidationError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, exc.error_code, str(exc), details=dict(exc.details))
            except AtsExportBlockedError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, "ats_export_blocked", str(exc), details={"gate": exc.gate})
            except ValueError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, "bad_request", str(exc))
            except Exception as exc:
                self._request_error_type = type(exc).__name__
                self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", str(exc))
            finally:
                self._finish_request_log()

        def do_DELETE(self):  # noqa: N802
            self._begin_request()
            try:
                self._enforce_origin_policy()
                _, segments, query = self._parse_request()
                if self._dispatch_route("DELETE", segments, query, auth_required=False):
                    return
                if self._dispatch_route("DELETE", segments, query, auth_required=True):
                    return

                self._send_error(HTTPStatus.NOT_FOUND, "not_found", "Route not found.")
            except _CLIENT_DISCONNECT_ERRORS as exc:
                self._handle_client_disconnect(exc)
            except PermissionError as exc:
                if _is_unauthorized_permission_error(exc):
                    self._send_unauthorized(str(exc))
                else:
                    self._send_error(HTTPStatus.FORBIDDEN, "forbidden", str(exc))
            except QuotaExceededError as exc:
                self._send_quota_exceeded(exc)
            except KeyError as exc:
                self._send_error(HTTPStatus.NOT_FOUND, "not_found", str(exc))
            except BackendValidationError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, exc.error_code, str(exc), details=dict(exc.details))
            except AtsExportBlockedError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, "ats_export_blocked", str(exc), details={"gate": exc.gate})
            except ValueError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, "bad_request", str(exc))
            except Exception as exc:
                self._request_error_type = type(exc).__name__
                self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", str(exc))
            finally:
                self._finish_request_log()

        def log_message(self, format, *args):  # noqa: A003
            return

    return BackendApiHandler


def serve_api(
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    data_dir: str = ".backend_data",
    storage_backend: str = "sqlite",
) -> None:
    load_project_dotenv()
    validate_environment()
    application = create_backend(data_dir, storage_backend=storage_backend)
    allowed_origins, allow_all_origins = _parse_allowed_origins(os.getenv("BACKEND_ALLOWED_ORIGINS", ""))
    allowed_extension_origins = _parse_allowed_extension_origins(
        os.getenv("RUNR_ASSISTED_APPLY_EXTENSION_ORIGINS", "")
    )
    server = ThreadingHTTPServer(
        (host, int(port)),
        build_handler(
            application,
            allowed_origins=allowed_origins,
            allowed_extension_origins=allowed_extension_origins,
            allow_all_origins=allow_all_origins,
        ),
    )
    print(f"Unified backend API listening on http://{host}:{port}")
    server.serve_forever()
