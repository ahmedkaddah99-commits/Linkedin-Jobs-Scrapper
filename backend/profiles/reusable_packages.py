from pathlib import Path

from backend.config.reusable_packages import cfg_str, load_reusable_packages_config, resolve_path


FALLBACK_CV_TEXT = "Ahmed Kaddah - reliable operational candidate with logistics and operations experience."
MODULE_DIR = Path(__file__).resolve().parent
DEFAULT_BASELINE_PATH = MODULE_DIR / "baseline_cv_reusable_packages.txt"


def load_baseline_profile_text() -> str:
    config = load_reusable_packages_config()
    configured_path = cfg_str(config, ("candidate", "baseline_cv_path"), "baseline_cv_reusable_packages.txt")
    candidate_paths = [
        DEFAULT_BASELINE_PATH,
        resolve_path(configured_path),
        resolve_path("baseline_cv_reusable_packages.txt"),
    ]

    for path in candidate_paths:
        if path.exists() and path.is_file():
            text = path.read_text(encoding="utf-8").strip()
            if text:
                return text

    return FALLBACK_CV_TEXT


def load_baseline_profile_path() -> Path:
    config = load_reusable_packages_config()
    configured_path = cfg_str(config, ("candidate", "baseline_cv_path"), "baseline_cv_reusable_packages.txt")
    candidate_paths = [
        DEFAULT_BASELINE_PATH,
        resolve_path(configured_path),
        resolve_path("baseline_cv_reusable_packages.txt"),
    ]
    for path in candidate_paths:
        if path.exists():
            return path
    return DEFAULT_BASELINE_PATH


__all__ = [
    "FALLBACK_CV_TEXT",
    "load_baseline_profile_path",
    "load_baseline_profile_text",
]
