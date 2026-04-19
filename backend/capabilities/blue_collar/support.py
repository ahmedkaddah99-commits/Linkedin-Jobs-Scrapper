from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
BLUE_COLLAR_ROOT = REPO_ROOT / "bc_automation"

if str(BLUE_COLLAR_ROOT) not in sys.path:
    sys.path.insert(0, str(BLUE_COLLAR_ROOT))

from blue_collar_config import (  # type: ignore[import-not-found]
    cfg_bool,
    cfg_int,
    cfg_list,
    cfg_str,
    load_blue_collar_config,
    resolve_path,
)
from blue_collar_cv_profile import load_baseline_cv_text  # type: ignore[import-not-found]
from backend.connectors.job_boards import collect_jobs_from_portals, compact_whitespace


def load_json_file(path: Path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json_file(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=4, ensure_ascii=False)
