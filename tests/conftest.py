from __future__ import annotations

import os

import pytest


_SAFE_TEST_ENV = {
    "RUNR_ENV": "test",
    "DATABASE_BACKEND": "sqlite",
    "TURSO_DATABASE_URL": "",
    "TURSO_AUTH_TOKEN": "",
    "OBJECT_STORAGE_BACKEND": "local",
    "RUNR_DISABLE_QUOTAS": "1",
    "S3_ENDPOINT_URL": "",
    "S3_ACCESS_KEY_ID": "",
    "S3_SECRET_ACCESS_KEY": "",
    "S3_BUCKET": "",
}


for _name, _value in _SAFE_TEST_ENV.items():
    os.environ[_name] = _value


# ---------------------------------------------------------------------------
# CP-030: Reset shared in-memory stores between tests to prevent state leaks
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_career_profile_memory_stores():
    """Prevent process-global Career Profile stores leaking between tests."""
    from backend.capabilities.career_profile_evidence.service import (
        _reset_evidence_store,
    )
    from backend.capabilities.evidence_recommendation.service import (
        _reset_recommendations,
    )
    from backend.capabilities.source_text_review.service import _reset_reviews

    resetters = (
        _reset_evidence_store,
        _reset_recommendations,
        _reset_reviews,
    )
    for reset in resetters:
        reset()
    yield
    for reset in resetters:
        reset()
