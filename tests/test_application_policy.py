"""AA-06: Cross-language policy decision engine tests.

Verifies that ``decide_field_action()`` produces the expected action and
reasons for every fixture in ``tests/fixtures/policy_fixtures.json``.
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.domain.application_package import ApplicationPackagePolicy
from backend.domain.application_policy import (
    ProfileValue,
    decide_field_action,
)

_FIXTURE_PATH = Path(__file__).resolve().parents[0] / "fixtures" / "policy_fixtures.json"


def _load_fixtures() -> list[dict[str, Any]]:
    if not _FIXTURE_PATH.is_file():
        raise FileNotFoundError(f"Policy fixtures not found at {_FIXTURE_PATH}")
    with open(_FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class TestPolicyFixtures(unittest.TestCase):
    """Policy decision engine fixtures."""


# Dynamically attach one test per fixture using default arguments to capture
# fixture state at iteration time (avoiding closure mutation).
_fixtures = _load_fixtures()
for _idx, _fixture in enumerate(_fixtures):
    _fixture_id = _fixture["id"]
    _description = _fixture.get("description", _fixture_id)

    def _make_test(
        fixture: dict[str, Any],
        fixture_id: str,
        description: str,
    ):
        def test(self: TestPolicyFixtures) -> None:
            raw_value = fixture["value"]
            raw_policy = fixture["policy"]
            expected = fixture["expected"]
            now_str = fixture.get("now", "2026-07-01T12:00:00+00:00")
            now = _parse_iso(now_str)

            # Check for validation errors (invalid combinations like AI+demographic)
            if expected.get("action") == "error" and expected.get("error_type") == "validation":
                with self.assertRaises(ValueError) as ctx:
                    ProfileValue.from_payload(raw_value)
                error_msg = str(ctx.exception)
                expected_contain = expected.get("error_message_contain", "")
                if expected_contain:
                    self.assertIn(expected_contain, error_msg)
                return

            # Build ProfileValue — this should succeed
            try:
                value = ProfileValue.from_payload(raw_value)
            except ValueError as exc:
                self.fail(
                    f"Fixture '{fixture_id}': ProfileValue creation failed: {exc}"
                )

            policy = ApplicationPackagePolicy(
                schema_version=1,
                permit_sensitive_autofill=bool(raw_policy.get("permit_sensitive_autofill")),
                permit_demographic_autofill=bool(raw_policy.get("permit_demographic_autofill")),
                require_legal_answer_confirmation=bool(
                    raw_policy.get("require_legal_answer_confirmation", True)
                ),
                jurisdiction=str(raw_policy.get("jurisdiction") or ""),
            )

            decision = decide_field_action(value, policy, now=now)

            expected_action = expected["action"]
            self.assertEqual(
                decision.action,
                expected_action,
                f"Fixture '{fixture_id}' ({description}): "
                f"expected action '{expected_action}', got '{decision.action}'. "
                f"Reasons: {decision.reasons}",
            )

            # Check that expected reasons are present
            for reason_fragment in expected.get("reasons_contain", []):
                found = any(reason_fragment in reason for reason in decision.reasons)
                self.assertTrue(
                    found,
                    f"Fixture '{fixture_id}' ({description}): "
                    f"expected reasons to contain '{reason_fragment}', "
                    f"but got: {decision.reasons}",
                )

        return test

    _test_method = _make_test(_fixture, _fixture_id, _description)
    _test_method.__name__ = f"test_policy_fixture_{_fixture_id}"
    _test_method.__doc__ = (
        f"Policy fixture {_idx + 1}/{len(_fixtures)}: {_description}"
    )
    setattr(TestPolicyFixtures, _test_method.__name__, _test_method)


if __name__ == "__main__":
    unittest.main()