import copy
import json
import os
from pathlib import Path
from typing import Any, Iterable


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_FILE_NAME = "reusable_packages.json"
DEFAULT_CONFIG_PATH = BASE_DIR / DEFAULT_CONFIG_FILE_NAME


DEFAULT_REUSABLE_PACKAGES_CONFIG = {
    "candidate": {
        "name": "Ahmed Kaddah",
        "email": "ahmed.kaddah@tutamail.com",
        "phone": "",
        "location": "91052 Erlangen / 90402 Nuremberg",
        "availability": "Ab sofort | Vollzeit | Mini-job",
        "languages": [
            "Arabic - Native",
            "English - C1",
            "German - B1/B2",
        ],
        "baseline_cv_path": "baseline_cv_reusable_packages.txt",
        "has_drivers_license": False,
        "has_special_training": False,
    },
    "job_search": {
        "keywords": [
            "lagerhelfer",
            "lagermitarbeiter",
            "warehouse",
            "logistik",
            "reinigungskraft",
            "kuechenhilfe",
            "servicekraft",
            "umzugshelfer",
            "produktionshelfer",
            "zusteller",
        ],
        "cities": [
            "Erlangen",
            "Nuremberg",
            "Nuernberg",
            "Fuerth",
        ],
        "radius_km": 35,
        "posted_within_days": 14,
        "portals": [
            "indeed",
            "arbeitsagentur",
            "linkedin",
            "stepstone",
        ],
        "max_pages_per_source": 2,
        "max_jobs_total": 1200,
    },
    "filters": {
        "exclude_driver_license_required": True,
        "exclude_special_training_required": True,
    },
    "classification": {
        "categories": [
            {
                "id": "moving_helper_loader",
                "name": "Moving / Helper / Loader",
                "description": "Physical helper roles for moving, loading, unloading, packing, setup.",
                "keywords": ["moving", "umzug", "loader", "be- und entladung", "helper", "helfer"],
            },
            {
                "id": "waiter_service_staff",
                "name": "Waiter / Service Staff",
                "description": "Restaurant service, table service, counter, hospitality support.",
                "keywords": ["waiter", "servicekraft", "kellner", "gastronomie", "restaurant", "bar"],
            },
            {
                "id": "cook_kitchen_staff",
                "name": "Cook / Kitchen Staff",
                "description": "Kitchen helper, prep cook, dishwashing, food production support.",
                "keywords": ["cook", "kueche", "kitchen", "spueler", "beikoch", "koch"],
            },
            {
                "id": "warehouse_logistics",
                "name": "Warehouse / Logistics",
                "description": "Warehouse operations, sorting, picking, packing, logistics support.",
                "keywords": ["lager", "warehouse", "logistik", "kommissionierung", "sortierung", "versand"],
            },
            {
                "id": "delivery_driver",
                "name": "Delivery / Driver",
                "description": "Parcel delivery, courier, driving and route-based distribution roles.",
                "keywords": ["delivery", "zusteller", "fahrer", "kurier", "driver", "lieferung"],
            },
            {
                "id": "cleaning_facility_support",
                "name": "Cleaning / Facility Support",
                "description": "Cleaning, janitorial and facility support roles.",
                "keywords": ["cleaning", "reinigung", "housekeeping", "facility", "gebaeudereinigung"],
            },
            {
                "id": "production_packaging",
                "name": "Production / Packaging",
                "description": "Factory helper, production line, packaging, assembly.",
                "keywords": ["produktion", "production", "montage", "verpackung", "factory"],
            },
            {
                "id": "retail_store_support",
                "name": "Retail / Store Support",
                "description": "Store assistant, stockroom, shelf refill, cashier support.",
                "keywords": ["retail", "store", "shop", "verkauf", "kasse", "stockroom"],
            },
            {
                "id": "other_operational",
                "name": "Other Operational",
                "description": "Other operational roles not covered by the main clusters.",
                "keywords": [],
            },
        ]
    },
    "pipeline": {
        "start_stage": 1,
        "end_stage": 5,
        "sleep_between_seconds": 2.0,
        "python_executable": "",
    },
    "runtime": {
        "stage1": {
            "output_json": "outputs/stage1_scraped_jobs.json",
            "snapshot_json": "outputs/stage1_scrape_snapshot.json",
            "source_log_json": "outputs/stage1_source_log.json",
            "reuse_snapshot": False,
            "request_timeout_seconds": 25,
            "arbeitsagentur_detail_fetch_limit": 20,
        },
        "stage2": {
            "input_json": "outputs/stage1_scraped_jobs.json",
            "output_json": "outputs/stage2_filtered_jobs.json",
            "rejected_output_json": "outputs/stage2_rejected_jobs.json",
        },
        "stage3": {
            "input_json": "outputs/stage2_filtered_jobs.json",
            "output_json": "outputs/stage3_classified_jobs.json",
            "role_clusters_json": "outputs/stage3_role_clusters.json",
            "batch_size": 50,
            "retries": 3,
            "retry_sleep_seconds": 2.0,
        },
        "stage4": {
            "input_json": "outputs/stage3_classified_jobs.json",
            "role_cv_output_dir": "outputs/role_cvs",
            "role_cv_index_json": "outputs/stage4_role_cvs.json",
        },
        "stage5": {
            "input_json": "outputs/stage3_classified_jobs.json",
            "role_cv_index_json": "outputs/stage4_role_cvs.json",
            "output_json": "outputs/stage5_application_packages.json",
            "output_xlsx": "outputs/reusable_packages_with_docs.xlsx",
            "docs_dir": "outputs/generated_docs",
        },
    },
    "ai": {
        "models": {
            "role_classifier": "deepseek-chat",
        },
        "prompts": {
            "role_classifier_extra_instructions": "",
            "role_classifier_prompt_override": "",
        },
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


def resolve_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return BASE_DIR / path


def _resolve_config_path(path_override: str = "") -> Path:
    if path_override:
        return Path(path_override)
    env_path = os.getenv("REUSABLE_PACKAGES_CONFIG_PATH", "").strip() or os.getenv("BLUE_COLLAR_CONFIG_PATH", "").strip()
    if env_path:
        return Path(env_path)
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


def load_reusable_packages_config(path_override: str = "") -> dict:
    config_path = _resolve_config_path(path_override=path_override)
    base = copy.deepcopy(DEFAULT_REUSABLE_PACKAGES_CONFIG)

    if config_path and str(config_path).strip() and config_path.exists():
        try:
            loaded = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            loaded = {}
        if isinstance(loaded, dict):
            return _deep_merge(base, loaded)
        return base
    return base


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


__all__ = [
    "DEFAULT_CONFIG_FILE_NAME",
    "DEFAULT_CONFIG_PATH",
    "DEFAULT_REUSABLE_PACKAGES_CONFIG",
    "resolve_path",
    "load_reusable_packages_config",
    "cfg_get",
    "cfg_str",
    "cfg_int",
    "cfg_float",
    "cfg_bool",
    "cfg_list",
    "normalize_windows_env_path",
]
