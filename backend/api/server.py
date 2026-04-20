from __future__ import annotations

import base64
import io
import json
import mimetypes
import re
import zipfile
from copy import deepcopy
from datetime import datetime, timezone
from email.parser import BytesFeedParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

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
)
from backend.capabilities.tailored_documents.rendering import get_document_design_options
from backend.bootstrap import create_backend
from backend.domain.phase0_contracts import (
    normalize_candidate_asset_descriptor,
    normalize_rejected_job_review,
    phase0_contract_catalog,
)
from backend.domain.models import (
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
    utc_plus_seconds,
)


def _json_bytes(payload) -> bytes:
    return json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")


_EXPANDED_ARTIFACT_DELIMITER = "__item__"
_EXPANDED_ARTIFACT_SUFFIXES = {".csv", ".docx", ".json", ".md", ".pdf", ".txt", ".xlsx"}


def _artifact_download_url(run_id: str, artifact_id: str) -> str:
    return f"/v1/runs/{run_id}/artifacts/{artifact_id}/download"


def _file_timestamp_iso(path: Path, *, fallback: str) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
    except Exception:
        return str(fallback or "")


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
    target = Path(artifact.path)
    return artifact.path, (target.name or artifact.artifact_id)


# ---------------------------------------------------------------------------
# CV extraction helpers
# ---------------------------------------------------------------------------

def _extract_text_from_docx(data: bytes) -> str:
    """Extract plain text from a DOCX file using python-docx or a basic ZIP/XML fallback."""
    try:
        import docx  # type: ignore
        doc = docx.Document(io.BytesIO(data))
        return "\n".join(para.text for para in doc.paragraphs)
    except Exception:
        pass
    # Fallback: extract XML text nodes directly from the ZIP
    try:
        import zipfile
        import xml.etree.ElementTree as ET
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            with zf.open("word/document.xml") as f:
                tree = ET.parse(f)
                ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
                return " ".join(node.text for node in tree.iter(f"{{{ns}}}t") if node.text)
    except Exception:
        return ""


def _extract_text_from_pdf(data: bytes) -> str:
    """Extract plain text from a PDF using pypdf if available."""
    try:
        from pypdf import PdfReader  # type: ignore
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


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
        r"^(skills|core\s+competencies|competencies|technical\s+skills|key\s+skills)",
        re.IGNORECASE,
    )
    _EXP_HEADERS = re.compile(
        r"^(experience|work\s+experience|professional\s+experience|employment)",
        re.IGNORECASE,
    )

    sections: dict[str, list[str]] = {}
    current_section = "_preamble"
    sections[current_section] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if _SUMMARY_HEADERS.match(stripped):
            current_section = "summary"
            sections.setdefault(current_section, [])
        elif _SKILLS_HEADERS.match(stripped):
            current_section = "skills"
            sections.setdefault(current_section, [])
        elif _EXP_HEADERS.match(stripped):
            current_section = "experience"
            sections.setdefault(current_section, [])
        else:
            sections.setdefault(current_section, []).append(stripped)

    # ---- build result ----
    result: dict = {}

    summary_lines = sections.get("summary", [])
    if summary_lines:
        result["summary"] = " ".join(summary_lines[:6])  # cap at ~6 sentences

    skills_lines = sections.get("skills", [])
    if skills_lines:
        # Try to treat comma-separated lines as individual competencies
        competencies: list[str] = []
        for skill_line in skills_lines:
            for part in re.split(r"[,;|•·]", skill_line):
                part = part.strip(" .-")
                if part and len(part) < 60:
                    competencies.append(part)
        result["competencies"] = competencies[:20]  # cap at 20

    exp_lines = sections.get("experience", [])
    if exp_lines:
        result["experience_lines"] = exp_lines[:40]  # cap at 40 raw lines

    return result


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
        "workspace_type": workspace.workspace_type,
        "automation_flow": str(workspace.metadata.get("automation_flow") or workspace.settings.get("automation_flow") or ""),
        "settings": dict(workspace.settings),
        "feature_flags": workspace.feature_flags,
        "profiles": [profile.to_dict() for profile in workspace.profiles],
        "prompt_sets": [prompt_set.to_dict() for prompt_set in workspace.prompt_sets],
        "sources": [source.to_dict() for source in workspace.sources],
        "metadata": dict(workspace.metadata),
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
    }


def _workspace_option(workspace) -> dict:
    return {
        "id": workspace.id,
        "name": workspace.name,
        "workspace_type": workspace.workspace_type,
        "automation_flow": str(workspace.metadata.get("automation_flow") or workspace.settings.get("automation_flow") or ""),
    }


def _merge_profile_metadata(existing_profile: dict, profile_payload: dict, user) -> dict:
    merged = {
        "name": str(profile_payload.get("name") or existing_profile.get("name") or user.display_name or user.email.split("@")[0]),
        "role_title": str(profile_payload.get("role_title") or existing_profile.get("role_title") or ""),
        "email": str(profile_payload.get("email") or existing_profile.get("email") or user.email),
        "location": str(profile_payload.get("location") or existing_profile.get("location") or ""),
        "website": str(profile_payload.get("website") or existing_profile.get("website") or ""),
        "linkedin_url": str(profile_payload.get("linkedin_url") or existing_profile.get("linkedin_url") or ""),
        "github_url": str(profile_payload.get("github_url") or existing_profile.get("github_url") or ""),
        "avatar_url": str(profile_payload.get("avatar_url") or existing_profile.get("avatar_url") or ""),
        "photo_data_url": str(profile_payload.get("photo_data_url") or existing_profile.get("photo_data_url") or ""),
        "photo_path": str(profile_payload.get("photo_path") or existing_profile.get("photo_path") or ""),
        "summary": str(profile_payload.get("summary") or existing_profile.get("summary") or ""),
        "competencies": [
            str(item)
            for item in profile_payload.get("competencies", existing_profile.get("competencies") or [])
            if str(item).strip()
        ],
        "languages": [
            str(item)
            for item in profile_payload.get("languages", existing_profile.get("languages") or [])
            if str(item).strip()
        ],
        "recent_experience": [
            {
                "title": str(item.get("title") or ""),
                "company": str(item.get("company") or ""),
                "period": str(item.get("period") or ""),
            }
            for item in profile_payload.get("recent_experience", existing_profile.get("recent_experience") or [])
            if isinstance(item, dict)
        ],
    }
    if not merged["avatar_url"] and merged["photo_data_url"]:
        merged["avatar_url"] = merged["photo_data_url"]
    return merged


def _merge_document_metadata(existing_documents: dict, documents_payload: dict) -> dict:
    return {
        "generate_docx": bool(documents_payload.get("generate_docx", existing_documents.get("generate_docx", True))),
        "generate_pdf": bool(documents_payload.get("generate_pdf", existing_documents.get("generate_pdf", True))),
        "export_tracker": bool(documents_payload.get("export_tracker", existing_documents.get("export_tracker", True))),
        "export_package": bool(documents_payload.get("export_package", existing_documents.get("export_package", True))),
        "file_naming": str(documents_payload.get("file_naming") or existing_documents.get("file_naming") or "workspace_job_title"),
        "cv_template": str(documents_payload.get("cv_template") or existing_documents.get("cv_template") or "classic"),
        "cv_color_scheme": str(documents_payload.get("cv_color_scheme") or existing_documents.get("cv_color_scheme") or "classic_navy"),
        "cv_font": str(documents_payload.get("cv_font") or existing_documents.get("cv_font") or "Calibri"),
        "include_photo": bool(documents_payload.get("include_photo", existing_documents.get("include_photo", True))),
    }


def _build_run_input_overrides(user, payload: dict, *, workspace_settings: dict | None = None) -> dict:
    profile = dict((user.metadata or {}).get("profile") or {})
    documents = dict((user.metadata or {}).get("documents") or {})
    overrides = dict(payload.get("run_input_overrides") or {})
    workspace_settings = dict(workspace_settings or {})

    def workspace_has_value(key: str) -> bool:
        value = workspace_settings.get(key)
        return value not in (None, "", [], {})

    if profile.get("name") and not workspace_has_value("candidate_name"):
        overrides.setdefault("candidate_name", str(profile.get("name")))
    if profile.get("email") and not workspace_has_value("candidate_email"):
        overrides.setdefault("candidate_email", str(profile.get("email")))
    if profile.get("languages") and not workspace_has_value("languages"):
        overrides.setdefault("languages", [str(item) for item in profile.get("languages") or [] if str(item).strip()])

    if not workspace_has_value("cv_font"):
        overrides.setdefault("cv_font", str(documents.get("cv_font") or "Calibri"))
    if not workspace_has_value("cv_template"):
        overrides.setdefault("cv_template", str(documents.get("cv_template") or "classic"))
    if not workspace_has_value("cv_color_scheme"):
        overrides.setdefault("cv_color_scheme", str(documents.get("cv_color_scheme") or "classic_navy"))
    if not workspace_has_value("include_photo"):
        overrides.setdefault("include_photo", bool(documents.get("include_photo", True)))

    include_photo_enabled = workspace_settings.get("include_photo")
    if include_photo_enabled is None:
        include_photo_enabled = bool(documents.get("include_photo", True))
    if include_photo_enabled and not workspace_has_value("profile_image"):
        photo_path = str(profile.get("photo_path") or "")
        if photo_path:
            overrides.setdefault("profile_image", photo_path)
    elif not include_photo_enabled and not workspace_has_value("profile_image"):
        overrides["profile_image"] = ""

    return overrides


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
    referrals = [contact.to_dict() for contact in application.list_referral_contacts(user.user_id)]

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
    document_design_options = get_document_design_options()

    return {
        "profile": profile_section,
        "candidate_assets": _load_candidate_assets(user),
        "defaults": defaults,
        "documents": documents,
        "review_preferences": review_preferences,
        "referrals": referrals,
        "account": {
            "display_name": user.display_name,
            "email": user.email,
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


def _collect_authorized_runs(application, user, *, workspace_id: str = "") -> tuple[dict[str, object], list[object]]:
    workspaces = {
        workspace.id: workspace
        for workspace in application.list_workspaces()
        if application.user_can_access_workspace(user, workspace.id)
    }
    runs = [
        run
        for run in application.list_runs(limit=1000, offset=0, status="", workspace_id=workspace_id)
        if application.user_can_access_workspace(user, run.workspace_id)
    ]
    return workspaces, runs


def _collect_review_queue_entries(application, user, *, workspace_id: str = "", run_id: str = "") -> list[dict]:
    workspaces, runs = _collect_authorized_runs(application, user, workspace_id=workspace_id)
    referral_contacts = application.list_referral_contacts(user.user_id)
    entries: list[dict] = []
    for run in runs:
        if run_id and run.id != run_id:
            continue
        job_sets = application.list_job_sets(run.id)
        review_records = application.list_reviews(run_id=run.id, limit=1000, offset=0)
        reviews_by_job: dict[str, object] = {}
        for review in review_records:
            reviews_by_job.setdefault(review.job_id, review)
        artifact_count = len(application.list_artifacts(run.id))
        workspace = workspaces.get(run.workspace_id)
        preferred_keys = run.final_job_set_keys or list(job_sets.keys())
        for set_key in preferred_keys:
            for job in job_sets.get(set_key, []):
                review = reviews_by_job.get(job.job_id)
                status = str((review.status if review else "") or "waiting_review")
                review_meta = dict(review.metadata or {}) if review else {}
                matched_contacts = find_referral_contacts_for_company(referral_contacts, job.company)
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
                        # Tracker fields (REQ-09 / REQ-10)
                        "tracker_status": str(review_meta.get("tracker_status") or ""),
                        "email_confirmed": bool(review_meta.get("email_confirmed") or False),
                        "referral_contacts": [contact.to_dict() for contact in matched_contacts],
                        "has_referral_contact": bool(matched_contacts),
                        "referable_contact_count": sum(1 for contact in matched_contacts if contact.can_refer),
                    }
                )
    entries.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return entries


def _collect_tracker_entries(application, user) -> list[dict]:
    """Return all reviews that have been approved or have a tracker_status set."""
    workspaces, runs = _collect_authorized_runs(application, user)
    workspaces_map = {ws.id: ws for ws in application.list_workspaces()}
    entries: list[dict] = []
    for run in runs:
        job_sets = application.list_job_sets(run.id)
        review_records = application.list_reviews(run_id=run.id, limit=1000, offset=0)
        # build a fast job lookup
        jobs_by_id: dict[str, object] = {}
        for jobs in job_sets.values():
            for job in jobs:
                jobs_by_id[job.job_id] = job
        workspace = workspaces_map.get(run.workspace_id)
        for review in review_records:
            review_meta = dict(review.metadata or {})
            tracker_status = str(review_meta.get("tracker_status") or "")
            # include if approved decision OR has any tracker status already set
            if review.decision != "approved" and not tracker_status:
                continue
            if not tracker_status:
                tracker_status = "applied"
            job = jobs_by_id.get(review.job_id)
            entries.append(
                {
                    "review_id": review.review_id,
                    "run_id": review.run_id,
                    "workspace_id": run.workspace_id,
                    "workspace_name": workspace.name if workspace else run.workspace_id,
                    "job_id": review.job_id,
                    "title": job.title if job else "",
                    "company": job.company if job else "",
                    "apply_link": (job.apply_link or job.link or job.source_url) if job else "",
                    "location": job.location_raw if job else "",
                    "tracker_status": tracker_status,
                    "email_confirmed": bool(review_meta.get("email_confirmed") or False),
                    "rejection_note": str(review_meta.get("rejection_note") or ""),
                    "rejected_at": str(review_meta.get("rejected_at") or ""),
                    "updated_at": review.updated_at,
                    "run_finished_at": run.finished_at or run.updated_at,
                }
            )
    entries.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return entries


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


def _collect_artifact_entries(application, user, *, workspace_id: str = "", run_id: str = "") -> list[dict]:
    workspaces, runs = _collect_authorized_runs(application, user, workspace_id=workspace_id)
    entries: list[dict] = []
    for run in runs:
        if run_id and run.id != run_id:
            continue
        workspace = workspaces.get(run.workspace_id)
        artifacts = application.list_artifacts(run.id)
        for artifact in artifacts:
            entries.extend(_expand_artifact_entries(run, workspace, artifact))
    entries.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return entries


_CANDIDATE_ASSET_METADATA_KEY = "candidate_assets"


def _candidate_asset_download_url(asset_id: str) -> str:
    return f"/documents/assets/{asset_id}/download"


def _bulk_export_download_url(bundle_id: str) -> str:
    return f"/documents/bulk-exports/{bundle_id}/download"


def _candidate_asset_storage_dir(user) -> Path:
    return Path("user_config") / "candidate_assets" / str(user.user_id)


def _candidate_asset_path(user, asset_id: str, filename: str) -> Path:
    suffix = Path(filename or "").suffix or ".bin"
    root = _candidate_asset_storage_dir(user)
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{asset_id}{suffix.lower()}"


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
) -> dict:
    asset_id = f"asset_{uuid4().hex[:16]}"
    target_path = _candidate_asset_path(user, asset_id, filename)
    target_path.write_bytes(file_bytes)
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
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
            "path": str(target_path.resolve()),
            "download_url": _candidate_asset_download_url(asset_id),
            "mime_type": content_type,
            "extension": target_path.suffix.lower().lstrip("."),
            "metadata": {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "tags": list(tags or []),
            },
        },
    )


def _document_group_for_asset_kind(asset_kind: str) -> tuple[str, str]:
    normalized_kind = str(asset_kind or "").strip().lower()
    if normalized_kind in {"workspace_cv", "generated_cv"}:
        return "generated_cvs" if normalized_kind == "generated_cv" else "uploaded_cvs", (
            "Generated CVs" if normalized_kind == "generated_cv" else "Uploaded CVs"
        )
    if normalized_kind in {"cover_letter", "motivation_letter"}:
        return "generated_letters", "Generated Letters"
    if normalized_kind == "bundle_export":
        return "exported_bundles", "Exported Bundles"
    return "supporting_documents", "Supporting Documents"


def _document_id_for_artifact(run_id: str, artifact_id: str) -> str:
    return f"artifact::{run_id}::{artifact_id}"


def _document_id_for_candidate_asset(asset_id: str) -> str:
    return f"asset::{asset_id}"


def _artifact_asset_kind(entry: dict) -> str:
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


def _artifact_entry_to_document_item(entry: dict) -> dict:
    asset_kind = _artifact_asset_kind(entry)
    group_id, group_label = _document_group_for_asset_kind(asset_kind)
    return {
        "document_id": _document_id_for_artifact(entry["run_id"], entry["artifact_id"]),
        "asset_id": "",
        "asset_kind": asset_kind,
        "group_id": group_id,
        "group_label": group_label,
        "display_name": str(entry.get("file_name") or ""),
        "workspace_id": str(entry.get("workspace_id") or ""),
        "workspace_name": str(entry.get("workspace_name") or ""),
        "run_id": str(entry.get("run_id") or ""),
        "job_title": str(entry.get("job_title") or ""),
        "company": str(entry.get("company") or ""),
        "created_at": str(entry.get("created_at") or ""),
        "source_origin": "generated_run",
        "download_url": str(entry.get("download_url") or ""),
        "preview_url": str(entry.get("download_url") or ""),
        "relative_path": str(entry.get("relative_path") or ""),
        "content_type": str(entry.get("content_type") or ""),
        "tags": [],
        "is_generated": True,
    }


def _candidate_asset_to_document_item(asset: dict, workspace_names: dict[str, str]) -> dict:
    asset_kind = str(asset.get("asset_kind") or "uploaded_document")
    group_id, group_label = _document_group_for_asset_kind(asset_kind)
    workspace_id = str(asset.get("workspace_binding", {}).get("workspace_id") or "")
    metadata = dict(asset.get("metadata") or {})
    return {
        "document_id": _document_id_for_candidate_asset(str(asset.get("asset_id") or "")),
        "asset_id": str(asset.get("asset_id") or ""),
        "asset_kind": asset_kind,
        "group_id": group_id,
        "group_label": group_label,
        "display_name": str(asset.get("display_name") or ""),
        "workspace_id": workspace_id,
        "workspace_name": workspace_names.get(workspace_id, workspace_id),
        "run_id": str(asset.get("source", {}).get("run_id") or ""),
        "job_title": "",
        "company": "",
        "created_at": str(metadata.get("created_at") or ""),
        "source_origin": str(asset.get("source", {}).get("origin") or "upload"),
        "download_url": str(asset.get("file", {}).get("download_url") or ""),
        "preview_url": str(asset.get("file", {}).get("download_url") or ""),
        "relative_path": str(asset.get("file", {}).get("path") or ""),
        "content_type": str(asset.get("file", {}).get("mime_type") or ""),
        "tags": list(metadata.get("tags") or []),
        "is_generated": str(asset.get("source", {}).get("origin") or "upload") != "upload",
    }


def _collect_document_entries(
    application,
    user,
    *,
    workspace_id: str = "",
    run_id: str = "",
    asset_kind: str = "",
) -> list[dict]:
    workspaces = {
        workspace.id: workspace.name
        for workspace in application.list_workspaces()
        if application.user_can_access_workspace(user, workspace.id)
    }
    entries = [
        _artifact_entry_to_document_item(entry)
        for entry in _collect_artifact_entries(application, user, workspace_id=workspace_id, run_id=run_id)
    ]
    for asset in _load_candidate_assets(user):
        asset_workspace_id = str(asset.get("workspace_binding", {}).get("workspace_id") or "")
        if workspace_id and asset_workspace_id and asset_workspace_id != workspace_id:
            continue
        entries.append(_candidate_asset_to_document_item(asset, workspaces))
    if asset_kind:
        entries = [item for item in entries if str(item.get("asset_kind") or "").lower() == asset_kind.lower()]
    entries.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return entries


def _resolve_candidate_asset_download(user, asset_id: str) -> tuple[str, str]:
    for asset in _load_candidate_assets(user):
        if asset["asset_id"] != asset_id:
            continue
        file_path = str(asset.get("file", {}).get("path") or "")
        download_name = str(asset.get("display_name") or Path(file_path).name or asset_id)
        return file_path, download_name
    raise KeyError(f"Candidate asset '{asset_id}' not found.")


def _resolve_document_selection(application, user, document_id: str) -> tuple[str, str]:
    kind, _, remainder = str(document_id or "").partition("::")
    if kind == "artifact":
        run_id, _, artifact_id = remainder.partition("::")
        if not run_id or not artifact_id:
            raise KeyError(f"Document '{document_id}' not found.")
        return _resolve_artifact_download(application, run_id, artifact_id)
    if kind == "asset":
        return _resolve_candidate_asset_download(user, remainder)
    raise KeyError(f"Document '{document_id}' not found.")


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


def _create_bulk_export_bundle(application, user, document_ids: list[str], *, label: str = "") -> dict:
    if not document_ids:
        raise ValueError("At least one document is required for bulk export.")
    bundle_id = f"bundle_{uuid4().hex[:16]}"
    bundle_path = _candidate_asset_bundle_dir(user) / f"{bundle_id}.zip"
    written_count = 0
    used_names: set[str] = set()
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for document_id in document_ids:
            file_path, file_name = _resolve_document_selection(application, user, document_id)
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


def _collect_rejected_job_entries(application, user, *, workspace_id: str = "", run_id: str = "") -> list[dict]:
    workspaces, runs = _collect_authorized_runs(application, user, workspace_id=workspace_id)
    reason_labels = _rejection_reason_labels()
    entries: list[dict] = []
    for run in runs:
        if run_id and run.id != run_id:
            continue
        workspace = workspaces.get(run.workspace_id)
        reviews_by_job = {
            review.job_id: review
            for review in application.list_reviews(run_id=run.id, limit=1000, offset=0)
        }
        blobs = application.repositories.job_store.load_all_blobs(run.id)
        seen_job_ids: set[str] = set()
        for blob_key, value in blobs.items():
            if not str(blob_key).endswith("_rejected") or not isinstance(value, list):
                continue
            source_stage = str(blob_key).removesuffix("_rejected")
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
                            or payload.get("stage3_filter_reason")
                            or payload.get("reason_summary")
                            or (review.notes if review else "")
                        ),
                        "details": payload.get("local_filter_reasons")
                        or payload.get("stage3_filter_reasons")
                        or payload.get("details")
                        or [],
                        "source_stage": source_stage,
                        "updated_at": review.updated_at if review else run.updated_at,
                        "apply_link": payload.get("apply_link") or payload.get("link") or payload.get("source_url"),
                        "workspace_editor": f"/workspaces?edit={run.workspace_id}&focus="
                        f"{_rejected_focus_for_reason(review_meta.get('reason_code') or '')}",
                        "override_state": review_meta.get("rejection_override_state"),
                        "override_requested_at": review_meta.get("rejection_override_requested_at"),
                        "override_requested_by": review_meta.get("rejection_override_requested_by"),
                        "override_notes": review_meta.get("rejection_override_notes"),
                        "metadata": review_meta,
                    }
                )
                reason_code = normalized["rejection"]["reason_code"]
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
                        "requeue_run_id": str(review_meta.get("requeue_run_id") or ""),
                        "workspace_editor_url": f"/workspaces?edit={run.workspace_id}&focus={_rejected_focus_for_reason(reason_code)}",
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
                    "workspace_editor": f"/workspaces?edit={run.workspace_id}&focus=review",
                    "override_state": review_meta.get("rejection_override_state"),
                    "override_requested_at": review_meta.get("rejection_override_requested_at"),
                    "override_requested_by": review_meta.get("rejection_override_requested_by"),
                    "override_notes": review_meta.get("rejection_override_notes"),
                    "metadata": review_meta,
                }
            )
            reason_code = normalized["rejection"]["reason_code"]
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
                    "requeue_run_id": str(review_meta.get("requeue_run_id") or ""),
                    "workspace_editor_url": f"/workspaces?edit={run.workspace_id}&focus=review",
                    "can_requeue": _workflow_supports_requeue(application, run),
                }
            )
    entries.sort(key=lambda item: str(item.get("recorded_at") or item.get("override_requested_at") or ""), reverse=True)
    return entries


def _dashboard_payload(application, user) -> dict:
    workspaces, runs = _collect_authorized_runs(application, user)
    review_queue = _collect_review_queue_entries(application, user)
    workers = application.list_workers(limit=100, offset=0, status="")
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
            {"label": "Running Workers", "value": sum(1 for worker in workers if worker.status == "running")},
            {
                "label": "Jobs Waiting Review",
                "value": sum(1 for item in review_queue if item["status"] in {"waiting_review", "pending"}),
            },
            {"label": "Completed Today", "value": completed_today},
        ],
        "recent_runs": recent_runs,
    }


def _extract_bearer_token(header_value: str) -> str:
    value = str(header_value or "").strip()
    if not value.lower().startswith("bearer "):
        return ""
    return value[7:].strip()


def _normalize_segments(raw_segments: list[str]) -> list[str]:
    if raw_segments[:1] == ["v1"]:
        return raw_segments[1:]
    return raw_segments


def _parse_int_param(query: dict[str, list[str]], name: str, *, default: int, minimum: int = 0, maximum: int = 1000) -> int:
    raw_value = str((query.get(name) or [str(default)])[0]).strip()
    try:
        value = int(raw_value)
    except Exception as exc:
        raise ValueError(f"{name} must be an integer") from exc
    return max(minimum, min(maximum, value))


def build_handler(application):
    class BackendApiHandler(BaseHTTPRequestHandler):
        def _cors_headers(self) -> dict[str, str]:
            origin = str(self.headers.get("Origin") or "").strip()
            return {
                "Access-Control-Allow-Origin": origin or "*",
                "Access-Control-Allow-Headers": "Authorization, Content-Type",
                "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
                "Access-Control-Max-Age": "600",
                "Vary": "Origin",
            }

        def _send_json(self, payload, status: int = 200, *, headers: dict[str, str] | None = None) -> None:
            body = _json_bytes(payload)
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            merged_headers = self._cors_headers()
            merged_headers.update(headers or {})
            for key, value in merged_headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, body: str, status: int = 200, *, headers: dict[str, str] | None = None) -> None:
            payload = str(body or "").encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            merged_headers = self._cors_headers()
            merged_headers.update(headers or {})
            for key, value in merged_headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(payload)

        def _send_error(self, status: int, code: str, message: str, *, details=None, headers: dict[str, str] | None = None) -> None:
            payload = {"error": {"code": code, "message": message}}
            if details is not None:
                payload["error"]["details"] = details
            self._send_json(payload, status=status, headers=headers)

        def _read_json_body(self):
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length <= 0:
                return {}
            raw = self.rfile.read(content_length)
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

        def _request_origin(self) -> str:
            forwarded_proto = str(self.headers.get("X-Forwarded-Proto") or "").strip()
            proto = forwarded_proto or ("https" if self.server.server_port == 443 else "http")
            host = str(self.headers.get("X-Forwarded-Host") or self.headers.get("Host") or "").strip()
            if not host:
                host = f"{self.server.server_name}:{self.server.server_port}"
            return f"{proto}://{host}"

        def _request_api_prefix(self) -> str:
            parsed = urlparse(self.path)
            path = parsed.path or "/"
            if path == "/v1" or path.startswith("/v1/"):
                return "/v1"
            return ""

        def _tracker_google_callback_uri(self) -> str:
            return f"{self._request_origin()}{self._request_api_prefix()}/tracker/email-integration/google/callback"

        def _pagination_meta(self, *, limit: int, offset: int, returned: int) -> dict[str, int]:
            return {"limit": int(limit), "offset": int(offset), "returned": int(returned)}

        def _send_file(self, file_path: str, *, download_name: str = "") -> None:
            target = Path(file_path)
            if not target.exists() or not target.is_file():
                raise KeyError(f"Artifact file '{file_path}' not found.")
            body = target.read_bytes()
            content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
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

        def _require_identity(self):
            token_value = _extract_bearer_token(self.headers.get("Authorization", ""))
            if not token_value:
                raise PermissionError("Missing bearer token.")
            return application.authenticate_access_token(token_value)

        def _require_scope(self, required_scope: str):
            user, token = self._require_identity()
            if not application.user_has_scope(token, required_scope):
                raise PermissionError(f"Missing scope: {required_scope}")
            return user, token

        def _require_workspace_access(self, *, workspace_id: str, required_scope: str):
            user, token = self._require_scope(required_scope)
            if not application.user_can_access_workspace(user, workspace_id):
                raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
            return user, token

        def _authorized_workspaces(self, user):
            return [workspace for workspace in application.list_workspaces() if application.user_can_access_workspace(user, workspace.id)]

        def _authorized_runs(self, user, *, limit: int, offset: int, status: str, workspace_id: str):
            runs = application.list_runs(limit=limit, offset=offset, status=status, workspace_id=workspace_id)
            return [run for run in runs if application.user_can_access_workspace(user, run.workspace_id)]

        def _send_unauthorized(self, message: str) -> None:
            self._send_error(
                status=HTTPStatus.UNAUTHORIZED,
                code="unauthorized",
                message=message,
                headers={"WWW-Authenticate": "Bearer"},
            )

        def do_OPTIONS(self):  # noqa: N802
            self.send_response(HTTPStatus.NO_CONTENT)
            for key, value in self._cors_headers().items():
                self.send_header(key, value)
            self.end_headers()

        def do_GET(self):  # noqa: N802
            try:
                _, segments, query = self._parse_request()

                if not segments:
                    self._send_json({"service": "unified-backend-api", "status": "ok"})
                    return
                if segments == ["health"]:
                    self._send_json({"status": "ok"})
                    return
                if segments == ["tracker", "email-integration", "google", "callback"]:
                    state = str((query.get("state") or [""])[0]).strip()
                    user_id, state_nonce = _parse_tracker_google_oauth_state(state)
                    if not user_id or not state_nonce:
                        self._send_html(
                            tracker_google_oauth_callback_message(
                                success=False,
                                message="The Google authorization callback is missing a valid tracker state.",
                            ),
                            status=HTTPStatus.BAD_REQUEST,
                        )
                        return
                    try:
                        user = application.get_user(user_id)
                    except KeyError:
                        self._send_html(
                            tracker_google_oauth_callback_message(
                                success=False,
                                message="The tracker user for this Google authorization request no longer exists.",
                            ),
                            status=HTTPStatus.NOT_FOUND,
                        )
                        return
                    current_config = _get_tracker_email_config(user)
                    if not tracker_google_oauth_state_is_valid(current_config, expected_state=state_nonce):
                        self._send_html(
                            tracker_google_oauth_callback_message(
                                success=False,
                                message="This Google authorization request is expired or no longer valid.",
                            ),
                            status=HTTPStatus.BAD_REQUEST,
                        )
                        return
                    provider_error = str((query.get("error") or [""])[0]).strip()
                    if provider_error:
                        failed_config = mark_google_tracker_authorization_error(
                            current_config,
                            error_message=f"Google authorization failed: {provider_error}",
                        )
                        _persist_tracker_email_config(application, user, failed_config)
                        self._send_html(
                            tracker_google_oauth_callback_message(
                                success=False,
                                message=f"Google authorization failed: {provider_error}",
                            ),
                            status=HTTPStatus.BAD_REQUEST,
                        )
                        return
                    code = str((query.get("code") or [""])[0]).strip()
                    if not code:
                        failed_config = mark_google_tracker_authorization_error(
                            current_config,
                            error_message="Google did not return an authorization code.",
                        )
                        _persist_tracker_email_config(application, user, failed_config)
                        self._send_html(
                            tracker_google_oauth_callback_message(
                                success=False,
                                message="Google did not return an authorization code.",
                            ),
                            status=HTTPStatus.BAD_REQUEST,
                        )
                        return
                    try:
                        token_payload = exchange_google_tracker_oauth_code(
                            code=code,
                            redirect_uri=str(current_config.get("oauth_redirect_uri") or self._tracker_google_callback_uri()),
                        )
                        access_token = str(token_payload.get("access_token") or "").strip()
                        refresh_token = str(token_payload.get("refresh_token") or "").strip() or _resolve_tracker_email_refresh_token(
                            application,
                            current_config,
                        )
                        if not access_token:
                            raise ValueError("Google did not return an access token.")
                        if not refresh_token:
                            raise ValueError(
                                "Google did not return a refresh token. Disconnect and authorize again."
                            )
                        profile_payload = fetch_google_tracker_profile(access_token=access_token)
                        email_address = str(profile_payload.get("emailAddress") or current_config.get("email_address") or "").strip()
                        updated_config = complete_google_tracker_authorization(
                            current_config,
                            email_address=email_address,
                        )
                        updated_config["access_token_secret_id"] = _upsert_tracker_email_access_token_secret(
                            application,
                            user,
                            updated_config,
                            access_token,
                        )
                        updated_config["refresh_token_secret_id"] = _upsert_tracker_email_refresh_token_secret(
                            application,
                            user,
                            updated_config,
                            refresh_token,
                        )
                        expires_in = int(token_payload.get("expires_in") or 3600)
                        updated_config["access_token_expires_at"] = utc_plus_seconds(expires_in)
                        _persist_tracker_email_config(application, user, updated_config)
                        self._send_html(
                            tracker_google_oauth_callback_message(
                                success=True,
                                message=f"{email_address or 'Your Gmail account'} is now connected to the tracker.",
                            ),
                            status=HTTPStatus.OK,
                        )
                        return
                    except ValueError as exc:
                        failed_config = mark_google_tracker_authorization_error(current_config, error_message=str(exc))
                        _persist_tracker_email_config(application, user, failed_config)
                        self._send_html(
                            tracker_google_oauth_callback_message(success=False, message=str(exc)),
                            status=HTTPStatus.BAD_REQUEST,
                        )
                        return
                if segments == ["auth", "me"]:
                    user, token = self._require_identity()
                    self._send_json({"user": user.to_dict(), "token": token.to_public_dict()})
                    return
                if segments == ["dashboard"]:
                    user, _ = self._require_identity()
                    self._send_json(_dashboard_payload(application, user))
                    return
                if segments == ["settings"]:
                    user, _ = self._require_identity()
                    self._send_json(_build_settings_payload(application, user))
                    return
                if segments == ["referrals"]:
                    user, _ = self._require_identity()
                    limit = _parse_int_param(query, "limit", default=100, maximum=1000)
                    offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                    contacts = application.list_referral_contacts(user.user_id)
                    paged_contacts = contacts[offset : offset + limit]
                    self._send_json(
                        {
                            "contacts": [contact.to_dict() for contact in paged_contacts],
                            "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(paged_contacts)),
                        }
                    )
                    return
                if segments[:1] == ["referrals"] and len(segments) == 2:
                    user, _ = self._require_identity()
                    self._send_json(application.get_referral_contact(user.user_id, segments[1]).to_dict())
                    return
                if segments == ["cv"]:
                    user, _ = self._require_identity()
                    metadata = dict(user.metadata or {})
                    cv_text = str(metadata.get("cv_text") or "")
                    # fall back to disk file if metadata not populated yet
                    if not cv_text:
                        cv_path = Path("user_config") / "cv_master.txt"
                        if cv_path.exists():
                            try:
                                cv_text = cv_path.read_text(encoding="utf-8")
                            except Exception:
                                cv_text = ""
                    self._send_json({"cv_text": cv_text, "char_count": len(cv_text)})
                    return
                if segments == ["users"]:
                    self._require_scope(TOKEN_SCOPE_USERS_READ)
                    limit = _parse_int_param(query, "limit", default=50, maximum=500)
                    offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                    users = application.list_users()
                    paged_users = users[offset : offset + limit]
                    self._send_json(
                        {
                            "users": [user.to_dict() for user in paged_users],
                            "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(paged_users)),
                        }
                    )
                    return
                if segments[:1] == ["users"] and len(segments) == 2:
                    self._require_scope(TOKEN_SCOPE_USERS_READ)
                    self._send_json(application.get_user(segments[1]).to_dict())
                    return
                if segments[:1] == ["users"] and len(segments) == 3 and segments[2] == "tokens":
                    self._require_scope(TOKEN_SCOPE_USERS_READ)
                    limit = _parse_int_param(query, "limit", default=100, maximum=500)
                    offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                    tokens = [
                        token.to_public_dict()
                        for token in application.list_api_tokens(
                            user_id=segments[1],
                            include_inactive=True,
                            limit=limit,
                            offset=offset,
                        )
                    ]
                    self._send_json(
                        {
                            "user_id": segments[1],
                            "tokens": tokens,
                            "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(tokens)),
                        }
                    )
                    return
                if segments == ["tokens"]:
                    self._require_scope(TOKEN_SCOPE_USERS_READ)
                    user_id = str((query.get("user_id") or [""])[0]).strip()
                    include_inactive = str((query.get("include_inactive") or ["false"])[0]).strip().lower() in {"1", "true", "yes"}
                    limit = _parse_int_param(query, "limit", default=100, maximum=500)
                    offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                    tokens = [
                        token.to_public_dict()
                        for token in application.list_api_tokens(
                            user_id=user_id,
                            include_inactive=include_inactive,
                            limit=limit,
                            offset=offset,
                        )
                    ]
                    self._send_json(
                        {
                            "tokens": tokens,
                            "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(tokens)),
                        }
                    )
                    return
                if segments == ["secrets"]:
                    user, _ = self._require_scope(TOKEN_SCOPE_SECRETS_READ)
                    workspace_id = str((query.get("workspace_id") or [""])[0])
                    limit = _parse_int_param(query, "limit", default=100, maximum=500)
                    offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                    if workspace_id and not application.user_can_access_workspace(user, workspace_id):
                        raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
                    secrets = [
                        secret.to_public_dict()
                        for secret in application.list_secrets(workspace_id=workspace_id, limit=limit, offset=offset)
                    ]
                    self._send_json(
                        {
                            "secrets": secrets,
                            "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(secrets)),
                        }
                    )
                    return
                if segments[:1] == ["secrets"] and len(segments) == 2:
                    user, _ = self._require_scope(TOKEN_SCOPE_SECRETS_READ)
                    secret = application.get_secret(segments[1])
                    if secret.workspace_id and not application.user_can_access_workspace(user, secret.workspace_id):
                        raise PermissionError(f"Workspace access denied for '{secret.workspace_id}'.")
                    self._send_json(secret.to_public_dict())
                    return
                if segments == ["workspaces"]:
                    user, _ = self._require_scope(TOKEN_SCOPE_WORKSPACES_READ)
                    limit = _parse_int_param(query, "limit", default=50, maximum=500)
                    offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                    workspaces = self._authorized_workspaces(user)
                    paged_workspaces = workspaces[offset : offset + limit]
                    self._send_json(
                        {
                            "workspaces": [_workspace_summary(item) for item in paged_workspaces],
                            "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(paged_workspaces)),
                        }
                    )
                    return
                if segments[:1] == ["workspaces"] and len(segments) == 2:
                    self._require_workspace_access(workspace_id=segments[1], required_scope=TOKEN_SCOPE_WORKSPACES_READ)
                    self._send_json(application.get_workspace(segments[1]).to_dict())
                    return
                if segments == ["workspace-builder", "catalog"]:
                    self._require_scope(TOKEN_SCOPE_WORKSPACES_READ)
                    self._send_json(application.get_workspace_builder_catalog())
                    return
                if segments == ["workflow-templates"]:
                    self._require_scope(TOKEN_SCOPE_TEMPLATES_READ)
                    limit = _parse_int_param(query, "limit", default=50, maximum=500)
                    offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                    templates = application.list_workflow_templates()
                    paged_templates = templates[offset : offset + limit]
                    self._send_json(
                        {
                            "workflow_templates": [_workflow_template_summary(item) for item in paged_templates],
                            "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(paged_templates)),
                        }
                    )
                    return
                if segments[:1] == ["workflow-templates"] and len(segments) == 2:
                    self._require_scope(TOKEN_SCOPE_TEMPLATES_READ)
                    self._send_json(application.get_workflow_template(segments[1]).to_dict())
                    return
                if segments == ["connectors"]:
                    self._require_scope(TOKEN_SCOPE_TEMPLATES_READ)
                    self._send_json({"connectors": [_component_summary(item) for item in application.list_connectors()]})
                    return
                if segments == ["generations"]:
                    self._require_scope(TOKEN_SCOPE_TEMPLATES_READ)
                    self._send_json({"generations": [_component_summary(item) for item in application.list_generations()]})
                    return
                if segments == ["renderers"]:
                    self._require_scope(TOKEN_SCOPE_TEMPLATES_READ)
                    self._send_json({"renderers": [_component_summary(item) for item in application.list_renderers()]})
                    return
                if segments == ["runs"]:
                    user, _ = self._require_scope(TOKEN_SCOPE_RUNS_READ)
                    limit = _parse_int_param(query, "limit", default=50, maximum=500)
                    offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                    status = str((query.get("status") or [""])[0])
                    workspace_id = str((query.get("workspace_id") or [""])[0])
                    if workspace_id and not application.user_can_access_workspace(user, workspace_id):
                        raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
                    runs = self._authorized_runs(user, limit=limit, offset=offset, status=status, workspace_id=workspace_id)
                    self._send_json(
                        {
                            "runs": [_run_summary(item) for item in runs],
                            "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(runs)),
                        }
                    )
                    return
                if segments == ["review-queue"]:
                    user, _ = self._require_identity()
                    limit = _parse_int_param(query, "limit", default=100, maximum=1000)
                    offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                    workspace_id = str((query.get("workspace_id") or [""])[0]).strip()
                    run_id = str((query.get("run_id") or [""])[0]).strip()
                    status = str((query.get("status") or [""])[0]).strip().lower()
                    if workspace_id and not application.user_can_access_workspace(user, workspace_id):
                        raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
                    entries = _collect_review_queue_entries(application, user, workspace_id=workspace_id, run_id=run_id)
                    if status:
                        entries = [item for item in entries if str(item.get("status") or "").lower() == status]
                    paged_entries = entries[offset : offset + limit]
                    self._send_json(
                        {
                            "items": paged_entries,
                            "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(paged_entries)),
                        }
                    )
                    return
                if segments == ["tracker"]:
                    user, _ = self._require_identity()
                    entries = _collect_tracker_entries(application, user)
                    self._send_json(
                        {
                            "items": entries,
                            "meta": self._pagination_meta(limit=len(entries), offset=0, returned=len(entries)),
                        }
                    )
                    return
                if segments == ["tracker", "email-integration"]:
                    user, _ = self._require_identity()
                    self._send_json(_tracker_email_integration_payload(application, user), status=HTTPStatus.OK)
                    return
                if segments == ["contracts", "phase0"]:
                    self._require_identity()
                    self._send_json(phase0_contract_catalog(), status=HTTPStatus.OK)
                    return
                if segments == ["documents"]:
                    user, _ = self._require_scope(TOKEN_SCOPE_ARTIFACTS_READ)
                    limit = _parse_int_param(query, "limit", default=100, maximum=1000)
                    offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                    workspace_id = str((query.get("workspace_id") or [""])[0]).strip()
                    run_id = str((query.get("run_id") or [""])[0]).strip()
                    asset_kind = str((query.get("asset_kind") or [""])[0]).strip().lower()
                    group_id = str((query.get("group_id") or [""])[0]).strip().lower()
                    if workspace_id and not application.user_can_access_workspace(user, workspace_id):
                        raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
                    entries = _collect_document_entries(
                        application,
                        user,
                        workspace_id=workspace_id,
                        run_id=run_id,
                        asset_kind=asset_kind,
                    )
                    if group_id:
                        entries = [item for item in entries if str(item.get("group_id") or "").lower() == group_id]
                    paged_entries = entries[offset : offset + limit]
                    self._send_json(
                        {
                            "documents": paged_entries,
                            "groups": [
                                {
                                    "group_id": group_key,
                                    "group_label": group_items[0]["group_label"],
                                    "count": len(group_items),
                                }
                                for group_key, group_items in {
                                    key: [item for item in entries if item["group_id"] == key]
                                    for key in sorted({item["group_id"] for item in entries})
                                }.items()
                            ],
                            "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(paged_entries)),
                        }
                    )
                    return
                if segments[:2] == ["documents", "assets"] and len(segments) == 4 and segments[3] == "download":
                    user, _ = self._require_scope(TOKEN_SCOPE_ARTIFACTS_READ)
                    file_path, download_name = _resolve_candidate_asset_download(user, segments[2])
                    self._send_file(file_path, download_name=download_name)
                    return
                if segments[:2] == ["documents", "bulk-exports"] and len(segments) == 4 and segments[3] == "download":
                    user, _ = self._require_scope(TOKEN_SCOPE_ARTIFACTS_READ)
                    bundle_path = _candidate_asset_bundle_dir(user) / f"{segments[2]}.zip"
                    self._send_file(str(bundle_path), download_name=bundle_path.name)
                    return
                if segments == ["rejected-jobs"]:
                    user, _ = self._require_scope(TOKEN_SCOPE_REVIEWS_READ)
                    limit = _parse_int_param(query, "limit", default=100, maximum=1000)
                    offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                    workspace_id = str((query.get("workspace_id") or [""])[0]).strip()
                    run_id = str((query.get("run_id") or [""])[0]).strip()
                    if workspace_id and not application.user_can_access_workspace(user, workspace_id):
                        raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
                    entries = _collect_rejected_job_entries(application, user, workspace_id=workspace_id, run_id=run_id)
                    paged_entries = entries[offset : offset + limit]
                    self._send_json(
                        {
                            "items": paged_entries,
                            "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(paged_entries)),
                        }
                    )
                    return
                if segments == ["artifacts"]:
                    user, _ = self._require_scope(TOKEN_SCOPE_ARTIFACTS_READ)
                    limit = _parse_int_param(query, "limit", default=100, maximum=1000)
                    offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                    workspace_id = str((query.get("workspace_id") or [""])[0]).strip()
                    run_id = str((query.get("run_id") or [""])[0]).strip()
                    artifact_type = str((query.get("artifact_type") or [""])[0]).strip().lower()
                    if workspace_id and not application.user_can_access_workspace(user, workspace_id):
                        raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
                    entries = _collect_artifact_entries(application, user, workspace_id=workspace_id, run_id=run_id)
                    if artifact_type:
                        entries = [item for item in entries if str(item.get("artifact_type") or "").lower() == artifact_type]
                    paged_entries = entries[offset : offset + limit]
                    self._send_json(
                        {
                            "artifacts": paged_entries,
                            "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(paged_entries)),
                        }
                    )
                    return
                if segments[:1] == ["runs"] and len(segments) == 2:
                    run = application.get_run(segments[1])
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_RUNS_READ)
                    self._send_json(run.to_dict())
                    return
                if segments[:1] == ["runs"] and len(segments) == 3 and segments[2] == "jobs":
                    run = application.get_run(segments[1])
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_RUNS_READ)
                    job_sets = application.list_job_sets(segments[1])
                    self._send_json({"run_id": segments[1], "job_sets": {key: [job.to_dict() for job in jobs] for key, jobs in job_sets.items()}})
                    return
                if segments[:1] == ["runs"] and len(segments) == 4 and segments[2] == "jobs":
                    run = application.get_run(segments[1])
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_RUNS_READ)
                    jobs = application.get_job_set(segments[1], segments[3])
                    self._send_json({"run_id": segments[1], "set_key": segments[3], "jobs": [job.to_dict() for job in jobs]})
                    return
                if segments[:1] == ["runs"] and len(segments) == 3 and segments[2] == "artifacts":
                    run = application.get_run(segments[1])
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_ARTIFACTS_READ)
                    artifacts = application.list_artifacts(segments[1])
                    self._send_json({"run_id": segments[1], "artifacts": [artifact.to_dict() for artifact in artifacts]})
                    return
                if segments[:1] == ["runs"] and len(segments) == 4 and segments[2] == "artifacts":
                    run = application.get_run(segments[1])
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_ARTIFACTS_READ)
                    self._send_json(application.get_artifact(segments[1], segments[3]).to_dict())
                    return
                if segments[:1] == ["runs"] and len(segments) == 5 and segments[2] == "artifacts" and segments[4] == "download":
                    run = application.get_run(segments[1])
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_ARTIFACTS_READ)
                    file_path, download_name = _resolve_artifact_download(application, segments[1], segments[3])
                    self._send_file(file_path, download_name=download_name)
                    return
                if segments[:1] == ["runs"] and len(segments) == 3 and segments[2] == "reviews":
                    run = application.get_run(segments[1])
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_REVIEWS_READ)
                    limit = _parse_int_param(query, "limit", default=100, maximum=500)
                    offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                    reviews = application.list_reviews(run_id=segments[1], limit=limit, offset=offset)
                    self._send_json(
                        {
                            "run_id": segments[1],
                            "reviews": [review.to_dict() for review in reviews],
                            "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(reviews)),
                        }
                    )
                    return
                if segments == ["workers"]:
                    self._require_scope(TOKEN_SCOPE_WORKER_EXECUTE)
                    limit = _parse_int_param(query, "limit", default=50, maximum=500)
                    offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                    status = str((query.get("status") or [""])[0]).strip()
                    workers = application.list_workers(limit=limit, offset=offset, status=status)
                    self._send_json(
                        {
                            "workers": [worker.to_dict() for worker in workers],
                            "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(workers)),
                        }
                    )
                    return
                if segments[:1] == ["workers"] and len(segments) == 2:
                    self._require_scope(TOKEN_SCOPE_WORKER_EXECUTE)
                    self._send_json(application.get_worker(segments[1]).to_dict())
                    return
                if segments[:1] == ["runs"] and len(segments) == 4 and segments[2] == "reviews":
                    review = application.get_review(segments[3])
                    run = application.get_run(review.run_id)
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_REVIEWS_READ)
                    if review.run_id != segments[1]:
                        self._send_error(HTTPStatus.NOT_FOUND, "not_found", "Review not found for run.")
                        return
                    self._send_json(review.to_dict())
                    return

                self._send_error(HTTPStatus.NOT_FOUND, "not_found", "Route not found.")
            except PermissionError as exc:
                if "Missing bearer token" in str(exc) or "Invalid or expired access token" in str(exc):
                    self._send_unauthorized(str(exc))
                else:
                    self._send_error(HTTPStatus.FORBIDDEN, "forbidden", str(exc))
            except KeyError as exc:
                self._send_error(HTTPStatus.NOT_FOUND, "not_found", str(exc))
            except ValueError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, "bad_request", str(exc))
            except Exception as exc:
                self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", str(exc))

        def do_POST(self):  # noqa: N802
            try:
                _, segments, query = self._parse_request()

                # ---- CV upload (multipart/form-data — must be handled before JSON body read) ----
                if segments == ["documents", "upload"]:
                    user, _ = self._require_identity()
                    content_type_header = str(self.headers.get("Content-Type") or "")
                    if "multipart/form-data" not in content_type_header:
                        raise ValueError("documents/upload requires multipart/form-data content type")
                    content_length = int(self.headers.get("Content-Length", "0"))
                    raw_body = self.rfile.read(content_length) if content_length > 0 else b""
                    filename, file_bytes = _parse_multipart_file(content_type_header, raw_body)
                    if not file_bytes:
                        raise ValueError("No file found in multipart body. Ensure the form field has a filename.")
                    asset_kind = str((query.get("asset_kind") or ["uploaded_document"])[0]).strip() or "uploaded_document"
                    workspace_id = str((query.get("workspace_id") or [""])[0]).strip()
                    if workspace_id and not application.user_can_access_workspace(user, workspace_id):
                        raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
                    display_name = str((query.get("display_name") or [filename])[0]).strip() or filename
                    asset = _store_candidate_asset_upload(
                        application,
                        user,
                        filename=filename,
                        file_bytes=file_bytes,
                        asset_kind=asset_kind,
                        display_name=display_name,
                        workspace_id=workspace_id,
                        role=asset_kind,
                        tags=[asset_kind],
                    )
                    self._send_json({"asset": asset}, status=HTTPStatus.CREATED)
                    return
                if segments == ["cv-upload"]:
                    user, _ = self._require_identity()
                    content_type_header = str(self.headers.get("Content-Type") or "")
                    if "multipart/form-data" not in content_type_header:
                        raise ValueError("cv-upload requires multipart/form-data content type")
                    content_length = int(self.headers.get("Content-Length", "0"))
                    raw_body = self.rfile.read(content_length) if content_length > 0 else b""
                    filename, file_bytes = _parse_multipart_file(content_type_header, raw_body)
                    if not file_bytes:
                        raise ValueError("No file found in multipart body. Ensure the form field has a filename.")
                    ext = Path(filename).suffix.lower() if filename else ".txt"
                    if ext == ".docx":
                        cv_text = _extract_text_from_docx(file_bytes)
                    elif ext == ".pdf":
                        cv_text = _extract_text_from_pdf(file_bytes)
                    else:
                        # .txt or unknown — try UTF-8, fall back to latin-1
                        try:
                            cv_text = file_bytes.decode("utf-8")
                        except UnicodeDecodeError:
                            cv_text = file_bytes.decode("latin-1")
                    if not cv_text.strip():
                        raise ValueError(f"Could not extract any text from uploaded file '{filename}'.")
                    # Save to disk (for legacy pipeline compatibility)
                    cv_save_path = Path("user_config") / "cv_master.txt"
                    cv_save_path.parent.mkdir(parents=True, exist_ok=True)
                    cv_save_path.write_text(cv_text, encoding="utf-8")
                    existing_assets = [
                        asset
                        for asset in _load_candidate_assets(user)
                        if not (
                            str(asset.get("asset_kind") or "") == "workspace_cv"
                            and not str(asset.get("workspace_binding", {}).get("workspace_id") or "").strip()
                        )
                    ]
                    user = _persist_candidate_assets(application, user, existing_assets)
                    uploaded_asset = _store_candidate_asset_upload(
                        application,
                        user,
                        filename=filename,
                        file_bytes=file_bytes,
                        asset_kind="workspace_cv",
                        display_name=filename or "Workspace CV",
                        role="workspace_cv",
                        tags=["cv", "workspace_cv"],
                    )
                    # Persist in user metadata
                    user = application.get_user(user.user_id)
                    metadata = dict(user.metadata or {})
                    metadata["cv_text"] = cv_text
                    user.metadata = metadata
                    user.updated_at = datetime.now(timezone.utc).isoformat()
                    application.repositories.auth_repository.upsert_user(user)
                    # Parse heuristic sections for frontend pre-fill
                    parsed = _parse_cv_sections(cv_text)
                    self._send_json(
                        {
                            "cv_text": cv_text,
                            "char_count": len(cv_text),
                            "filename": filename,
                            "asset": uploaded_asset,
                            "parsed": parsed,
                        },
                        status=HTTPStatus.CREATED,
                    )
                    return
                if segments == ["profile-photo-upload"]:
                    user, _ = self._require_identity()
                    content_type_header = str(self.headers.get("Content-Type") or "")
                    if "multipart/form-data" not in content_type_header:
                        raise ValueError("profile-photo-upload requires multipart/form-data content type")
                    content_length = int(self.headers.get("Content-Length", "0"))
                    raw_body = self.rfile.read(content_length) if content_length > 0 else b""
                    filename, file_bytes = _parse_multipart_file(content_type_header, raw_body)
                    if not file_bytes:
                        raise ValueError("No file found in multipart body. Ensure the form field has a filename.")
                    if len(file_bytes) > 2 * 1024 * 1024:
                        raise ValueError("Profile photo must be 2MB or smaller.")
                    extension = _guess_image_extension(filename, file_bytes)
                    if extension not in {".png", ".jpg"}:
                        raise ValueError("Profile photo must be a PNG or JPG image.")
                    photo_path, photo_data_url = _store_profile_photo(user, file_bytes, extension)
                    metadata = dict(user.metadata or {})
                    profile = _merge_profile_metadata(dict(metadata.get("profile") or {}), {}, user)
                    profile["photo_path"] = photo_path
                    profile["photo_data_url"] = photo_data_url
                    if not profile.get("avatar_url"):
                        profile["avatar_url"] = photo_data_url
                    metadata["profile"] = profile
                    user.metadata = metadata
                    user.updated_at = datetime.now(timezone.utc).isoformat()
                    application.repositories.auth_repository.upsert_user(user)
                    self._send_json(
                        {
                            "photo_path": photo_path,
                            "photo_data_url": photo_data_url,
                        },
                        status=HTTPStatus.CREATED,
                    )
                    return

                payload = self._read_json_body()

                if segments == ["referrals"]:
                    user, _ = self._require_identity()
                    self._send_json(
                        application.upsert_referral_contact(user_id=user.user_id, payload=payload).to_dict(),
                        status=HTTPStatus.CREATED,
                    )
                    return
                if segments == ["referrals", "import"]:
                    user, _ = self._require_identity()
                    self._send_json(
                        application.import_referral_contacts(
                            user_id=user.user_id,
                            csv_text=str(payload.get("csv_text") or ""),
                            source_kind=str(payload.get("source_kind") or "linkedin_csv"),
                        ),
                        status=HTTPStatus.OK,
                    )
                    return
                if segments == ["outreach", "referral-draft"]:
                    user, _ = self._require_identity()
                    self._send_json(
                        application.generate_referral_outreach(
                            user_id=user.user_id,
                            run_id=str(payload.get("run_id") or ""),
                            job_id=str(payload.get("job_id") or ""),
                            contact_id=str(payload.get("contact_id") or ""),
                        ),
                        status=HTTPStatus.OK,
                    )
                    return
                if segments == ["outreach", "hiring-manager-draft"]:
                    user, _ = self._require_identity()
                    self._send_json(
                        application.generate_hiring_manager_outreach(
                            user_id=user.user_id,
                            run_id=str(payload.get("run_id") or ""),
                            job_id=str(payload.get("job_id") or ""),
                        ),
                        status=HTTPStatus.OK,
                    )
                    return
                if segments == ["users"]:
                    self._require_scope(TOKEN_SCOPE_USERS_WRITE)
                    self._send_json(application.upsert_user(payload).to_dict(), status=HTTPStatus.CREATED)
                    return
                if segments[:1] == ["users"] and len(segments) == 3 and segments[2] == "tokens":
                    self._require_scope(TOKEN_SCOPE_USERS_WRITE)
                    token, raw_token = application.issue_api_token(
                        user_id=segments[1],
                        name=str(payload.get("name") or "api-token"),
                        scopes=[str(item) for item in payload.get("scopes") or [] if str(item).strip()],
                        expires_at=str(payload.get("expires_at") or ""),
                        metadata=dict(payload.get("metadata") or {}),
                    )
                    self._send_json({"token": token.to_public_dict(), "access_token": raw_token}, status=HTTPStatus.CREATED)
                    return
                if segments == ["secrets"]:
                    user, _ = self._require_scope(TOKEN_SCOPE_SECRETS_WRITE)
                    workspace_id = str(payload.get("workspace_id") or "")
                    if workspace_id and not application.user_can_access_workspace(user, workspace_id):
                        raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
                    self._send_json(application.upsert_secret(payload).to_public_dict(), status=HTTPStatus.CREATED)
                    return
                if segments == ["workspaces"]:
                    user, _ = self._require_scope(TOKEN_SCOPE_WORKSPACES_WRITE)
                    workspace_id = str(payload.get("id") or "")
                    if workspace_id and not application.user_can_access_workspace(user, workspace_id):
                        raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
                    self._send_json(application.upsert_workspace(payload).to_dict(), status=HTTPStatus.CREATED)
                    return
                if segments == ["workspace-builder", "workspaces"]:
                    self._require_scope(TOKEN_SCOPE_WORKSPACES_WRITE)
                    self._send_json(
                        application.create_workspace_from_scratch(payload).to_dict(),
                        status=HTTPStatus.CREATED,
                    )
                    return
                if segments == ["workspace-builder", "source-validation"]:
                    self._require_scope(TOKEN_SCOPE_WORKSPACES_READ)
                    self._send_json(application.validate_workspace_builder_sources(payload), status=HTTPStatus.OK)
                    return
                if segments == ["workflow-templates"]:
                    self._require_scope(TOKEN_SCOPE_TEMPLATES_WRITE)
                    self._send_json(application.upsert_workflow_template(payload).to_dict(), status=HTTPStatus.CREATED)
                    return
                if segments == ["documents", "bulk-export"]:
                    user, _ = self._require_scope(TOKEN_SCOPE_ARTIFACTS_READ)
                    bundle = _create_bulk_export_bundle(
                        application,
                        user,
                        [str(item) for item in payload.get("document_ids") or [] if str(item).strip()],
                        label=str(payload.get("label") or ""),
                    )
                    self._send_json(bundle, status=HTTPStatus.CREATED)
                    return
                if segments == ["runs"]:
                    user, _ = self._require_scope(TOKEN_SCOPE_RUNS_WRITE)
                    workspace_id = str(payload.get("workspace_id") or "").strip()
                    if not workspace_id:
                        raise ValueError("workspace_id is required")
                    if not application.user_can_access_workspace(user, workspace_id):
                        raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
                    workspace = application.get_workspace(workspace_id)
                    execution_mode = str(payload.get("execution_mode") or "queued").strip().lower()
                    max_attempts = max(1, int(payload.get("max_attempts") or 1))
                    run_input_overrides = _build_run_input_overrides(
                        user,
                        payload,
                        workspace_settings=workspace.settings,
                    )
                    if execution_mode == "queued":
                        run = application.enqueue_run(
                            workspace_id,
                            run_input_overrides=run_input_overrides,
                            requested_by=f"api:{user.user_id}",
                            max_attempts=max_attempts,
                        )
                    elif execution_mode == "planned":
                        run = application.start_run(
                            workspace_id,
                            run_input_overrides=run_input_overrides,
                            execute=False,
                            requested_by=f"api:{user.user_id}",
                            max_attempts=max_attempts,
                        )
                    elif execution_mode == "sync":
                        run = application.start_run(
                            workspace_id,
                            run_input_overrides=run_input_overrides,
                            execute=True,
                            requested_by=f"api:{user.user_id}",
                            max_attempts=max_attempts,
                        )
                    else:
                        raise ValueError("execution_mode must be one of: queued, planned, sync")
                    self._send_json(run.to_dict(), status=HTTPStatus.CREATED)
                    return
                if segments == ["rejected-jobs", "requeue"]:
                    user, _ = self._require_scope(TOKEN_SCOPE_RUNS_WRITE)
                    run_id = str(payload.get("run_id") or "").strip()
                    job_id = str(payload.get("job_id") or "").strip()
                    if not run_id or not job_id:
                        raise ValueError("run_id and job_id are required")
                    original_run = application.get_run(run_id)
                    if not application.user_can_access_workspace(user, original_run.workspace_id):
                        raise PermissionError(f"Workspace access denied for '{original_run.workspace_id}'.")
                    execution_mode = str(payload.get("execution_mode") or "queued").strip().lower()
                    requeued_run = application.requeue_job_for_generation(
                        run_id=run_id,
                        job_id=job_id,
                        requested_by=f"api:{user.user_id}",
                        max_attempts=max(1, int(payload.get("max_attempts") or 1)),
                        execute=execution_mode == "sync",
                        notes=str(payload.get("notes") or ""),
                    )
                    reviewer_name = user.display_name or user.email or user.user_id
                    reason_summary = str(payload.get("reason_summary") or payload.get("notes") or "")
                    source_stage = str(payload.get("source_stage") or "rejected_review")
                    review = _upsert_rejected_review_override(
                        application,
                        run_id=run_id,
                        job_id=job_id,
                        reviewer=reviewer_name,
                        reason_summary=reason_summary,
                        source_stage=source_stage,
                        notes=str(payload.get("notes") or ""),
                        requeue_run_id=requeued_run.id,
                    )
                    self._send_json({"run": requeued_run.to_dict(), "review": review}, status=HTTPStatus.CREATED)
                    return
                if segments[:1] == ["runs"] and len(segments) == 3 and segments[2] == "cancel":
                    run = application.get_run(segments[1])
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_RUNS_WRITE)
                    self._send_json(application.cancel_run(segments[1]).to_dict(), status=HTTPStatus.OK)
                    return
                if segments[:1] == ["runs"] and len(segments) == 3 and segments[2] == "retry":
                    run = application.get_run(segments[1])
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_RUNS_WRITE)
                    self._send_json(application.retry_run(segments[1]).to_dict(), status=HTTPStatus.OK)
                    return
                if segments[:1] == ["runs"] and len(segments) == 3 and segments[2] == "resume":
                    run = application.get_run(segments[1])
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_RUNS_WRITE)
                    self._send_json(application.resume_run(segments[1]).to_dict(), status=HTTPStatus.OK)
                    return
                if segments[:1] == ["runs"] and len(segments) == 3 and segments[2] == "reviews":
                    run = application.get_run(segments[1])
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_REVIEWS_WRITE)
                    self._send_json(application.upsert_review(run_id=segments[1], payload=payload).to_dict(), status=HTTPStatus.CREATED)
                    return
                if segments == ["workers", "process-next"]:
                    self._require_scope(TOKEN_SCOPE_WORKER_EXECUTE)
                    worker_id = str(payload.get("worker_id") or "api_worker")
                    lease_seconds = max(5, int(payload.get("lease_seconds") or 60))
                    run = application.process_next_queued_run(
                        auto_retry_failed=bool(payload.get("auto_retry_failed", True)),
                        worker_id=worker_id,
                        lease_seconds=lease_seconds,
                    )
                    if run is None:
                        self._send_json({"status": "idle"})
                        return
                    self._send_json({"status": "processed", "run": run.to_dict()}, status=HTTPStatus.OK)
                    return
                if segments == ["workers", "recover-stale"]:
                    self._require_scope(TOKEN_SCOPE_WORKER_EXECUTE)
                    recovered = application.recover_stale_workers()
                    self._send_json({"recovered_workers": [worker.to_dict() for worker in recovered]}, status=HTTPStatus.OK)
                    return
                if segments == ["tracker", "email-integration", "google", "start"]:
                    user, _ = self._require_identity()
                    merged_payload = {
                        **_get_tracker_email_config(user),
                        "provider_id": "gmail",
                        "auth_strategy": "google_oauth",
                    }
                    if "folder" in payload:
                        merged_payload["folder"] = str(payload.get("folder") or "INBOX")
                    if "max_messages" in payload and payload.get("max_messages") is not None:
                        merged_payload["max_messages"] = payload.get("max_messages")
                    current_config = normalize_tracker_email_config(merged_payload)
                    redirect_uri = self._tracker_google_callback_uri()
                    state_nonce, oauth_state = _build_tracker_google_oauth_state(user)
                    authorization_url = build_google_tracker_authorization_url(
                        state=oauth_state,
                        redirect_uri=redirect_uri,
                    )
                    updated_config = begin_google_tracker_authorization(
                        {**current_config, "oauth_state": state_nonce},
                        redirect_uri=redirect_uri,
                        authorization_url=authorization_url,
                    )
                    updated_config["oauth_state"] = state_nonce
                    refreshed_user = _persist_tracker_email_config(application, user, updated_config)
                    self._send_json(
                        {
                            "authorization_url": authorization_url,
                            "expires_at": updated_config["oauth_state_expires_at"],
                            "integration": _tracker_email_integration_payload(application, refreshed_user),
                        },
                        status=HTTPStatus.OK,
                    )
                    return
                if segments == ["tracker", "email-integration", "sync"]:
                    user, _ = self._require_identity()
                    current_config = _get_tracker_email_config(user)
                    tracker_items = _collect_tracker_entries(application, user)
                    try:
                        updated_config = dict(current_config)
                        if str(current_config.get("auth_strategy") or "") == "google_oauth":
                            refresh_token = _resolve_tracker_email_refresh_token(application, current_config)
                            access_token = _resolve_tracker_email_access_token(application, current_config)
                            if refresh_token:
                                token_payload = refresh_google_tracker_access_token(refresh_token=refresh_token)
                                access_token = str(token_payload.get("access_token") or "").strip()
                                if not access_token:
                                    raise ValueError("Google did not return an access token during refresh.")
                                updated_config["access_token_secret_id"] = _upsert_tracker_email_access_token_secret(
                                    application,
                                    user,
                                    updated_config,
                                    access_token,
                                )
                                updated_config["access_token_expires_at"] = utc_plus_seconds(
                                    int(token_payload.get("expires_in") or 3600)
                                )
                            result = sync_tracker_gmail(
                                application=application,
                                user=user,
                                tracker_items=tracker_items,
                                config=updated_config,
                                access_token=access_token,
                            )
                        else:
                            password = _resolve_tracker_email_password(application, current_config)
                            result = sync_tracker_email(
                                application=application,
                                user=user,
                                tracker_items=tracker_items,
                                config=current_config,
                                password=password,
                            )
                    except ValueError as exc:
                        failed_config = dict(current_config)
                        failed_config["last_error"] = str(exc)
                        failed_config["updated_at"] = datetime.now(timezone.utc).isoformat()
                        _persist_tracker_email_config(application, user, failed_config)
                        raise
                    updated_config["processed_message_ids"] = result["processed_message_ids"]
                    updated_config["last_sync_at"] = result["synced_at"]
                    updated_config["updated_at"] = result["synced_at"]
                    updated_config["last_error"] = ""
                    updated_config["last_sync_summary"] = dict(result["summary"] or {})
                    updated_config["authorization_state"] = "authorized"
                    if result.get("history_id"):
                        updated_config["history_id"] = str(result.get("history_id") or "")
                    refreshed_user = _persist_tracker_email_config(application, user, updated_config)
                    self._send_json(
                        {
                            "integration": _tracker_email_integration_payload(application, refreshed_user),
                            "result": result,
                        },
                        status=HTTPStatus.OK,
                    )
                    return

                self._send_error(HTTPStatus.NOT_FOUND, "not_found", "Route not found.")
            except PermissionError as exc:
                if "Missing bearer token" in str(exc) or "Invalid or expired access token" in str(exc):
                    self._send_unauthorized(str(exc))
                else:
                    self._send_error(HTTPStatus.FORBIDDEN, "forbidden", str(exc))
            except KeyError as exc:
                self._send_error(HTTPStatus.NOT_FOUND, "not_found", str(exc))
            except ValueError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, "bad_request", str(exc))
            except Exception as exc:
                self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", str(exc))

        def do_PUT(self):  # noqa: N802
            try:
                _, segments, _ = self._parse_request()
                payload = self._read_json_body()

                if segments == ["settings"]:
                    user, _ = self._require_identity()
                    metadata = dict(user.metadata or {})
                    existing_profile = dict(metadata.get("profile") or {})
                    existing_documents = dict(metadata.get("documents") or {})

                    if "profile" in payload:
                        profile_payload = dict(payload.get("profile") or {})
                        metadata["profile"] = _merge_profile_metadata(existing_profile, profile_payload, user)

                    if "defaults" in payload:
                        defaults_payload = dict(payload.get("defaults") or {})
                        default_workspace_id = str(defaults_payload.get("default_workspace_id") or "")
                        if default_workspace_id and not application.user_can_access_workspace(user, default_workspace_id):
                            raise PermissionError(f"Workspace access denied for '{default_workspace_id}'.")
                        metadata["defaults"] = {
                            "default_workspace_id": default_workspace_id,
                            "default_execution_mode": str(defaults_payload.get("default_execution_mode") or "queued"),
                            "default_profile_id": str(defaults_payload.get("default_profile_id") or ""),
                            "default_prompt_set_id": str(defaults_payload.get("default_prompt_set_id") or ""),
                            "max_jobs_per_run": max(1, int(defaults_payload.get("max_jobs_per_run") or 25)),
                        }

                    if "documents" in payload:
                        documents_payload = dict(payload.get("documents") or {})
                        metadata["documents"] = _merge_document_metadata(existing_documents, documents_payload)

                    if "review_preferences" in payload:
                        review_payload = dict(payload.get("review_preferences") or {})
                        metadata["review_preferences"] = {
                            "require_review_before_use": bool(review_payload.get("require_review_before_use", True)),
                            "default_decision_state": str(review_payload.get("default_decision_state") or "waiting_review"),
                            "rejection_note_required": bool(review_payload.get("rejection_note_required", True)),
                            "auto_open_next_item": bool(review_payload.get("auto_open_next_item", True)),
                        }

                    if "account" in payload:
                        account_payload = dict(payload.get("account") or {})
                        user.display_name = str(account_payload.get("display_name") or user.display_name)
                        user.email = str(account_payload.get("email") or user.email)

                    user.metadata = metadata
                    user.updated_at = datetime.now(timezone.utc).isoformat()
                    application.repositories.auth_repository.upsert_user(user)
                    refreshed_user = application.get_user(user.user_id)
                    self._send_json(_build_settings_payload(application, refreshed_user), status=HTTPStatus.OK)
                    return
                if segments[:1] == ["referrals"] and len(segments) == 2:
                    user, _ = self._require_identity()
                    self._send_json(
                        application.upsert_referral_contact(
                            user_id=user.user_id,
                            payload=payload,
                            contact_id=segments[1],
                        ).to_dict(),
                        status=HTTPStatus.OK,
                    )
                    return
                if segments[:2] == ["workspace-builder", "workspaces"] and len(segments) == 3:
                    self._require_workspace_access(
                        workspace_id=segments[2],
                        required_scope=TOKEN_SCOPE_WORKSPACES_WRITE,
                    )
                    self._send_json(
                        application.update_workspace_from_scratch(segments[2], payload).to_dict(),
                        status=HTTPStatus.OK,
                    )
                    return
                if segments[:1] == ["users"] and len(segments) == 2:
                    self._require_scope(TOKEN_SCOPE_USERS_WRITE)
                    payload["user_id"] = segments[1]
                    self._send_json(application.upsert_user(payload).to_dict(), status=HTTPStatus.OK)
                    return
                if segments == ["tracker", "email-integration"]:
                    user, _ = self._require_identity()
                    existing_config = _get_tracker_email_config(user)
                    raw_password = str(payload.get("password") or "").strip()
                    merged_payload = {
                        **existing_config,
                        **{key: value for key, value in payload.items() if key != "password" and value is not None},
                    }
                    if raw_password and not str(payload.get("auth_strategy") or "").strip():
                        merged_payload["auth_strategy"] = "legacy_imap_password"
                    merged_config = normalize_tracker_email_config(merged_payload)
                    connection_fingerprint = (
                        existing_config.get("provider_id"),
                        existing_config.get("email_address"),
                        existing_config.get("imap_host"),
                        existing_config.get("imap_port"),
                        existing_config.get("folder"),
                    )
                    next_fingerprint = (
                        merged_config.get("provider_id"),
                        merged_config.get("email_address"),
                        merged_config.get("imap_host"),
                        merged_config.get("imap_port"),
                        merged_config.get("folder"),
                    )
                    now_iso = datetime.now(timezone.utc).isoformat()
                    if merged_config.get("auth_strategy") == "google_oauth":
                        merged_config["provider_id"] = "gmail"
                    else:
                        password = raw_password or _resolve_tracker_email_password(application, existing_config)
                        test_tracker_email_connection(merged_config, password)
                        if raw_password:
                            merged_config["password_secret_id"] = _upsert_tracker_email_password_secret(
                                application,
                                user,
                                merged_config,
                                raw_password,
                            )
                        else:
                            merged_config["password_secret_id"] = str(existing_config.get("password_secret_id") or "")
                        merged_config["connected_at"] = (
                            str(existing_config.get("connected_at") or now_iso)
                            if connection_fingerprint == next_fingerprint
                            else now_iso
                        )
                    merged_config["updated_at"] = now_iso
                    merged_config["last_error"] = ""
                    if connection_fingerprint != next_fingerprint:
                        merged_config["processed_message_ids"] = []
                        merged_config["last_sync_at"] = ""
                        merged_config["last_sync_summary"] = {}
                    refreshed_user = _persist_tracker_email_config(application, user, merged_config)
                    self._send_json(_tracker_email_integration_payload(application, refreshed_user), status=HTTPStatus.OK)
                    return
                if segments[:1] == ["tracker"] and len(segments) == 2:
                    # PUT /tracker/:review_id — update tracker_status, email_confirmed, rejection_note
                    user, _ = self._require_identity()
                    review = application.get_review(segments[1])
                    run = application.get_run(review.run_id)
                    if not application.user_can_access_workspace(user, run.workspace_id):
                        raise PermissionError(f"Workspace access denied for '{run.workspace_id}'.")
                    review_meta = dict(review.metadata or {})
                    allowed_tracker_statuses = {"applied", "email_confirmed", "interview_invited", "rejected"}
                    if "tracker_status" in payload:
                        new_status = str(payload["tracker_status"]).strip().lower()
                        if new_status and new_status not in allowed_tracker_statuses:
                            raise ValueError(f"tracker_status must be one of: {sorted(allowed_tracker_statuses)}")
                        review_meta["tracker_status"] = new_status
                    if "email_confirmed" in payload:
                        review_meta["email_confirmed"] = bool(payload["email_confirmed"])
                    if "rejection_note" in payload:
                        review_meta["rejection_note"] = str(payload["rejection_note"])
                    if payload.get("tracker_status") == "rejected" and not review_meta.get("rejected_at"):
                        review_meta["rejected_at"] = datetime.now(timezone.utc).isoformat()
                    review.metadata = review_meta
                    application.repositories.review_store.upsert_review(review)
                    self._send_json(
                        {
                            "review_id": review.review_id,
                            "tracker_status": str(review_meta.get("tracker_status") or ""),
                            "email_confirmed": bool(review_meta.get("email_confirmed") or False),
                            "rejection_note": str(review_meta.get("rejection_note") or ""),
                            "rejected_at": str(review_meta.get("rejected_at") or ""),
                            "updated_at": review.updated_at,
                        },
                        status=HTTPStatus.OK,
                    )
                    return
                if segments[:1] == ["secrets"] and len(segments) == 2:
                    user, _ = self._require_scope(TOKEN_SCOPE_SECRETS_WRITE)
                    payload["secret_id"] = segments[1]
                    workspace_id = str(payload.get("workspace_id") or "")
                    if workspace_id and not application.user_can_access_workspace(user, workspace_id):
                        raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
                    self._send_json(application.upsert_secret(payload).to_public_dict(), status=HTTPStatus.OK)
                    return
                if segments[:1] == ["workspaces"] and len(segments) == 2:
                    self._require_workspace_access(workspace_id=segments[1], required_scope=TOKEN_SCOPE_WORKSPACES_WRITE)
                    payload["id"] = segments[1]
                    self._send_json(application.upsert_workspace(payload).to_dict(), status=HTTPStatus.OK)
                    return
                if segments[:1] == ["workflow-templates"] and len(segments) == 2:
                    self._require_scope(TOKEN_SCOPE_TEMPLATES_WRITE)
                    payload["id"] = segments[1]
                    self._send_json(application.upsert_workflow_template(payload).to_dict(), status=HTTPStatus.OK)
                    return
                if segments[:1] == ["runs"] and len(segments) == 4 and segments[2] == "jobs":
                    run = application.get_run(segments[1])
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_RUNS_WRITE)
                    jobs = payload.get("jobs")
                    if not isinstance(jobs, list):
                        raise ValueError("jobs must be a list")
                    job_set = application.upsert_job_set(segments[1], segments[3], jobs)
                    self._send_json({"run_id": segments[1], "set_key": segments[3], "jobs": [job.to_dict() for job in job_set]})
                    return
                if segments[:1] == ["runs"] and len(segments) == 4 and segments[2] == "artifacts":
                    run = application.get_run(segments[1])
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_ARTIFACTS_WRITE)
                    payload["artifact_id"] = segments[3]
                    self._send_json(application.upsert_artifact(segments[1], payload).to_dict(), status=HTTPStatus.OK)
                    return
                if segments[:1] == ["runs"] and len(segments) == 4 and segments[2] == "reviews":
                    run = application.get_run(segments[1])
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_REVIEWS_WRITE)
                    self._send_json(application.upsert_review(run_id=segments[1], payload=payload, review_id=segments[3]).to_dict(), status=HTTPStatus.OK)
                    return

                self._send_error(HTTPStatus.NOT_FOUND, "not_found", "Route not found.")
            except PermissionError as exc:
                if "Missing bearer token" in str(exc) or "Invalid or expired access token" in str(exc):
                    self._send_unauthorized(str(exc))
                else:
                    self._send_error(HTTPStatus.FORBIDDEN, "forbidden", str(exc))
            except KeyError as exc:
                self._send_error(HTTPStatus.NOT_FOUND, "not_found", str(exc))
            except ValueError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, "bad_request", str(exc))
            except Exception as exc:
                self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", str(exc))

        def do_DELETE(self):  # noqa: N802
            try:
                _, segments, _ = self._parse_request()

                if segments[:1] == ["users"] and len(segments) == 2:
                    self._require_scope(TOKEN_SCOPE_USERS_WRITE)
                    application.delete_user(segments[1])
                    self._send_json({"deleted": segments[1]}, status=HTTPStatus.OK)
                    return
                if segments[:1] == ["referrals"] and len(segments) == 2:
                    user, _ = self._require_identity()
                    application.delete_referral_contact(user.user_id, segments[1])
                    self._send_json({"deleted": segments[1]}, status=HTTPStatus.OK)
                    return
                if segments[:1] == ["users"] and len(segments) == 4 and segments[2] == "tokens":
                    self._require_scope(TOKEN_SCOPE_USERS_WRITE)
                    self._send_json(application.revoke_api_token(segments[3]).to_public_dict(), status=HTTPStatus.OK)
                    return
                if segments == ["tracker", "email-integration"]:
                    user, _ = self._require_identity()
                    existing_config = _get_tracker_email_config(user)
                    for secret_id in {
                        str(existing_config.get("password_secret_id") or "").strip(),
                        str(existing_config.get("access_token_secret_id") or "").strip(),
                        str(existing_config.get("refresh_token_secret_id") or "").strip(),
                    }:
                        if not secret_id:
                            continue
                        try:
                            application.delete_secret(secret_id)
                        except KeyError:
                            pass
                    refreshed_user = _clear_tracker_email_config(application, user)
                    self._send_json(
                        {
                            "deleted": "tracker_email_integration",
                            "integration": _tracker_email_integration_payload(application, refreshed_user),
                        },
                        status=HTTPStatus.OK,
                    )
                    return
                if segments[:1] == ["secrets"] and len(segments) == 2:
                    self._require_scope(TOKEN_SCOPE_SECRETS_WRITE)
                    application.delete_secret(segments[1])
                    self._send_json({"deleted": segments[1]}, status=HTTPStatus.OK)
                    return
                if segments[:1] == ["workspaces"] and len(segments) == 2:
                    self._require_workspace_access(workspace_id=segments[1], required_scope=TOKEN_SCOPE_WORKSPACES_WRITE)
                    application.delete_workspace(segments[1])
                    self._send_json({"deleted": segments[1]}, status=HTTPStatus.OK)
                    return
                if segments[:1] == ["workflow-templates"] and len(segments) == 2:
                    self._require_scope(TOKEN_SCOPE_TEMPLATES_WRITE)
                    application.delete_workflow_template(segments[1])
                    self._send_json({"deleted": segments[1]}, status=HTTPStatus.OK)
                    return
                if segments[:1] == ["runs"] and len(segments) == 4 and segments[2] == "jobs":
                    run = application.get_run(segments[1])
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_RUNS_WRITE)
                    application.delete_job_set(segments[1], segments[3])
                    self._send_json({"deleted": segments[3], "run_id": segments[1]}, status=HTTPStatus.OK)
                    return
                if segments[:1] == ["runs"] and len(segments) == 4 and segments[2] == "artifacts":
                    run = application.get_run(segments[1])
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_ARTIFACTS_WRITE)
                    application.delete_artifact(segments[1], segments[3])
                    self._send_json({"deleted": segments[3], "run_id": segments[1]}, status=HTTPStatus.OK)
                    return
                if segments[:1] == ["runs"] and len(segments) == 4 and segments[2] == "reviews":
                    review = application.get_review(segments[3])
                    run = application.get_run(review.run_id)
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_REVIEWS_WRITE)
                    application.delete_review(segments[3])
                    self._send_json({"deleted": segments[3], "run_id": segments[1]}, status=HTTPStatus.OK)
                    return
                if segments[:1] == ["runs"] and len(segments) == 2:
                    run = application.get_run(segments[1])
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_RUNS_WRITE)
                    application.delete_run(segments[1])
                    self._send_json({"deleted": segments[1]}, status=HTTPStatus.OK)
                    return

                self._send_error(HTTPStatus.NOT_FOUND, "not_found", "Route not found.")
            except PermissionError as exc:
                if "Missing bearer token" in str(exc) or "Invalid or expired access token" in str(exc):
                    self._send_unauthorized(str(exc))
                else:
                    self._send_error(HTTPStatus.FORBIDDEN, "forbidden", str(exc))
            except KeyError as exc:
                self._send_error(HTTPStatus.NOT_FOUND, "not_found", str(exc))
            except ValueError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, "bad_request", str(exc))
            except Exception as exc:
                self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", str(exc))

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
    application = create_backend(data_dir, storage_backend=storage_backend)
    server = ThreadingHTTPServer((host, int(port)), build_handler(application))
    print(f"Unified backend API listening on http://{host}:{port}")
    server.serve_forever()
