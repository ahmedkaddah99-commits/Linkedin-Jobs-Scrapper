"""Owner-approved employer exclusions shared by collectors and publication."""
from __future__ import annotations

import json
import os
from pathlib import Path


def excluded_company_ids() -> frozenset[str]:
    configured = os.environ.get("RUNR_EMPLOYER_EXCLUSION_POLICY")
    path = Path(configured or "/etc/runr/employer-exclusions.json")
    if not configured and not path.exists():
        return frozenset()
    # An explicitly configured policy must fail closed if missing or malformed.
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported employer exclusion policy")
    ids = payload.get("company_ids")
    if not isinstance(ids, list) or any(not isinstance(v, str) or not v.strip() for v in ids):
        raise ValueError("invalid employer exclusion company IDs")
    return frozenset(ids)
