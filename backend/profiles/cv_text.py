from __future__ import annotations

import contextlib
import contextvars
import os
from pathlib import Path
from typing import Any, Iterator, Mapping

from backend.config.job_seeker import cfg_str, load_job_seeker_config, normalize_windows_env_path


DEFAULT_CV_PATH = "user_config/cv_master.txt"
DEFAULT_CV_DOCX_PATH = "Ahmed Kaddah CV.docx"
FALLBACK_CV_TEXT = "Ahmed Kaddah - Business Transformation and AI Specialist."
_RUNTIME_CV_OVERRIDE: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "runtime_cv_override",
    default=None,
)


def _load_docx_text(path: Path) -> str:
    try:
        from docx import Document
    except Exception:
        return ""

    try:
        document = Document(path)
        lines = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
        return "\n".join(lines).strip()
    except Exception:
        return ""


def _load_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except Exception:
        return ""

    try:
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    except Exception:
        return ""


def _load_plain_text(path: Path) -> str:
    for encoding in ("utf-8", "latin-1"):
        try:
            return path.read_text(encoding=encoding).strip()
        except UnicodeDecodeError:
            continue
        except Exception:
            return ""
    return ""


def extract_cv_text_from_path(path: str | Path) -> str:
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return ""
    suffix = file_path.suffix.lower()
    if suffix == ".docx":
        return _load_docx_text(file_path)
    if suffix == ".pdf":
        return _load_pdf_text(file_path)
    return _load_plain_text(file_path)


def get_runtime_cv_override() -> dict[str, Any]:
    return dict(_RUNTIME_CV_OVERRIDE.get() or {})


@contextlib.contextmanager
def runtime_cv_override(snapshot: Mapping[str, Any] | None) -> Iterator[None]:
    token = _RUNTIME_CV_OVERRIDE.set(dict(snapshot or {}))
    try:
        yield
    finally:
        _RUNTIME_CV_OVERRIDE.reset(token)


def resolve_runtime_cv_docx_path() -> Path | None:
    snapshot = get_runtime_cv_override()
    raw_path = str(snapshot.get("path") or snapshot.get("workspace_cv_asset_path") or "").strip()
    if not raw_path:
        return None
    file_path = Path(raw_path)
    if file_path.suffix.lower() != ".docx":
        return None
    return file_path if file_path.exists() and file_path.is_file() else None


def load_cv_text() -> str:
    runtime_override = get_runtime_cv_override()
    override_text = str(runtime_override.get("text") or runtime_override.get("workspace_cv_text") or "").strip()
    if override_text:
        return override_text
    if runtime_override.get("required"):
        raise RuntimeError("The selected workspace CV snapshot is missing text for this run.")

    config = load_job_seeker_config()
    candidate_paths = []

    config_path = normalize_windows_env_path(cfg_str(config, ("candidate", "cv_path"), ""))
    if config_path:
        candidate_paths.append(Path(config_path))

    config_docx_path = normalize_windows_env_path(cfg_str(config, ("candidate", "cv_docx_path"), ""))
    if config_docx_path:
        candidate_paths.append(Path(config_docx_path))

    env_path = normalize_windows_env_path(os.getenv("MY_CV_PATH", ""))
    if env_path:
        candidate_paths.append(Path(env_path))

    candidate_paths.append(Path(DEFAULT_CV_PATH))
    candidate_paths.append(Path(DEFAULT_CV_DOCX_PATH))
    candidate_paths.append(Path(r"C:\Users\ahmed\OneDrive\Personal\CV\Ahmed Kaddah CV.docx"))

    for path in candidate_paths:
        if path.exists() and path.is_file():
            text = extract_cv_text_from_path(path)
            if text:
                return text

    env_text = os.getenv("MY_CV_SUMMARY", "").strip()
    if env_text:
        return env_text

    return FALLBACK_CV_TEXT


__all__ = [
    "DEFAULT_CV_DOCX_PATH",
    "DEFAULT_CV_PATH",
    "FALLBACK_CV_TEXT",
    "extract_cv_text_from_path",
    "get_runtime_cv_override",
    "load_cv_text",
    "resolve_runtime_cv_docx_path",
    "runtime_cv_override",
]
