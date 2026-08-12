"""Loader and redaction guard for local enrichment evaluation fixtures."""

from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
from typing import Any


FIXTURE_DIRECTORY = Path(__file__).with_name("fixtures")
PROHIBITED_KEYS = frozenset(
    {
        "description",
        "full_description",
        "raw_payload",
        "source_raw_payload",
        "email",
        "phone",
        "access_token",
        "secret",
        "api_key",
    }
)


def _load(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Fixture must contain a list: {path}")
    cases: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError(f"Fixture case must be an object: {path}")
        if not item.get("fixture_id") or not item.get("split"):
            raise ValueError(f"Fixture case needs fixture_id and split: {path}")
        if item.get("synthetic") is not True:
            raise ValueError(f"Fixture case must be explicitly synthetic: {item.get('fixture_id')}")
        cases.append(item)
    return cases


def load_evaluation_fixture(*, include_blind_holdout: bool = False) -> list[dict[str, Any]]:
    cases = _load(FIXTURE_DIRECTORY / "normalization_cases.json")
    if include_blind_holdout:
        cases.extend(_load(FIXTURE_DIRECTORY / "normalization_blind_holdout.json"))
    return cases


def assert_sanitized_fixture(record: Mapping[str, Any]) -> None:
    """Fail closed if a fixture accidentally contains sensitive/raw fields."""

    keys = {str(key).casefold() for key in record}
    prohibited = keys & PROHIBITED_KEYS
    if prohibited:
        raise ValueError(f"Fixture contains prohibited keys: {sorted(prohibited)}")
    if len(str(record.get("description_excerpt") or "")) > 1000:
        raise ValueError("Fixture evidence excerpt exceeds 1000 characters")


def validate_fixture_privacy(*, include_blind_holdout: bool = True) -> None:
    for case in load_evaluation_fixture(include_blind_holdout=include_blind_holdout):
        assert_sanitized_fixture(case)


__all__ = [
    "FIXTURE_DIRECTORY",
    "PROHIBITED_KEYS",
    "assert_sanitized_fixture",
    "load_evaluation_fixture",
    "validate_fixture_privacy",
]
