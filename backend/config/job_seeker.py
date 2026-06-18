from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any, Iterable


DEFAULT_USER_CONFIG_DIR = "user_config"
DEFAULT_CONFIG_FILE_NAME = "job_seeker_config.json"
DEFAULT_CONFIG_PATH = Path(DEFAULT_USER_CONFIG_DIR) / DEFAULT_CONFIG_FILE_NAME
LEGACY_CONFIG_PATH = Path(DEFAULT_CONFIG_FILE_NAME)
DEFAULT_ENV_PATH = Path(DEFAULT_USER_CONFIG_DIR) / ".env"
LEGACY_ENV_PATH = Path(".env")
DEV_ENV_PATH = Path("dev.env")


DEFAULT_JOB_SEEKER_CONFIG = {
    "candidate": {
        "name": "Kaddah Ahmed",
        "email": "ahmed.kaddah@tutamail.com",
        "cv_path": "user_config/cv_master.txt",
        "cv_docx_path": "Ahmed Kaddah CV.docx",
        "profile_image_path": "",
        "profile_links": {
            "linkedin": {
                "url": "",
                "text": "",
                "icon": "in",
                "logo_path": "",
            },
            "github": {
                "url": "",
                "text": "",
                "icon": "GH",
                "logo_path": "",
            },
        },
        "cv_font": "Calibri",
        "languages": [
            "Arabic - Native",
            "English - C1",
            "German - B1/B2",
        ],
    },
    "job_search": {
        "keywords": [
            "analyst",
            "consultant",
            "product manager",
            "product Owner",
            "project manager",
            "business process manager",
            "intern",
        ],
        "linkedin_geo_id": "101282230",
        "time_posted_seconds": 86400,
        "experience_levels": [1, 2, 3],
        "forbidden_title_keywords": [
            "senior",
            "engineer",
            "sr",
            "sr.",
            "lead",
            "principal",
            "head",
            "director",
        ],
        "priority": {
            "low_applicant_threshold": 80,
        },
    },
    "pipeline": {
        "start_stage": 1,
        "end_stage": 4,
        "sleep_between_seconds": 2.0,
        "python_executable": "",
        "force_stage3_reprocess": False,
        "force_stage4_regenerate": False,
    },
    "runtime": {
        "stage1": {
            "max_pages": 400,
            "max_enrich_jobs": 2000,
            "output_json": "highly_curated_jobs.json",
            "excluded_output_json": "deepseek_excluded_jobs.json",
            "scrape_snapshot_json": "stage1_scrape_snapshot.json",
            "reuse_scrape_snapshot": False,
            "debug_enrich_blocks": True,
            "page_fetch_sleep_seconds": 1.0,
            "use_scrapeops_proxy_fallback": False,
        },
        "stage2": {
            "input_json": "highly_curated_jobs.json",
            "output_json": "stage2_filtered_local.json",
            "rejected_output_json": "stage2_rejected_local.json",
            "german_special_char_threshold": 9999,
            "french_special_char_threshold": 0,
            "spanish_special_char_threshold": 0,
            "max_german_level": "B2",
        },
        "stage3": {
            "input_json": "stage2_filtered_local.json",
            "output_json": "stage3_filtered_ai.json",
            "rejected_output_json": "stage3_rejected_local.json",
            "checkpoint_json": "stage3_checkpoint.json",
            "batch_size": 30,
            "sleep_seconds": 3.0,
            "retries": 3,
            "retry_sleep_seconds": 3.0,
            "german_special_char_threshold": 9999,
            "french_special_char_threshold": 0,
            "spanish_special_char_threshold": 0,
            "max_german_level": "B2",
            "force_reprocess": False,
        },
        "stage4": {
            "input_json": "stage3_filtered_ai.json",
            "checkpoint_json": "stage4_checkpoint.json",
            "sleep_seconds": 4.0,
            "retries": 3,
            "retry_sleep_seconds": 3.0,
            "max_jobs": 0,
            "excel_mode": "new-sheet",
            "sheet_name": "",
            "run_date": "",
            "force_regenerate": False,
        },
        "manual_urls": {
            "input_file": "user_config/manual_job_urls.txt",
            "output_json": "manual_url_jobs.json",
            "failed_output_json": "manual_url_failures.json",
            "request_timeout_seconds": 45,
            "dedupe_against_tracker": True,
        },
    },
    "ai": {
        "models": {
            "stage1_title_filter": "deepseek-chat",
            "stage1_title_filter_deepseek": "deepseek-chat",
            "stage3_filter": "gemini-2.5-flash-lite",
            "stage4_docs_deepseek": "deepseek-chat",
            "stage4_docs_fallback_gemini": "gemini-2.5-flash",
        },
        "prompts": {
            "stage1_extra_instructions": "",
            "stage1_prompt_override": (
                "You are an expert career assistant. I will give you my CV summary and a list of job titles.\n\n"
                "MY CV SUMMARY:\n{{CV_SUMMARY}}\n\n"
                "JOB LIST:\n{{JOB_LIST}}\n\n"
                "YOUR TASK:\n"
                "Evaluate every job in the list.\n\n"
                "Rules:\n"
                "- APPROVE a job ONLY IF:\n"
                "  1) The title is relevant to my CV (Business Transformation, AI, Project/Product Management, Consulting, Data/Business Analysis)\n"
                "  2) The title can be English or German\n\n"
                "OUTPUT FORMAT (IMPORTANT):\n"
                "Return ONLY raw JSON (no markdown, no extra text), shaped EXACTLY like this:\n\n"
                "{\n"
                "  \"approved_ids\": [\"123\", \"456\"],\n"
                "  \"excluded\": [\n"
                "    {\n"
                "      \"id\": \"789\",\n"
                "      \"reason\": \"Not relevant\"\n"
                "    },\n"
                "    {\n"
                "      \"id\": \"1011\",\n"
                "      \"reason\": \"Not relevant\"\n"
                "    },\n"
                "    {\n"
                "      \"id\": \"1213\",\n"
                "      \"reason\": \"Not relevant\"\n"
                "    }\n"
                "  ]\n"
                "}\n"
            ),
            "stage3_extra_instructions": "",
            "stage3_prompt_override": (
                "You are a strict career-job screening assistant.\n\n"
                "Candidate CV summary:\n"
                "{{CV_SUMMARY}}\n\n"
                "Jobs to evaluate (JSON):\n"
                "{{JOBS_JSON}}\n\n"
                "Evaluate every job and reject when any of these are true:\n"
                "1) Role is not suitable for this candidate profile. Reject clearly unrelated functions (HR, accounting, recruitment, sales) and highly specialized senior jobs not aligned with candidate experience.\n"
                "2) Job explicitly requires German above B2 (e.g., C1/C2, fluent/native, verhandlungssicher).\n\n"
                "Output requirements:\n"
                "- Return only raw JSON\n"
                "- Do not return markdown\n"
                "- Keep schema exactly:\n"
                "{\n"
                "  \"approved_ids\": [\"123\", \"456\"],\n"
                "  \"excluded\": [\n"
                "    {\"id\": \"789\", \"reason\": \"Not suitable for profile\"},\n"
                "    {\"id\": \"1000\", \"reason\": \"German requirement above B2\"}\n"
                "  ]\n"
                "}\n"
            ),
            "stage4_extra_instructions": "",
            "stage4_prompt_override": "",
        },
    },
    "outputs": {
        "stage4_json": "stage4_documents.json",
        "stage4_xlsx": "final_jobs_with_docs.xlsx",
        "docs_dir": "generated_docs",
    },
}

_CONTROL_CHAR_ESCAPES = {
    7: "\\a",
    8: "\\b",
    9: "\\t",
    10: "\\n",
    11: "\\v",
    12: "\\f",
    13: "\\r",
}


def _resolve_config_path(path_override: str = "") -> Path:
    if path_override:
        return Path(path_override)
    env_path = os.getenv("JOB_SEEKER_CONFIG_PATH", "").strip()
    if env_path:
        return Path(env_path)
    if DEFAULT_CONFIG_PATH.exists():
        return DEFAULT_CONFIG_PATH
    if LEGACY_CONFIG_PATH.exists():
        return LEGACY_CONFIG_PATH
    return DEFAULT_CONFIG_PATH


def _deep_merge(base: Any, override: Any):
    if isinstance(base, dict) and isinstance(override, dict):
        merged = copy.deepcopy(base)
        for key, value in override.items():
            if key in merged:
                merged[key] = _deep_merge(merged[key], value)
            else:
                merged[key] = copy.deepcopy(value)
        return merged
    return copy.deepcopy(override)


def load_job_seeker_config(path_override: str = "") -> dict:
    config_path = _resolve_config_path(path_override=path_override)
    base = copy.deepcopy(DEFAULT_JOB_SEEKER_CONFIG)

    if config_path and str(config_path).strip() and config_path.exists() and config_path.is_file():
        try:
            loaded = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            loaded = {}
        if isinstance(loaded, dict):
            return _deep_merge(base, loaded)
        return base
    return base


def load_project_dotenv(*, override: bool = False) -> None:
    try:
        from dotenv import dotenv_values
    except Exception:
        return

    injected_names = set(os.environ)
    dotenv_paths = (LEGACY_ENV_PATH, DEV_ENV_PATH, DEFAULT_ENV_PATH)
    for dotenv_path in dotenv_paths:
        if not dotenv_path.exists() or not dotenv_path.is_file():
            continue
        for name, value in dotenv_values(dotenv_path=dotenv_path).items():
            if value is None:
                continue
            if override or name not in injected_names:
                os.environ[name] = value


def cfg_get(config: dict, path: Iterable[str], default=None):
    node = config
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node


def cfg_str(config: dict, path: Iterable[str], default: str = "") -> str:
    value = cfg_get(config, path, default)
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def cfg_int(config: dict, path: Iterable[str], default: int = 0) -> int:
    value = cfg_get(config, path, default)
    try:
        return int(value)
    except Exception:
        return int(default)


def cfg_float(config: dict, path: Iterable[str], default: float = 0.0) -> float:
    value = cfg_get(config, path, default)
    try:
        return float(value)
    except Exception:
        return float(default)


def cfg_bool(config: dict, path: Iterable[str], default: bool = False) -> bool:
    value = cfg_get(config, path, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(default)


def cfg_list(config: dict, path: Iterable[str], default=None):
    if default is None:
        default = []
    value = cfg_get(config, path, default)
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        parts = [item.strip() for item in value.split(",")]
        return [item for item in parts if item]
    return copy.deepcopy(default)


def normalize_windows_env_path(raw_path: str) -> str:
    value = (raw_path or "").strip()
    if not value:
        return ""

    if any(ord(ch) < 32 for ch in value):
        repaired = []
        for ch in value:
            code = ord(ch)
            if code < 32:
                repaired.append(_CONTROL_CHAR_ESCAPES.get(code, ""))
            else:
                repaired.append(ch)
        value = "".join(repaired)

    return value
