"""Read-only reconciliation of checked-in/imported company URLs."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from backend.domain.company_identity import (
    canonical_url_lifecycle,
    canonical_url_type,
    structural_url,
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        _text(row.get("company_id")),
        canonical_url_type(row.get("url_type") or row.get("type")),
        _text(row.get("canonical_url")),
    )


def _normalise(row: Mapping[str, Any]) -> dict[str, Any]:
    original, canonical, reason = structural_url(row.get("url") or row.get("canonical_url"))
    lifecycle = canonical_url_lifecycle(row.get("url_lifecycle") or row.get("lifecycle") or "discovered")
    if not canonical:
        lifecycle = "invalid"
    return {
        **dict(row),
        "company_id": _text(row.get("company_id")),
        "url": original,
        "canonical_url": canonical,
        "url_type": canonical_url_type(row.get("url_type") or row.get("type")),
        "url_lifecycle": lifecycle,
        "validation_reason": _text(row.get("validation_reason")) or reason,
    }


def build_url_reconciliation_report(
    checked_in_urls: Iterable[Mapping[str, Any]] = (),
    imported_urls: Iterable[Mapping[str, Any]] = (),
    persisted_urls: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Compare URL occurrences without importing or mutating anything."""

    checked = [_normalise(row) for row in checked_in_urls]
    imported = [_normalise(row) for row in imported_urls]
    persisted = [_normalise(row) for row in persisted_urls]

    def loose_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
        company_id, url_type, canonical = _key(row)
        return (company_id, url_type, canonical) if company_id else ("", url_type, canonical)

    persisted_by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in persisted:
        if row["canonical_url"]:
            persisted_by_key[loose_key(row)].append(row)

    imported_by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in imported:
        imported_by_key[loose_key(row)].append(row)

    report: dict[str, Any] = {
        "schema_version": "company_url_reconciliation_v1",
        "read_only": True,
        "counts": {
            "persisted": 0,
            "deduplicated": 0,
            "unlinked": 0,
            "never_imported": 0,
            "invalid": 0,
            "intentionally_ignored": 0,
        },
        "persisted": [],
        "deduplicated": [],
        "unlinked": [],
        "never_imported": [],
        "invalid": [],
        "intentionally_ignored": [],
    }

    seen_persisted: set[tuple[str, str, str]] = set()
    for row in imported:
        key = loose_key(row)
        lifecycle = row["url_lifecycle"]
        if lifecycle in {"ignored", "rejected"}:
            bucket = "intentionally_ignored"
        elif lifecycle == "invalid" or not row["canonical_url"]:
            bucket = "invalid"
        elif key in persisted_by_key:
            bucket = "persisted" if key not in seen_persisted else "deduplicated"
            seen_persisted.add(key)
        else:
            bucket = "unlinked"
        report[bucket].append(row)
        report["counts"][bucket] += 1

    imported_keys = set(imported_by_key)
    for row in checked:
        key = loose_key(row)
        if row["url_lifecycle"] in {"ignored", "rejected"}:
            bucket = "intentionally_ignored"
        elif row["url_lifecycle"] == "invalid" or not row["canonical_url"]:
            bucket = "invalid"
        elif key not in imported_keys and key not in persisted_by_key:
            bucket = "never_imported"
        else:
            continue
        report[bucket].append(row)
        report["counts"][bucket] += 1

    if not imported:
        for row in persisted:
            key = loose_key(row)
            if key in seen_persisted:
                continue
            seen_persisted.add(key)
            report["persisted"].append(row)
            report["counts"]["persisted"] += 1

    return report


__all__ = ["build_url_reconciliation_report"]
