"""Cheap, deterministic pre-detail job-title filter for the owner's target roles."""
from __future__ import annotations

import json, re
from functools import lru_cache
from pathlib import Path

DEFAULT_POLICY_PATH = Path(__file__).resolve().parents[2] / "data" / "job_role_policy.json"

@lru_cache(maxsize=4)
def load_policy(path: str = str(DEFAULT_POLICY_PATH)):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9+#]+", " ", str(title or "").casefold()).strip()

def title_matches(title: str, *, policy_path: str | None = None) -> bool:
    text = normalize_title(title)
    if not text:
        return False
    policy = load_policy(policy_path or str(DEFAULT_POLICY_PATH))
    if any(re.search(pattern, text) for pattern in policy["excluded_title_patterns"]):
        return False
    return any(re.search(pattern, text) for pattern in policy["included_title_patterns"])

def rejection_reason(title: str) -> str:
    return "owner_role_policy_excluded" if not title_matches(title) else ""
