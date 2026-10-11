"""Subsystem ownership and ticket scope enforcement."""

from __future__ import annotations

import re
import hashlib
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping

import yaml


class ScopeError(ValueError):
    """Raised when a ticket cannot be assigned a safe code scope."""


def normalize_workstream(value: str) -> str:
    match = re.fullmatch(r"WS[- ]?(\d+)", value.strip(), re.IGNORECASE)
    if not match:
        raise ScopeError(f"invalid workstream: {value}")
    return f"WS-{int(match.group(1)):02d}"


@dataclass(frozen=True)
class Subsystem:
    id: str
    workstream: str
    linear_project: str | None
    purpose: str
    owned_globs: tuple[str, ...]
    exclusions: tuple[str, ...]
    documentation: tuple[str, ...]
    verification_commands: tuple[str, ...]

    def owns(self, path: str) -> bool:
        normalized = _normalize_path(path)
        return any(_matches(normalized, pattern) for pattern in self.owned_globs) and not any(
            _matches(normalized, pattern) for pattern in self.exclusions
        )


class SubsystemRegistry(dict[str, Subsystem]):
    def resolve(self, value: str) -> Subsystem:
        normalized = value.strip().casefold()
        normalized_workstream = None
        try:
            normalized_workstream = normalize_workstream(value).casefold()
        except ScopeError:
            pass
        for subsystem in self.values():
            if normalized in {
                subsystem.id.casefold(),
                subsystem.workstream.casefold(),
                (subsystem.linear_project or "").casefold(),
            } or normalized_workstream == subsystem.workstream.casefold():
                return subsystem
        raise ScopeError(f"unknown subsystem: {value}")

    def owners_for_path(self, path: str) -> tuple[Subsystem, ...]:
        normalized = _normalize_path(path)
        return tuple(subsystem for subsystem in self.values() if subsystem.owns(normalized))


def load_registry(path: str) -> SubsystemRegistry:
    with open(path, encoding="utf-8") as stream:
        document = yaml.safe_load(stream) or {}
    registry = SubsystemRegistry()
    for raw in document.get("subsystems", []):
        subsystem = Subsystem(
            id=str(raw["id"]),
            workstream=normalize_workstream(str(raw["workstream"])),
            linear_project=raw.get("linear_project"),
            purpose=str(raw.get("purpose", "")),
            owned_globs=tuple(raw.get("owned_globs", raw.get("owned_paths", []))),
            exclusions=tuple(raw.get("exclusions", [])),
            documentation=tuple(raw.get("documentation", [])),
            verification_commands=tuple(raw.get("verification_commands", [])),
        )
        if subsystem.id in registry:
            raise ScopeError(f"duplicate subsystem id: {subsystem.id}")
        registry[subsystem.id] = subsystem
    return registry


def resolve_primary_subsystem(
    labels: Iterable[Mapping[str, Any]], registry: SubsystemRegistry
) -> str:
    candidates = []
    for label in labels:
        if str(label.get("group", label.get("parent_name", ""))).casefold() != "subsystem":
            continue
        candidates.append(registry.resolve(str(label.get("name", ""))))
    if len(candidates) != 1:
        raise ScopeError("exactly one primary Subsystem label is required")
    return candidates[0].id


@dataclass(frozen=True)
class ScopeManifest:
    issue_id: str
    subsystem: str
    co_owners: tuple[str, ...]
    allowed_reads: tuple[str, ...]
    allowed_writes: tuple[str, ...]
    denied_roots: tuple[str, ...]
    required_tests: tuple[str, ...]
    content_hashes: tuple[tuple[str, str], ...] = ()
    external_verification: tuple[str, ...] = ()

    def validate_write_paths(self, changed_paths: Iterable[str]) -> None:
        invalid = [
            _normalize_path(path)
            for path in changed_paths
            if not any(_matches(_normalize_path(path), pattern) for pattern in self.allowed_writes)
        ]
        if invalid:
            raise ScopeError(f"writes outside allowed paths: {', '.join(sorted(invalid))}")

    def validate_read_paths(self, read_paths: Iterable[str]) -> None:
        invalid = [
            _normalize_path(path)
            for path in read_paths
            if not any(_matches(_normalize_path(path), pattern) for pattern in self.allowed_reads)
        ]
        if invalid:
            raise ScopeError(f"reads outside allowed paths: {', '.join(sorted(invalid))}")


def build_scope_manifest(
    registry: SubsystemRegistry,
    *,
    issue_id: str,
    primary_subsystem: str,
    allowed_paths: Iterable[str],
    required_reading: Iterable[str] = (),
    required_tests: Iterable[str] = (),
    external_verification: Iterable[str] = (),
    co_owners: Iterable[str] = (),
    repo_root: str | Path | None = None,
) -> ScopeManifest:
    primary = registry.resolve(primary_subsystem)
    co_owner_subsystems = tuple(registry.resolve(value) for value in co_owners)
    co_owner_ids = tuple(dict.fromkeys(subsystem.id for subsystem in co_owner_subsystems))
    normalized_allowed = tuple(dict.fromkeys(_normalize_path(path) for path in allowed_paths))
    for path in normalized_allowed:
        owners = registry.owners_for_path(path)
        if not owners:
            raise ScopeError(f"allowed path is outside the subsystem registry: {path}")
        owner_ids = {owner.id for owner in owners}
        if primary.id not in owner_ids and not owner_ids.intersection(co_owner_ids):
            raise ScopeError(
                f"allowed path {path} conflicts with primary subsystem {primary.id}; declare its owner as co-owner"
            )
        undeclared = owner_ids - {primary.id} - set(co_owner_ids)
        if undeclared:
            raise ScopeError(f"allowed path {path} has undeclared co-owner(s): {', '.join(sorted(undeclared))}")

    allowed_reads = tuple(
        dict.fromkeys(
            [
                "AGENTS.md",
                "docs/INDEX.md",
                "docs/subsystems.yaml",
                *primary.documentation,
                *primary.owned_globs,
                *normalized_allowed,
                *(_normalize_path(path) for path in required_reading),
            ]
        )
    )
    allowed_subsystems = {primary.id, *co_owner_ids}
    denied_roots = tuple(
        pattern
        for subsystem in registry.values()
        if subsystem.id not in allowed_subsystems
        for pattern in subsystem.owned_globs
    )
    content_hashes = []
    if repo_root is not None:
        root = Path(repo_root)
        for read_path in allowed_reads:
            if any(char in read_path for char in "*?["):
                continue
            candidate = root / read_path
            if candidate.is_file():
                content_hashes.append(
                    (read_path, hashlib.sha256(candidate.read_bytes()).hexdigest())
                )
    return ScopeManifest(
        issue_id=issue_id,
        subsystem=primary.id,
        co_owners=co_owner_ids,
        allowed_reads=allowed_reads,
        allowed_writes=normalized_allowed,
        denied_roots=denied_roots,
        required_tests=tuple(required_tests),
        content_hashes=tuple(content_hashes),
        external_verification=tuple(external_verification),
    )


def _normalize_path(path: str) -> str:
    normalized = str(path).replace("\\", "/").strip()
    if not normalized or normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        raise ScopeError(f"path must be repository-relative: {path}")
    parts = PurePosixPath(normalized).parts
    if ".." in parts:
        raise ScopeError(f"path may not escape the repository: {path}")
    return normalized.removeprefix("./")


def _matches(path: str, pattern: str) -> bool:
    normalized_pattern = pattern.replace("\\", "/")
    if normalized_pattern.endswith("/**"):
        prefix = normalized_pattern[:-3].rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    return PurePosixPath(path).match(normalized_pattern)
