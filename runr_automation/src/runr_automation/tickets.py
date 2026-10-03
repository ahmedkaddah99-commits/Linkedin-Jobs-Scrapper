"""Normalize canonical Linear ticket descriptions into executable fields."""

from __future__ import annotations

import re
import shlex
from collections.abc import Mapping
from typing import Any


_ALIASES = {
    "primary subsystem": "subsystem",
    "subsystem": "subsystem",
    "allowed paths": "allowed_paths",
    "exact allowed paths": "allowed_paths",
    "source sha and exact source paths": "allowed_paths",
    "minimal required reading": "required_reading",
    "required reading": "required_reading",
    "acceptance criteria": "acceptance_criteria",
    "safe local verification commands": "required_tests",
    "safe verification commands": "required_tests",
    "safe verification": "required_tests",
    "required tests": "required_tests",
    "co owners": "co_owners",
    "co owner subsystem ids": "co_owners",
}

_EXTERNAL_VERIFICATION_EXECUTABLES = {"systemd-analyze"}


def _heading(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _sections(description: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    bold_section = False
    for raw in description.splitlines():
        line = raw.strip()
        if line.startswith("#"):
            current = _ALIASES.get(_heading(line.lstrip("#").strip()))
            bold_section = False
            if current:
                sections.setdefault(current, [])
            continue
        bold = re.fullmatch(r"\*\*(?P<label>.+?):\*\*(?:\s*(?P<value>.*))?", line)
        if bold:
            current = _ALIASES.get(_heading(bold.group("label")))
            bold_section = True
            if current:
                sections.setdefault(current, [])
                _append_section_value(
                    sections,
                    current,
                    bold.group("value") or "",
                    normalize_bold_co_owners=True,
                )
            continue
        if current and line:
            _append_section_value(
                sections,
                current,
                line,
                normalize_bold_co_owners=bold_section,
            )
    return sections


def _append_section_value(
    sections: dict[str, list[str]],
    current: str,
    raw_value: str,
    *,
    normalize_bold_co_owners: bool,
) -> None:
    value = re.sub(r"^[-*]\s+", "", raw_value).strip()
    if not value or value.casefold() in {"none", "n/a"}:
        return
    values = re.split(r"\s*;\s*", value) if current in {
        "allowed_paths",
        "required_reading",
        "co_owners",
    } else [value]
    for item in values:
        item = item.strip()
        if not item:
            continue
        if current == "co_owners" and normalize_bold_co_owners:
            match = re.match(r"^WS[- ]?(\d+)\b", item, re.IGNORECASE)
            if not match:
                continue
            item = f"WS-{int(match.group(1)):02d}"
        sections[current].append(item)


def strip_markdown_wrapper(value: str) -> str:
    cleaned = value.strip()
    while len(cleaned) >= 2 and cleaned[0] == cleaned[-1] == "`":
        cleaned = cleaned[1:-1].strip()
    return cleaned


def _command_name(command: str) -> str | None:
    try:
        args = shlex.split(command, posix=False)
    except ValueError:
        return None
    if not args:
        return None
    return args[0].replace("/", "\\").rsplit("\\", 1)[-1].casefold()


def _partition_verification_commands(values: list[str]) -> tuple[list[str], list[str]]:
    local: list[str] = []
    external: list[str] = []
    for value in values:
        command = strip_markdown_wrapper(value)
        if not command:
            continue
        if _command_name(command) in _EXTERNAL_VERIFICATION_EXECUTABLES:
            external.append(command)
        else:
            local.append(command)
    return local, external


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
    raw_verification = _list(payload.get("required_tests")) or parsed.get("required_tests", [])
    required_tests, discovered_external = _partition_verification_commands(raw_verification)
    explicit_external = [
        strip_markdown_wrapper(value) for value in _list(payload.get("external_verification"))
    ]
    external_verification = list(dict.fromkeys([*explicit_external, *discovered_external]))
    return {
        **dict(payload),
        "title": str(payload.get("title") or "").strip(),
        "acceptance_criteria": str(acceptance or "").strip(),
        "subsystem": str(subsystem).strip() if subsystem else None,
        "allowed_paths": _list(payload.get("allowed_paths")) or parsed.get("allowed_paths", []),
        "required_reading": _list(payload.get("required_reading")) or parsed.get("required_reading", []),
        "required_tests": required_tests,
        "external_verification": external_verification,
        "co_owners": _list(payload.get("co_owners")) or parsed.get("co_owners", []),
    }
