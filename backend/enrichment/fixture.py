"""Loader and redaction guard for local enrichment evaluation fixtures."""

from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
from typing import Any


FIXTURE_DIRECTORY = Path(__file__).with_name("fixtures")
GOLDEN_LABELS_PATH = FIXTURE_DIRECTORY / "golden_labels.json"
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


def load_golden_labels() -> dict[str, dict[str, Any]]:
    """Load adjudicated labels for development/calibration only.

    Blind holdout labels intentionally do not live in the checked-in fixture
    files.  The evaluator therefore treats holdout outputs as unlabeled
    replay/safety evidence and reports the resulting data gap.
    """

    payload = json.loads(GOLDEN_LABELS_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Golden labels must contain a list")
    labels: dict[str, dict[str, Any]] = {}
    for item in payload:
        if not isinstance(item, dict) or not item.get("fixture_id"):
            raise ValueError("Golden label needs fixture_id")
        fixture_id = str(item["fixture_id"])
        split = str(item.get("split") or "")
        if split not in {"development", "calibration"}:
            raise ValueError(f"Golden labels cannot label blind holdout: {fixture_id}")
        if not isinstance(item.get("labels"), dict):
            raise ValueError(f"Golden label needs labels: {fixture_id}")
        adjudication = item.get("adjudication")
        if not isinstance(adjudication, dict) or adjudication.get("status") != "adjudicated":
            raise ValueError(f"Golden label needs adjudication metadata: {fixture_id}")
        if fixture_id in labels:
            raise ValueError(f"Duplicate golden label: {fixture_id}")
        labels[fixture_id] = item
    return labels


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
    for label in load_golden_labels().values():
        assert_sanitized_fixture(label)


__all__ = [
    "FIXTURE_DIRECTORY",
    "GOLDEN_LABELS_PATH",
    "PROHIBITED_KEYS",
    "assert_sanitized_fixture",
    "load_evaluation_fixture",
    "load_golden_labels",
    "validate_fixture_privacy",
]
