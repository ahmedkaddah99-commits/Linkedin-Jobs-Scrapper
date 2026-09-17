"""Normalize canonical Linear ticket descriptions into executable fields."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


_ALIASES = {
    "primary subsystem": "subsystem",
    "subsystem": "subsystem",
    "allowed paths": "allowed_paths",
    "source sha and exact source paths": "allowed_paths",
    "minimal required reading": "required_reading",
    "required reading": "required_reading",
    "acceptance criteria": "acceptance_criteria",
    "safe local verification commands": "required_tests",
    "safe verification commands": "required_tests",
    "required tests": "required_tests",
    "co owners": "co_owners",
    "co owner subsystem ids": "co_owners",
}


def _heading(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _sections(description: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for raw in description.splitlines():
        line = raw.strip()
        if line.startswith("#"):
            current = _ALIASES.get(_heading(line.lstrip("#").strip()))
            if current:
                sections.setdefault(current, [])
            continue
        if current and line:
            value = re.sub(r"^[-*]\s+", "", line).strip()
            if value and value.casefold() not in {"none", "n/a"}:
                sections[current].append(value)
    return sections


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item).strip()]
    raise ValueError("ticket list field must be a string or list")


def _subsystem_label(payload: Mapping[str, Any]) -> str | None:
    labels = payload.get("labels") or {}
    nodes = labels.get("nodes", []) if isinstance(labels, Mapping) else []
    candidates = [
        str(label.get("name"))
        for label in nodes
        if isinstance(label, Mapping)
        and isinstance(label.get("parent"), Mapping)
        and str(label["parent"].get("name", "")).casefold() == "subsystem"
    ]
    return candidates[0] if len(candidates) == 1 else None


def normalize_ticket_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    parsed = _sections(str(payload.get("description") or ""))
    acceptance = payload.get("acceptance_criteria")
    if acceptance is None:
        acceptance = "\n".join(parsed.get("acceptance_criteria", []))
    elif isinstance(acceptance, (list, tuple)):
        acceptance = "\n".join(str(item) for item in acceptance)
    subsystem = payload.get("subsystem") or next(iter(parsed.get("subsystem", [])), None) or _subsystem_label(payload)
    return {
        **dict(payload),
        "title": str(payload.get("title") or "").strip(),
        "acceptance_criteria": str(acceptance or "").strip(),
        "subsystem": str(subsystem).strip() if subsystem else None,
        "allowed_paths": _list(payload.get("allowed_paths")) or parsed.get("allowed_paths", []),
        "required_reading": _list(payload.get("required_reading")) or parsed.get("required_reading", []),
        "required_tests": _list(payload.get("required_tests")) or parsed.get("required_tests", []),
        "co_owners": _list(payload.get("co_owners")) or parsed.get("co_owners", []),
    }
