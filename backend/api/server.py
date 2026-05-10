from __future__ import annotations

import base64
import io
import json
import mimetypes
import os
import re
import zipfile
from copy import deepcopy
from datetime import datetime, timezone
from email.parser import BytesFeedParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from backend.application.services import BackendValidationError
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
from backend.capabilities.tailored_documents.rendering import get_document_design_options
from backend.bootstrap import create_backend
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
from backend.tools.discover_company_careers import run_discovery as run_career_url_discovery
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
from backend.orchestration.workspace_builder import _slugify
from backend.profiles.cv_profile_extraction import extract_cv_profile, normalize_profile_payload
from backend.profiles.cv_text import extract_cv_text_from_path


def _json_bytes(payload) -> bytes:
    return json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")


_EXPANDED_ARTIFACT_DELIMITER = "__item__"
_EXPANDED_ARTIFACT_SUFFIXES = {".csv", ".docx", ".json", ".md", ".pdf", ".txt", ".xlsx"}
_LOOPBACK_ORIGIN_HOSTS = {"127.0.0.1", "localhost", "::1"}


class AtsExportBlockedError(ValueError):
    def __init__(self, gate: dict):
        self.gate = gate
        super().__init__(gate.get("last_warning") or "Final CV export is blocked until the ATS score target is reached.")


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


def _extract_text_from_uploaded_file(filename: str, data: bytes) -> str:
    extension = Path(filename or "").suffix.lower()
    if extension == ".docx":
        return _extract_text_from_docx(data).strip()
    if extension == ".pdf":
        return _extract_text_from_pdf(data).strip()
    for encoding in ("utf-8", "latin-1"):
        try:
            return data.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
        except Exception:
            return ""
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


_CV_SECTION_HEADER_PATTERN = re.compile(
    r"^(professional\s+summary|summary|profile|about\s+me|objective|skills|core\s+competencies|"
    r"competencies|technical\s+skills|key\s+skills|experience|work\s+experience|"
    r"professional\s+experience|employment|education|certifications?)$",
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


def _cv_nonempty_lines(cv_text: str) -> list[str]:
    return [line.strip() for line in str(cv_text or "").splitlines() if line.strip()]


def _looks_like_cv_section_header(line: str) -> bool:
    return bool(_CV_SECTION_HEADER_PATTERN.match(str(line or "").strip()))


def _looks_like_cv_contact_line(line: str) -> bool:
    return bool(_CV_CONTACT_LINE_PATTERN.search(str(line or "").strip()))


def _looks_like_cv_date_line(line: str) -> bool:
    return bool(_CV_DATE_TOKEN_PATTERN.search(str(line or "").strip()))


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
            if len(summary_lines) >= 4:
                break
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
                    "bulletsText": "\n".join(bullets[:4]),
                }
            )
        current = None

    for raw_line in lines[:40]:
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
    return entries[:4]


def _build_workspace_cv_preview_profile(
    cv_text: str,
    shared_profile: dict[str, Any],
    *,
    asset_display_name: str = "",
    parsed_profile: dict[str, Any] | None = None,
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
        summary = " ".join(summary_candidates[:3]).strip()
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
        for item in (normalized_parsed_profile.get("languages") or normalized_shared_profile.get("languages") or [])
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

    photo_data_url = str(shared_profile.get("photo_data_url") or shared_profile.get("avatar_url") or "").strip()
    avatar_url = str(shared_profile.get("avatar_url") or shared_profile.get("photo_data_url") or "").strip()

    return {
        "name": name,
        "role_title": role_title,
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
        "competencies": competencies[:20],
        "languages": languages[:12],
        "recent_experience": recent_experience[:4],
        "education": education[:6],
        "photo_data_url": photo_data_url,
        "avatar_url": avatar_url,
    }


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


def _workflow_snapshot_for_run(application, run) -> dict:
    if run.run_plan and isinstance(run.run_plan.workflow_snapshot, dict) and run.run_plan.workflow_snapshot:
        return dict(run.run_plan.workflow_snapshot)
    workflow = application.repositories.workspace_repository.get_workflow_template(run.workflow_template_id)
    return workflow.to_dict()


def _customer_job_payload(job_payload: dict, *, review=None, document_count: int = 0) -> dict:
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
    searchable = str(text or "").casefold()
    for canonical_name, aliases in _CUSTOMER_LANGUAGE_ALIASES.items():
        if any(alias.casefold() in searchable for alias in aliases):
            return canonical_name
    return ""


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
        "can_generate_documents": bool(entry.get("can_requeue") or False),
        "create_documents_run_id": str(entry.get("requeue_run_id") or ""),
        "create_documents_run_status": str(entry.get("requeue_run_status") or ""),
        "create_documents_run_finished_at": str(entry.get("requeue_run_finished_at") or ""),
        "create_documents_run_url": str(entry.get("requeue_run_url") or ""),
    }


def _collect_run_customer_view(application, user, run) -> dict:
    workflow_snapshot = _workflow_snapshot_for_run(application, run)
    workflow_stages = [
        dict(stage)
        for stage in workflow_snapshot.get("stages") or []
        if isinstance(stage, dict)
    ]
    workspace = application.get_workspace(run.workspace_id)
    reviews = application.list_reviews(run_id=run.id, limit=1000, offset=0)
    reviews_by_job = {review.job_id: review for review in reviews}
    job_sets = application.list_job_sets(run.id)
    documents = _collect_document_entries(application, user, run_id=run.id)
    document_count_by_job: dict[str, int] = {}
    for document in documents:
        job_id = str(document.get("job_id") or "")
        if job_id:
            document_count_by_job[job_id] = document_count_by_job.get(job_id, 0) + 1
    rejected_entries = _collect_rejected_job_entries(application, user, run_id=run.id)
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
            job_payload = job.to_dict()
            if job_payload.get("job_id"):
                included_job_ids.add(str(job_payload.get("job_id")))
            customer_job = _customer_job_payload(
                job_payload,
                review=reviews_by_job.get(job.job_id),
                document_count=document_count_by_job.get(job.job_id, 0),
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

    tracker_items = [item for item in _collect_tracker_entries(application, user) if str(item.get("run_id") or "") == run.id]
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
        "",
    )
    generated_job_count = 0
    for key in run.final_job_set_keys or []:
        generated_job_count += len(job_sets.get(key, []))

    return {
        "run": {
            **_run_summary(run),
            "workspace_name": workspace.name,
            "workflow_name": str(workflow_snapshot.get("name") or run.workflow_template_id),
            "current_stage_name": current_stage_name,
        },
        "summary": {
            "stage_count": len(stages),
            "completed_stage_count": sum(1 for stage in stages if str(stage.get("status") or "") == "completed"),
            "included_job_count": len(included_job_ids),
            "excluded_job_count": len(excluded_job_ids),
            "generated_job_count": generated_job_count,
            "tracker_job_count": len(tracker_items),
            "excluded_ready_for_documents_count": sum(
                1
                for item in rejected_entries
                if bool(item.get("can_requeue") or False) and not str(item.get("requeue_run_id") or "")
            ),
        },
        "tracker": {
            "item_count": len(tracker_items),
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


def _workspace_option(workspace) -> dict:
    return {
        "id": workspace.id,
        "name": workspace.name,
        "workspace_type": workspace.workspace_type,
        "automation_flow": str(workspace.metadata.get("automation_flow") or workspace.settings.get("automation_flow") or ""),
    }


def _merge_profile_metadata(existing_profile: dict, profile_payload: dict, user) -> dict:
    normalized_existing = normalize_profile_payload(existing_profile)
    normalized_payload = normalize_profile_payload(profile_payload)
    payload_keys = set(profile_payload or {})
    merged = {
        "name": str(
            normalized_payload.get("name")
            or normalized_existing.get("name")
            or user.display_name
            or user.email.split("@")[0]
        ),
        "role_title": str(normalized_payload.get("role_title") or normalized_existing.get("role_title") or ""),
        "email": str(normalized_payload.get("email") or normalized_existing.get("email") or user.email),
        "location": str(normalized_payload.get("location") or normalized_existing.get("location") or ""),
        "website": str(normalized_payload.get("website") or normalized_existing.get("website") or ""),
        "linkedin_url": str(normalized_payload.get("linkedin_url") or normalized_existing.get("linkedin_url") or ""),
        "github_url": str(normalized_payload.get("github_url") or normalized_existing.get("github_url") or ""),
        "avatar_url": str(profile_payload.get("avatar_url") or existing_profile.get("avatar_url") or ""),
        "photo_data_url": str(profile_payload.get("photo_data_url") or existing_profile.get("photo_data_url") or ""),
        "photo_path": str(profile_payload.get("photo_path") or existing_profile.get("photo_path") or ""),
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


def _merge_document_metadata(existing_documents: dict, documents_payload: dict) -> dict:
    existing_web_cv_palette = dict(existing_documents.get("web_cv_palette") or {})
    payload_web_cv_palette = dict(documents_payload.get("web_cv_palette") or {})
    default_web_cv_show_photo = existing_documents.get("web_cv_show_photo")
    if default_web_cv_show_photo is None:
        default_web_cv_show_photo = existing_documents.get("include_photo", True)

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
        "web_cv_template": str(documents_payload.get("web_cv_template") or existing_documents.get("web_cv_template") or "ats_single_column"),
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
    }


def _build_run_input_overrides(user, payload: dict, *, workspace_settings: dict | None = None) -> dict:
    profile = dict((user.metadata or {}).get("profile") or {})
    documents = dict((user.metadata or {}).get("documents") or {})
    overrides = dict(payload.get("run_input_overrides") or {})
    workspace_settings = dict(workspace_settings or {})
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
    {"key": "apply_link", "label": "Application link"},
    {"key": "linkedin_link", "label": "LinkedIn link"},
    {"key": "priority_rank", "label": "Priority"},
    {"key": "applicant_count", "label": "Applicants"},
    {"key": "documents", "label": "Documents"},
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
    if not label:
        label = document_type or "Document"
    return {
        "document_id": str(document.get("document_id") or ""),
        "field": str(document.get("asset_kind") or ""),
        "label": label,
        "document_type": document_type,
        "asset_kind": str(document.get("asset_kind") or ""),
        "download_url": str(document.get("download_url") or ""),
        "path": str(document.get("relative_path") or document.get("path") or ""),
        "workspace_id": str(document.get("workspace_id") or ""),
        "run_id": str(document.get("run_id") or ""),
        "job_id": str(metadata.get("job_id") or document.get("job_id") or ""),
        "source_origin": str(document.get("source_origin") or ""),
        "source_scope": source_scope,
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


def _collect_tracker_entries(application, user) -> list[dict]:
    """Return all reviews that have been approved or have a tracker_status set."""
    workspaces, runs = _collect_authorized_runs(application, user)
    workspaces_map = {ws.id: ws for ws in application.list_workspaces()}
    application_documents, standard_documents = _index_tracker_documents(_collect_document_entries(application, user))
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
            application_status = normalize_application_status(
                review_meta.get("application_status") or tracker_status,
                default="Applied",
            )
            job = jobs_by_id.get(review.job_id)
            job_extra = dict(job.extra_fields or {}) if job else {}
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
            entry = {
                "review_id": review.review_id,
                "run_id": review.run_id,
                "workspace_id": run.workspace_id,
                "workspace_name": workspace.name if workspace else run.workspace_id,
                "job_id": review.job_id,
                "title": job.title if job else "",
                "company": job.company if job else "",
                "apply_link": (job.apply_link or job.link or job.source_url) if job else "",
                "linkedin_link": str(job_extra.get("linkedin_link") or (job.link if job else "") or ""),
                "location": job.location_raw if job else "",
                "full_description": description_text,
                "tracker_status": tracker_status,
                "application_status": application_status,
                "email_confirmed": bool(review_meta.get("email_confirmed") or False),
                "rejection_note": str(review_meta.get("rejection_note") or ""),
                "rejected_at": str(review_meta.get("rejected_at") or ""),
                "application_date": str(review_meta.get("application_date") or review_meta.get("applied_at") or ""),
                "notes": str(review.notes or review_meta.get("notes") or ""),
                "applicant_count": job_extra.get("applicant_count") or job_extra.get("num_applicants") or "",
                "posted_time_text": str(job_extra.get("posted_time_text") or job_extra.get("listed_at_text") or ""),
                "priority_rank": job.priority_rank if job else job_extra.get("priority_rank"),
                "priority_bucket": str(job_extra.get("priority_bucket") or job_extra.get("priority_tier") or ""),
                **document_fields,
                "documents": documents,
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
            entries.append(entry)
    for external in _load_external_tracker_applications(user):
        application_status = normalize_application_status(
            external.get("application_status") or external.get("tracker_status"),
            default="Unknown",
        )
        tracker_status = str(
            external.get("tracker_status")
            or legacy_tracker_status_for_application_status(application_status)
        )
        entry = {
            "review_id": str(external.get("review_id") or external.get("application_id") or ""),
            "application_id": str(external.get("application_id") or ""),
            "run_id": "",
            "workspace_id": "",
            "workspace_name": "External applications",
            "job_id": str(external.get("application_id") or ""),
            "title": str(external.get("title") or ""),
            "company": str(external.get("company") or ""),
            "apply_link": str(external.get("apply_link") or ""),
            "linkedin_link": "",
            "location": str(external.get("location") or ""),
            "full_description": str(external.get("full_description") or ""),
            "tracker_status": tracker_status,
            "application_status": application_status,
            "email_confirmed": bool(external.get("email_confirmed") or False),
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
            "source_label": "Gmail",
            "external_application": True,
            "gmail_detection": dict(external.get("gmail_detection") or {}),
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
        contact.contact_id: contact.to_dict() for contact in application.list_referral_contacts(user.user_id)
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


def _save_referral_outreach_status_from_payload(application, user, payload: dict) -> dict:
    contact_id = str(payload.get("contact_id") or "").strip()
    run_id = str(payload.get("run_id") or "").strip()
    job_id = str(payload.get("job_id") or "").strip()
    if not contact_id or not run_id or not job_id:
        raise ValueError("run_id, job_id, and contact_id are required")
    run = application.get_run(run_id)
    if not application.user_can_access_workspace(user, run.workspace_id):
        raise PermissionError(f"Workspace access denied for '{run.workspace_id}'.")
    contact = application.get_referral_contact(user.user_id, contact_id)
    _, record = _persist_referral_outreach_status(
        application,
        user,
        run_id=run_id,
        job_id=job_id,
        contact_id=contact_id,
        outreach_status=str(payload.get("outreach_status") or ""),
        contact_snapshot=contact.to_dict(),
    )
    return record


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
        updated["updated_at"] = datetime.now(timezone.utc).isoformat()
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


def _run_jobs_for_document_lookup(application, run) -> list[object]:
    job_sets = application.list_job_sets(run.id)
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


def _collect_artifact_entries(application, user, *, workspace_id: str = "", run_id: str = "") -> list[dict]:
    workspaces, runs = _collect_authorized_runs(application, user, workspace_id=workspace_id)
    entries: list[dict] = []
    for run in runs:
        if run_id and run.id != run_id:
            continue
        workspace = workspaces.get(run.workspace_id)
        run_jobs = _run_jobs_for_document_lookup(application, run)
        artifacts = application.list_artifacts(run.id)
        for artifact in artifacts:
            entries.extend(
                _enrich_artifact_entry_with_job_context(entry, run_jobs)
                for entry in _expand_artifact_entries(run, workspace, artifact)
            )
    entries.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return entries


_CANDIDATE_ASSET_METADATA_KEY = "candidate_assets"
_WORKSPACE_CV_RUNTIME_SETTING_KEYS = (
    "workspace_cv_text",
    "workspace_cv_asset_path",
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


def _get_candidate_asset_by_id(user, asset_id: str) -> dict:
    target_asset_id = str(asset_id or "").strip()
    for asset in _load_candidate_assets(user):
        if str(asset.get("asset_id") or "").strip() == target_asset_id:
            return asset
    raise ValueError(f"Workspace CV asset '{target_asset_id}' was not found.")


def _candidate_asset_file_path(asset: dict) -> Path | None:
    file_payload = dict(asset.get("file") or {})
    raw_path = str(file_payload.get("path") or asset.get("path") or "").strip()
    return Path(raw_path) if raw_path else None


def _resolve_workspace_cv_binding(user, asset_id: str) -> tuple[dict[str, str], dict]:
    asset = _get_candidate_asset_by_id(user, asset_id)
    asset_kind = str(asset.get("asset_kind") or "").strip().lower()
    if asset_kind != "workspace_cv":
        raise ValueError(f"Asset '{asset_id}' is not a workspace CV.")

    asset_path = _candidate_asset_file_path(asset)
    if asset_path is None or not asset_path.exists() or not asset_path.is_file():
        raise ValueError(f"Workspace CV asset '{asset_id}' is missing its source file.")

    cv_text = extract_cv_text_from_path(asset_path)
    if not cv_text:
        raise ValueError(f"Workspace CV asset '{asset_id}' does not contain readable text.")

    file_payload = dict(asset.get("file") or {})
    return (
        {
            "workspace_cv_text": cv_text,
            "workspace_cv_asset_path": str(asset_path.resolve()),
            "workspace_cv_asset_display_name": str(asset.get("display_name") or asset_path.name or asset_id),
            "workspace_cv_asset_extension": str(
                file_payload.get("extension") or asset_path.suffix.lower().lstrip(".")
            ),
            "workspace_cv_asset_mime_type": str(
                file_payload.get("mime_type") or mimetypes.guess_type(asset_path.name)[0] or ""
            ),
        },
        deepcopy(asset),
    )


def _prepare_workspace_builder_payload_with_cv(payload: dict, user, *, existing_workspace=None) -> tuple[dict, dict[str, str]]:
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
        if not asset_id:
            raise ValueError("workspace_cv_asset_id is required for tailored-documents workspaces.")
        runtime_settings, workspace_cv_asset = _resolve_workspace_cv_binding(user, asset_id)
        settings.update(runtime_settings)
        builder_payload["workspace_cv_asset"] = workspace_cv_asset

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
                **dict(metadata or {}),
            },
        },
    )


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
    return _attach_application_document_contract({
        "document_id": _document_id_for_artifact(entry["run_id"], entry["artifact_id"]),
        "asset_id": "",
        "asset_kind": asset_kind,
        "group_id": group_id,
        "group_label": group_label,
        "display_name": str(
            metadata.get("document_display_name")
            or metadata.get("document_name")
            or entry.get("file_name")
            or ""
        ),
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
        asset_path = str(asset.get("file", {}).get("path") or asset.get("path") or "").strip()
        cv_text = extract_cv_text_from_path(asset_path) if asset_path else ""
        preview_profile = _build_workspace_cv_preview_profile(
            cv_text,
            shared_profile,
            asset_display_name=str(asset.get("display_name") or ""),
            parsed_profile=dict(metadata.get("parsed_profile") or {}),
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
) -> list[dict]:
    raw_profile = dict((user.metadata or {}).get("profile") or {})
    shared_profile = {
        "name": str(raw_profile.get("name") or user.display_name or user.email.split("@")[0]),
        "role_title": str(raw_profile.get("role_title") or ""),
        "email": str(raw_profile.get("email") or user.email),
        "location": str(raw_profile.get("location") or ""),
        "website": str(raw_profile.get("website") or ""),
        "linkedin_url": str(raw_profile.get("linkedin_url") or ""),
        "github_url": str(raw_profile.get("github_url") or ""),
        "summary": str(raw_profile.get("summary") or ""),
        "competencies": list(raw_profile.get("competencies") or []),
        "languages": list(raw_profile.get("languages") or []),
        "recent_experience": list(raw_profile.get("recent_experience") or []),
        "education": list(raw_profile.get("education") or []),
        "photo_data_url": str(raw_profile.get("photo_data_url") or ""),
        "avatar_url": str(raw_profile.get("avatar_url") or ""),
    }
    workspaces = {
        workspace.id: workspace.name
        for workspace in application.list_workspaces()
        if application.user_can_access_workspace(user, workspace.id)
    }
    entries = [
        _artifact_entry_to_document_item(entry)
        for entry in _collect_artifact_entries(application, user, workspace_id=workspace_id, run_id=run_id)
        if _artifact_entry_is_user_facing_document(entry)
    ]
    for asset in _load_candidate_assets(user):
        asset_workspace_id = str(asset.get("workspace_binding", {}).get("workspace_id") or "")
        if workspace_id and asset_workspace_id and asset_workspace_id != workspace_id:
            continue
        entries.append(_candidate_asset_to_document_item(asset, workspaces, shared_profile))
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


def _find_document_entry(application, user, document_id: str) -> dict:
    for item in _collect_document_entries(application, user):
        if str(item.get("document_id") or "") == str(document_id or ""):
            return item
    raise KeyError(f"Document '{document_id}' not found.")


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
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for document_id in document_ids:
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


def _collect_rejected_job_entries(application, user, *, workspace_id: str = "", run_id: str = "") -> list[dict]:
    workspaces, runs = _collect_authorized_runs(application, user, workspace_id=workspace_id)
    reason_labels = _rejection_reason_labels()
    entries: list[dict] = []
    requeue_run_cache: dict[str, object | None] = {}
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


def _parse_bool_param(query: dict[str, list[str]], name: str, *, default: bool = False) -> bool:
    raw_value = str((query.get(name) or [str(default)])[0]).strip().lower()
    if raw_value in {"1", "true", "yes", "on"}:
        return True
    if raw_value in {"0", "false", "no", "off"}:
        return False
    return default


def _normalize_origin_value(value: str) -> str:
    origin = str(value or "").strip()
    if not origin:
        return ""
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def _origin_is_loopback(origin: str) -> bool:
    normalized = _normalize_origin_value(origin)
    if not normalized:
        return False
    parsed = urlparse(normalized)
    return str(parsed.hostname or "").strip().lower() in _LOOPBACK_ORIGIN_HOSTS


def _parse_allowed_origins(raw_value: str) -> tuple[set[str], bool]:
    values = {str(item).strip() for item in str(raw_value or "").split(",") if str(item).strip()}
    allow_all = "*" in values
    normalized = {_normalize_origin_value(item) for item in values if item != "*"}
    normalized.discard("")
    return normalized, allow_all


def build_handler(application, *, allowed_origins: set[str] | None = None, allow_all_origins: bool = False):
    normalized_allowed_origins = {_normalize_origin_value(item) for item in (allowed_origins or set())}
    normalized_allowed_origins.discard("")

    class BackendApiHandler(BaseHTTPRequestHandler):
        def _cors_origin(self) -> str:
            origin = _normalize_origin_value(str(self.headers.get("Origin") or ""))
            if not origin:
                return ""
            if allow_all_origins or origin in normalized_allowed_origins or _origin_is_loopback(origin):
                return origin
            return ""

        def _cors_headers(self) -> dict[str, str]:
            headers = {
                "Access-Control-Allow-Headers": "Authorization, Content-Type",
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
            configured_redirect_uri = str(tracker_google_oauth_metadata().get("redirect_uri") or "").strip()
            if configured_redirect_uri:
                return configured_redirect_uri
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
            try:
                self._enforce_origin_policy()
                self.send_response(HTTPStatus.NO_CONTENT)
                for key, value in self._cors_headers().items():
                    self.send_header(key, value)
                self.end_headers()
            except PermissionError as exc:
                self._send_error(HTTPStatus.FORBIDDEN, "forbidden", str(exc))

        def do_GET(self):  # noqa: N802
            try:
                self._enforce_origin_policy()
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
                if segments == ["dev", "bootstrap-auth"]:
                    user = application.upsert_user(
                        {
                            "email": "admin@runr.local",
                            "display_name": "Runr Admin",
                            "role": "admin",
                            "allowed_workspace_ids": [],
                        }
                    )
                    token, raw_token = application.issue_api_token(
                        user_id=user.user_id,
                        name="frontend-dev",
                        scopes=[],
                    )
                    self._send_json(
                        {
                            "api_base_url": self._request_api_prefix() or "/v1",
                            "access_token": raw_token,
                            "user": user.to_dict(),
                            "token": token.to_public_dict(),
                        }
                    )
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
                if segments == ["referrals", "outreach-statuses"]:
                    user, _ = self._require_identity()
                    limit = _parse_int_param(query, "limit", default=100, maximum=1000)
                    offset = _parse_int_param(query, "offset", default=0, maximum=100000)
                    items = _collect_referral_outreach_entries(
                        application,
                        user,
                        contact_id=str((query.get("contact_id") or [""])[0]).strip(),
                        run_id=str((query.get("run_id") or [""])[0]).strip(),
                        job_id=str((query.get("job_id") or [""])[0]).strip(),
                    )
                    paged_items = items[offset : offset + limit]
                    self._send_json(
                        {
                            "items": paged_items,
                            "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(paged_items)),
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
                    workspaces = {workspace.id: workspace for workspace in self._authorized_workspaces(user)}
                    runs = self._authorized_runs(user, limit=limit, offset=offset, status=status, workspace_id=workspace_id)
                    self._send_json(
                        {
                            "runs": [
                                {
                                    **_run_summary(item),
                                    "workspace_name": (
                                        workspaces[item.workspace_id].name
                                        if item.workspace_id in workspaces
                                        else item.workspace_id
                                    ),
                                }
                                for item in runs
                            ],
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
                            "columns": TRACKER_TABLE_COLUMNS,
                            "excel_baseline_columns": TRACKER_EXCEL_BASELINE_COLUMNS,
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
                            "groups": _document_group_payloads(entries),
                            "meta": self._pagination_meta(limit=limit, offset=offset, returned=len(paged_entries)),
                        }
                    )
                    return
                if segments[:2] == ["documents", "assets"] and len(segments) == 4 and segments[3] == "download":
                    user, _ = self._require_scope(TOKEN_SCOPE_ARTIFACTS_READ)
                    document_id = _document_id_for_candidate_asset(segments[2])
                    document = _find_document_entry(application, user, document_id)
                    _assert_document_export_allowed(
                        document,
                        export_anyway=_parse_bool_param(query, "export_anyway"),
                    )
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
                if segments[:1] == ["runs"] and len(segments) == 3 and segments[2] == "customer-view":
                    user, _ = self._require_identity()
                    run = application.get_run(segments[1])
                    if not application.user_can_access_workspace(user, run.workspace_id):
                        raise PermissionError(f"Workspace access denied for '{run.workspace_id}'.")
                    self._send_json(_collect_run_customer_view(application, user, run))
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
                    document_id = _document_id_for_artifact(segments[1], segments[3])
                    document = _find_document_entry(application, self._require_identity()[0], document_id)
                    _assert_document_export_allowed(
                        document,
                        export_anyway=_parse_bool_param(query, "export_anyway"),
                    )
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
            except BackendValidationError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, exc.error_code, str(exc), details=dict(exc.details))
            except AtsExportBlockedError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, "ats_export_blocked", str(exc), details={"gate": exc.gate})
            except ValueError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, "bad_request", str(exc))
            except Exception as exc:
                self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", str(exc))

        def do_POST(self):  # noqa: N802
            try:
                self._enforce_origin_policy()
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
                    tags = [asset_kind]
                    asset_metadata: dict[str, Any] = {}
                    if asset_kind in {"workspace_cv", "master_career_profile"}:
                        cv_text = _extract_text_from_uploaded_file(filename, file_bytes)
                        if not cv_text:
                            raise ValueError(f"Could not extract any text from uploaded file '{filename}'.")
                        extraction = extract_cv_profile(cv_text)
                        asset_metadata = {
                            "source_text": cv_text,
                            "source_char_count": len(cv_text),
                            "parsed_profile": dict(extraction.get("profile") or {}),
                            "profile_extraction": {
                                "provider": str(extraction.get("provider") or ""),
                                "model": str(extraction.get("model") or ""),
                                "warnings": list(extraction.get("warnings") or []),
                                "extracted_at": str(extraction.get("extracted_at") or ""),
                            },
                        }
                        tags = (
                            ["cv", "workspace_cv"]
                            if asset_kind == "workspace_cv"
                            else ["career_profile", "master_career_profile"]
                        )
                    asset = _store_candidate_asset_upload(
                        application,
                        user,
                        filename=filename,
                        file_bytes=file_bytes,
                        asset_kind=asset_kind,
                        display_name=display_name,
                        workspace_id=workspace_id,
                        role=asset_kind,
                        tags=tags,
                        metadata=asset_metadata,
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
                    extraction = extract_cv_profile(cv_text)
                    # Save to disk (for legacy pipeline compatibility)
                    cv_save_path = Path("user_config") / "cv_master.txt"
                    cv_save_path.parent.mkdir(parents=True, exist_ok=True)
                    cv_save_path.write_text(cv_text, encoding="utf-8")
                    uploaded_asset = _store_candidate_asset_upload(
                        application,
                        user,
                        filename=filename,
                        file_bytes=file_bytes,
                        asset_kind="workspace_cv",
                        display_name=filename or "Workspace CV",
                        role="workspace_cv",
                        tags=["cv", "workspace_cv"],
                        metadata={
                            "parsed_profile": dict(extraction.get("profile") or {}),
                            "profile_extraction": {
                                "provider": str(extraction.get("provider") or ""),
                                "model": str(extraction.get("model") or ""),
                                "warnings": list(extraction.get("warnings") or []),
                                "extracted_at": str(extraction.get("extracted_at") or ""),
                            },
                        },
                    )
                    # Persist in user metadata
                    user = application.get_user(user.user_id)
                    metadata = dict(user.metadata or {})
                    metadata["cv_text"] = cv_text
                    user.metadata = metadata
                    user.updated_at = datetime.now(timezone.utc).isoformat()
                    application.repositories.auth_repository.upsert_user(user)
                    self._send_json(
                        {
                            "cv_text": cv_text,
                            "char_count": len(cv_text),
                            "filename": filename,
                            "asset": uploaded_asset,
                            "parsed": dict(extraction.get("profile") or {}),
                            "extraction": {
                                "provider": str(extraction.get("provider") or ""),
                                "model": str(extraction.get("model") or ""),
                                "warnings": list(extraction.get("warnings") or []),
                                "extracted_at": str(extraction.get("extracted_at") or ""),
                            },
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

                if segments == ["ats", "export-gate", "evaluate"]:
                    self._require_identity()
                    gate = _evaluate_ats_export_gate_payload(
                        payload,
                        export_anyway=bool(payload.get("export_anyway")),
                    )
                    self._send_json(gate, status=HTTPStatus.OK)
                    return
                if segments == ["tracker", "email-integration", "detections", "approve"]:
                    user, _ = self._require_identity()
                    current_config = _get_tracker_email_config(user)
                    detections_payload = payload.get("detections")
                    if not isinstance(detections_payload, list):
                        detections_payload = [payload.get("detection") or payload]
                    approved: list[dict] = []
                    resolved_detection_ids: set[str] = set()
                    applications = _load_external_tracker_applications(user)
                    for detection_payload in detections_payload:
                        if not isinstance(detection_payload, dict):
                            continue
                        detection = normalize_gmail_application_detection(
                            {
                                **detection_payload,
                                "approval_state": "approved",
                            }
                        )
                        detection_id = _gmail_detection_id(detection)
                        if detection_id:
                            detection["detection_id"] = detection_id
                            resolved_detection_ids.add(detection_id)
                        review_id = str(detection.get("metadata", {}).get("review_id") or "").strip()
                        if review_id:
                            review = application.get_review(review_id)
                            run = application.get_run(review.run_id)
                            if not application.user_can_access_workspace(user, run.workspace_id):
                                raise PermissionError(f"Workspace access denied for '{run.workspace_id}'.")
                            review_meta = dict(review.metadata or {})
                            application_status = normalize_application_status(
                                detection["status"]["suggested_application_status"]
                            )
                            review_meta["application_status"] = application_status
                            review_meta["tracker_status"] = legacy_tracker_status_for_application_status(application_status)
                            if application_status == "Applied":
                                review_meta["email_confirmed"] = True
                            if application_status == "Rejected" and not review_meta.get("rejected_at"):
                                review_meta["rejected_at"] = detection["source_email"]["sent_at"] or datetime.now(timezone.utc).isoformat()
                            review_meta["tracker_email_sync"] = {
                                "message_id": detection["source_email"]["message_id"],
                                "subject": detection["source_email"]["subject"],
                                "from_address": detection["source_email"]["from_address"],
                                "status": review_meta["tracker_status"],
                                "suggested_application_status": application_status,
                                "confidence": detection["status"]["confidence"],
                                "evidence": list(detection["status"]["evidence"] or []),
                                "provider_id": str(detection.get("metadata", {}).get("provider_id") or current_config["provider_id"]),
                                "synced_at": datetime.now(timezone.utc).isoformat(),
                                "approval_state": "approved",
                            }
                            review.metadata = review_meta
                            application.repositories.review_store.upsert_review(review)
                            approved.append({"review_id": review_id, "application_status": application_status})
                            continue
                        external_application = _upsert_external_tracker_application_from_detection(applications, detection)
                        approved.append(external_application)
                    updated_config = dict(current_config)
                    updated_config["pending_detections"] = _merge_pending_tracker_detections(
                        existing=current_config.get("pending_detections") or [],
                        remove_ids=resolved_detection_ids,
                    )
                    if updated_config.get("last_sync_summary"):
                        updated_config["last_sync_summary"] = {
                            **dict(updated_config.get("last_sync_summary") or {}),
                            "pending_review": len(updated_config["pending_detections"]),
                        }
                    refreshed_user = _persist_external_tracker_applications(application, user, applications)
                    refreshed_user = _persist_tracker_email_config(application, refreshed_user, updated_config)
                    self._send_json(
                        {
                            "approved": approved,
                            "tracker": {
                                "items": _collect_tracker_entries(application, refreshed_user),
                                "meta": self._pagination_meta(limit=len(approved), offset=0, returned=len(approved)),
                            },
                            "integration": _tracker_email_integration_payload(application, refreshed_user),
                        },
                        status=HTTPStatus.OK,
                    )
                    return
                if segments == ["tracker", "email-integration", "detections", "dismiss"]:
                    user, _ = self._require_identity()
                    current_config = _get_tracker_email_config(user)
                    detections_payload = payload.get("detections")
                    if not isinstance(detections_payload, list):
                        detections_payload = [payload.get("detection") or payload]
                    dismissed: list[dict] = []
                    resolved_detection_ids: set[str] = set()
                    for detection_payload in detections_payload:
                        if not isinstance(detection_payload, dict):
                            continue
                        detection = normalize_gmail_application_detection(
                            {
                                **detection_payload,
                                "approval_state": "dismissed",
                            }
                        )
                        detection_id = _gmail_detection_id(detection)
                        if detection_id:
                            detection["detection_id"] = detection_id
                            resolved_detection_ids.add(detection_id)
                        dismissed.append(detection)
                    updated_config = dict(current_config)
                    updated_config["pending_detections"] = _merge_pending_tracker_detections(
                        existing=current_config.get("pending_detections") or [],
                        remove_ids=resolved_detection_ids,
                    )
                    if updated_config.get("last_sync_summary"):
                        updated_config["last_sync_summary"] = {
                            **dict(updated_config.get("last_sync_summary") or {}),
                            "pending_review": len(updated_config["pending_detections"]),
                        }
                    refreshed_user = _persist_tracker_email_config(application, user, updated_config)
                    self._send_json(
                        {
                            "dismissed": dismissed,
                            "integration": _tracker_email_integration_payload(application, refreshed_user),
                        },
                        status=HTTPStatus.OK,
                    )
                    return
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
                if segments == ["referrals", "outreach-status"]:
                    user, _ = self._require_identity()
                    self._send_json(
                        _save_referral_outreach_status_from_payload(application, user, payload),
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
                if segments == ["outreach", "target-contact-discovery"]:
                    user, _ = self._require_identity()
                    self._send_json(
                        application.generate_target_contact_discovery(
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
                if segments == ["career-url-discovery", "run"]:
                    self._require_scope(TOKEN_SCOPE_RUNS_WRITE)
                    source = str(payload.get("source") or "regular").strip().lower()
                    if source not in {"regular", "phd", "all"}:
                        raise ValueError("Choose regular companies, universities/PhD, or all sources.")
                    raw_limit = payload.get("limit")
                    limit = 25 if raw_limit in {None, ""} else int(raw_limit)
                    limit = max(0, min(5000, limit))
                    offset = max(0, int(payload.get("offset") or 0))
                    discovery_args = SimpleNamespace(
                        source=source,
                        input=str(payload.get("input") or ""),
                        input_format="auto",
                        company_name_column="",
                        homepage_url_column="",
                        homepage_url="",
                        domain="",
                        company_name="",
                        limit=limit,
                        offset=offset,
                        timeout_seconds=max(5, min(60, int(payload.get("timeout_seconds") or 20))),
                        shallow_crawl_pages=max(0, min(20, int(payload.get("shallow_crawl_pages") or 8))),
                        use_rendered_fallback=bool(payload.get("use_rendered_fallback") or False),
                        allow_domain_guessing=False,
                        output_json=str(payload.get("output_json") or ""),
                        output_company_sites=str(payload.get("output_company_sites") or ""),
                        save_mysql=bool(payload.get("save_mysql") or False),
                        mysql_host=str(payload.get("mysql_host") or ""),
                        mysql_port=int(payload.get("mysql_port") or 0),
                        mysql_user=str(payload.get("mysql_user") or ""),
                        mysql_password=str(payload.get("mysql_password") or ""),
                        mysql_database=str(payload.get("mysql_database") or ""),
                        mysql_table=str(payload.get("mysql_table") or ""),
                    )
                    result = run_career_url_discovery(discovery_args)
                    compact_results = []
                    for item in result.get("results", []):
                        compact_results.append(
                            {
                                "company_name": item.get("company_name", ""),
                                "homepage_url": item.get("homepage_url", ""),
                                "primary_career_url": item.get("primary_career_url", ""),
                                "secondary_candidate_urls": item.get("secondary_candidate_urls", []),
                                "ats_type": item.get("ats_type", ""),
                                "confidence_score": item.get("confidence_score", 0),
                                "crawl_status": item.get("crawl_status", ""),
                                "validation_evidence": item.get("validation_evidence", []),
                            }
                        )
                    self._send_json(
                        {
                            "processed": result.get("processed", 0),
                            "found": result.get("found", 0),
                            "not_found": result.get("not_found", 0),
                            "saved_list_path": result.get("output_company_sites", ""),
                            "details_path": result.get("output_json", ""),
                            "company_site_entries": result.get("company_site_entries", 0),
                            "mysql_rows_saved": result.get("mysql_rows_saved", 0),
                            "results": compact_results,
                        },
                        status=HTTPStatus.OK,
                    )
                    return
                if segments == ["workspaces"]:
                    user, _ = self._require_scope(TOKEN_SCOPE_WORKSPACES_WRITE)
                    workspace_id = str(payload.get("id") or "")
                    if workspace_id and not application.user_can_access_workspace(user, workspace_id):
                        raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
                    self._send_json(application.upsert_workspace(payload).to_dict(), status=HTTPStatus.CREATED)
                    return
                if segments == ["quick-apply", "runs"]:
                    user, _ = self._require_scope(TOKEN_SCOPE_RUNS_WRITE)
                    workspace_id = str(payload.get("workspace_id") or "").strip()
                    if not workspace_id:
                        raise ValueError("workspace_id is required")
                    if not application.user_can_access_workspace(user, workspace_id):
                        raise PermissionError(f"Workspace access denied for '{workspace_id}'.")
                    execution_mode = str(payload.get("execution_mode") or "sync").strip().lower()
                    max_attempts = max(1, int(payload.get("max_attempts") or 1))
                    manual_urls = payload.get("manual_urls") or payload.get("urls") or []
                    if execution_mode == "queued":
                        run, invalid_entries = application.start_quick_apply_run(
                            workspace_id,
                            manual_urls=manual_urls,
                            execute=False,
                            enqueue=True,
                            requested_by=f"api:{user.user_id}",
                            max_attempts=max_attempts,
                        )
                    elif execution_mode == "planned":
                        run, invalid_entries = application.start_quick_apply_run(
                            workspace_id,
                            manual_urls=manual_urls,
                            execute=False,
                            enqueue=False,
                            requested_by=f"api:{user.user_id}",
                            max_attempts=max_attempts,
                        )
                    elif execution_mode == "sync":
                        run, invalid_entries = application.start_quick_apply_run(
                            workspace_id,
                            manual_urls=manual_urls,
                            execute=True,
                            enqueue=False,
                            requested_by=f"api:{user.user_id}",
                            max_attempts=max_attempts,
                        )
                    else:
                        raise ValueError("execution_mode must be one of: queued, planned, sync")
                    self._send_json(
                        {
                            "run": run.to_dict(),
                            "accepted_url_count": int(run.metadata.get("accepted_url_count") or 0),
                            "invalid_entries": invalid_entries,
                        },
                        status=HTTPStatus.CREATED,
                    )
                    return
                if segments == ["workspace-builder", "workspaces"]:
                    user, _ = self._require_scope(TOKEN_SCOPE_WORKSPACES_WRITE)
                    prepared_payload, runtime_settings = _prepare_workspace_builder_payload_with_cv(payload, user)
                    workspace = application.create_workspace_from_scratch(prepared_payload)
                    workspace = _persist_workspace_runtime_settings(application, workspace, runtime_settings)
                    self._send_json(workspace.to_dict(), status=HTTPStatus.CREATED)
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
                        export_anyway=bool(payload.get("export_anyway")),
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
                if segments[:1] == ["runs"] and len(segments) == 5 and segments[2] == "excluded-jobs" and segments[4] == "generate-documents":
                    user, _ = self._require_scope(TOKEN_SCOPE_RUNS_WRITE)
                    run = application.get_run(segments[1])
                    if not application.user_can_access_workspace(user, run.workspace_id):
                        raise PermissionError(f"Workspace access denied for '{run.workspace_id}'.")
                    job_id = str(segments[3] or "").strip()
                    if not job_id:
                        raise ValueError("job_id is required")
                    execution_mode = str(payload.get("execution_mode") or "queued").strip().lower()
                    document_run = application.requeue_job_for_generation(
                        run_id=segments[1],
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
                        run_id=segments[1],
                        job_id=job_id,
                        reviewer=reviewer_name,
                        reason_summary=reason_summary,
                        source_stage=source_stage,
                        notes=str(payload.get("notes") or ""),
                        requeue_run_id=document_run.id,
                    )
                    self._send_json(
                        {
                            "run": document_run.to_dict(),
                            "review": review,
                        },
                        status=HTTPStatus.CREATED,
                    )
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
                    if "scan_window" in payload and payload.get("scan_window") is not None:
                        merged_payload["scan_window"] = normalize_gmail_scan_window(payload.get("scan_window"))
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
                    if "scan_window" in payload and payload.get("scan_window") is not None:
                        current_config["scan_window"] = normalize_gmail_scan_window(payload.get("scan_window"))
                    if "max_messages" in payload and payload.get("max_messages") is not None:
                        current_config["max_messages"] = payload.get("max_messages")
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
                        error_text = str(exc)
                        failed_config["last_error"] = error_text
                        if "invalid_grant" in error_text.lower() or "expired or revoked" in error_text.lower():
                            failed_config["connected"] = False
                            failed_config["authorization_state"] = "reauthorization_required"
                        failed_config["updated_at"] = datetime.now(timezone.utc).isoformat()
                        _persist_tracker_email_config(application, user, failed_config)
                        raise
                    updated_config["processed_message_ids"] = result["processed_message_ids"]
                    updated_config["last_sync_at"] = result["synced_at"]
                    updated_config["updated_at"] = result["synced_at"]
                    updated_config["last_error"] = ""
                    updated_config["last_sync_summary"] = dict(result["summary"] or {})
                    updated_config["pending_detections"] = _merge_pending_tracker_detections(
                        existing=current_config.get("pending_detections") or [],
                        additions=[
                            detection
                            for detection in result.get("detections") or []
                            if isinstance(detection, dict)
                            and str(detection.get("status", {}).get("approval_state") or "") == "pending_review"
                        ],
                    )
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
            except BackendValidationError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, exc.error_code, str(exc), details=dict(exc.details))
            except AtsExportBlockedError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, "ats_export_blocked", str(exc), details={"gate": exc.gate})
            except ValueError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, "bad_request", str(exc))
            except Exception as exc:
                self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", str(exc))

        def do_PUT(self):  # noqa: N802
            try:
                self._enforce_origin_policy()
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
                if segments == ["referrals", "outreach-status"]:
                    user, _ = self._require_identity()
                    self._send_json(
                        _save_referral_outreach_status_from_payload(application, user, payload),
                        status=HTTPStatus.OK,
                    )
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
                    user, _ = self._require_workspace_access(
                        workspace_id=segments[2],
                        required_scope=TOKEN_SCOPE_WORKSPACES_WRITE,
                    )
                    existing_workspace = application.get_workspace(segments[2])
                    prepared_payload, runtime_settings = _prepare_workspace_builder_payload_with_cv(
                        payload,
                        user,
                        existing_workspace=existing_workspace,
                    )
                    workspace = application.update_workspace_from_scratch(segments[2], prepared_payload)
                    workspace = _persist_workspace_runtime_settings(application, workspace, runtime_settings)
                    self._send_json(workspace.to_dict(), status=HTTPStatus.OK)
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
                        merged_config["pending_detections"] = []
                    refreshed_user = _persist_tracker_email_config(application, user, merged_config)
                    self._send_json(_tracker_email_integration_payload(application, refreshed_user), status=HTTPStatus.OK)
                    return
                if segments[:1] == ["tracker"] and len(segments) == 2:
                    # PUT /tracker/:review_id — update tracker_status, email_confirmed, rejection_note
                    user, _ = self._require_identity()
                    if segments[1].startswith("external_"):
                        _, updated_external = _update_external_tracker_application(
                            application,
                            user,
                            segments[1],
                            payload,
                        )
                        self._send_json(
                            {
                                "review_id": updated_external["review_id"],
                                "application_id": updated_external["application_id"],
                                "tracker_status": str(updated_external.get("tracker_status") or ""),
                                "application_status": normalize_application_status(
                                    updated_external.get("application_status") or updated_external.get("tracker_status"),
                                ),
                                "email_confirmed": bool(updated_external.get("email_confirmed") or False),
                                "rejection_note": str(updated_external.get("rejection_note") or ""),
                                "notes": str(updated_external.get("notes") or ""),
                                "updated_at": str(updated_external.get("updated_at") or ""),
                            },
                            status=HTTPStatus.OK,
                        )
                        return
                    review = application.get_review(segments[1])
                    run = application.get_run(review.run_id)
                    if not application.user_can_access_workspace(user, run.workspace_id):
                        raise PermissionError(f"Workspace access denied for '{run.workspace_id}'.")
                    review_meta = dict(review.metadata or {})
                    allowed_tracker_statuses = {
                        "applied",
                        "email_confirmed",
                        "interview_invited",
                        "rejected",
                        "not_applied",
                        "offer",
                        "withdrawn",
                        "unknown",
                    }
                    if "tracker_status" in payload:
                        new_status = str(payload["tracker_status"]).strip().lower()
                        if new_status and new_status not in allowed_tracker_statuses:
                            raise ValueError(f"tracker_status must be one of: {sorted(allowed_tracker_statuses)}")
                        review_meta["tracker_status"] = new_status
                        review_meta["application_status"] = normalize_application_status(new_status)
                    if "application_status" in payload:
                        application_status = normalize_application_status(payload.get("application_status"), default="")
                        if not application_status:
                            raise ValueError("application_status is required")
                        review_meta["application_status"] = application_status
                        review_meta["tracker_status"] = legacy_tracker_status_for_application_status(application_status)
                    if "email_confirmed" in payload:
                        review_meta["email_confirmed"] = bool(payload["email_confirmed"])
                    if "rejection_note" in payload:
                        review_meta["rejection_note"] = str(payload["rejection_note"])
                    if "notes" in payload:
                        review.notes = str(payload.get("notes") or "")
                        review_meta["notes"] = review.notes
                    if (
                        review_meta.get("tracker_status") == "rejected"
                        or review_meta.get("application_status") == "Rejected"
                    ) and not review_meta.get("rejected_at"):
                        review_meta["rejected_at"] = datetime.now(timezone.utc).isoformat()
                    review.metadata = review_meta
                    application.repositories.review_store.upsert_review(review)
                    self._send_json(
                        {
                            "review_id": review.review_id,
                            "tracker_status": str(review_meta.get("tracker_status") or ""),
                            "application_status": normalize_application_status(
                                review_meta.get("application_status") or review_meta.get("tracker_status"),
                            ),
                            "email_confirmed": bool(review_meta.get("email_confirmed") or False),
                            "rejection_note": str(review_meta.get("rejection_note") or ""),
                            "notes": str(review.notes or review_meta.get("notes") or ""),
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
            except BackendValidationError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, exc.error_code, str(exc), details=dict(exc.details))
            except AtsExportBlockedError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, "ats_export_blocked", str(exc), details={"gate": exc.gate})
            except ValueError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, "bad_request", str(exc))
            except Exception as exc:
                self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", str(exc))

        def do_DELETE(self):  # noqa: N802
            try:
                self._enforce_origin_policy()
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
                if segments[:1] == ["tracker"] and len(segments) == 2:
                    user, _ = self._require_identity()
                    if segments[1].startswith("external_"):
                        _, deleted_external = _delete_external_tracker_application(
                            application,
                            user,
                            segments[1],
                        )
                        self._send_json(
                            {
                                "deleted": deleted_external["review_id"],
                                "application_id": deleted_external["application_id"],
                            },
                            status=HTTPStatus.OK,
                        )
                        return
                    review = application.get_review(segments[1])
                    run = application.get_run(review.run_id)
                    if not application.user_can_access_workspace(user, run.workspace_id):
                        raise PermissionError(f"Workspace access denied for '{run.workspace_id}'.")
                    application.delete_job(review.run_id, review.job_id)
                    self._send_json(
                        {
                            "deleted": review.review_id,
                            "run_id": review.run_id,
                            "job_id": review.job_id,
                        },
                        status=HTTPStatus.OK,
                    )
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
                if segments[:1] == ["runs"] and len(segments) == 5 and segments[2] == "jobs" and segments[3] == "by-id":
                    run = application.get_run(segments[1])
                    self._require_workspace_access(workspace_id=run.workspace_id, required_scope=TOKEN_SCOPE_RUNS_WRITE)
                    application.delete_job(segments[1], segments[4])
                    self._send_json({"deleted": segments[4], "run_id": segments[1]}, status=HTTPStatus.OK)
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
            except BackendValidationError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, exc.error_code, str(exc), details=dict(exc.details))
            except AtsExportBlockedError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, "ats_export_blocked", str(exc), details={"gate": exc.gate})
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
    allowed_origins, allow_all_origins = _parse_allowed_origins(os.getenv("BACKEND_ALLOWED_ORIGINS", ""))
    server = ThreadingHTTPServer(
        (host, int(port)),
        build_handler(application, allowed_origins=allowed_origins, allow_all_origins=allow_all_origins),
    )
    print(f"Unified backend API listening on http://{host}:{port}")
    server.serve_forever()
