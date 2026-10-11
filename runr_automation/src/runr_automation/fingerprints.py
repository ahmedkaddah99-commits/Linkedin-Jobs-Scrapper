"""Stable fingerprints for remote issue content."""

from __future__ import annotations

import hashlib
import json
import re

from .linear_client import RemoteIssue


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())


def _canonicalize(value):
    if isinstance(value, dict):
        return {str(key): _canonicalize(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        return [_canonicalize(item) for item in value]
    if isinstance(value, str):
        return _normalize(value)
    return value


def normalized_issue_fingerprint(issue: RemoteIssue) -> str:
    canonical = {
        "title": _normalize(issue.title),
        "description": _normalize(issue.description),
        "lifecycle_state": _normalize(issue.lifecycle_state or ""),
        "project_id": issue.project_id or "",
        "label_ids": sorted(issue.label_ids),
    }
    for key in (
        "goal",
        "acceptance_criteria",
        "allowed_paths",
        "co_owners",
        "required_reading",
        "research_questions",
        "blocking_relations",
        "scope_resources",
        "priority",
        "estimate",
        "implementation_complete",
        "entities",
        "dependency_evidence",
        "subsystem",
    ):
        if key in issue.payload:
            canonical[key] = _canonicalize(issue.payload[key])
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
