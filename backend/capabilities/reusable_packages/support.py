from __future__ import annotations

import json
from pathlib import Path

from backend.config.reusable_packages import (
    cfg_bool,
    cfg_float,
    cfg_get,
    cfg_int,
    cfg_list,
    cfg_str,
    load_reusable_packages_config,
    resolve_path,
)
from backend.connectors.job_boards import collect_jobs_from_portals, compact_whitespace
from backend.profiles.reusable_packages import load_baseline_profile_text


def load_json_file(path: Path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json_file(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=4, ensure_ascii=False)


__all__ = [
    "cfg_bool",
    "cfg_float",
    "cfg_get",
    "cfg_int",
    "cfg_list",
    "cfg_str",
    "collect_jobs_from_portals",
    "compact_whitespace",
    "load_baseline_profile_text",
    "load_json_file",
    "load_reusable_packages_config",
    "resolve_path",
    "save_json_file",
]
