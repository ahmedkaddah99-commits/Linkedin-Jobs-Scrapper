from __future__ import annotations

import os
from pathlib import Path

from backend.config.job_seeker import cfg_str, load_job_seeker_config, normalize_windows_env_path


DEFAULT_CV_PATH = "user_config/cv_master.txt"
DEFAULT_CV_DOCX_PATH = "Ahmed Kaddah CV.docx"
FALLBACK_CV_TEXT = "Ahmed Kaddah - Business Transformation and AI Specialist."


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


def load_cv_text() -> str:
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
            if path.suffix.lower() == ".docx":
                text = _load_docx_text(path)
            else:
                text = path.read_text(encoding="utf-8").strip()
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
    "load_cv_text",
]
