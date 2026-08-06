from __future__ import annotations

import os
from urllib.parse import urlsplit

import pytest
import requests


_SAFE_TEST_ENV = {
    "RUNR_ENV": "test",
    "RUNR_TEST_MODE": "1",
    "RUNR_ACQUISITION_LIVE_NETWORK_ENABLED": "false",
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
    from backend.capabilities.cv_bullet_suggestions import _reset_suggestions

    resetters = (
        _reset_evidence_store,
        _reset_recommendations,
        _reset_reviews,
        _reset_suggestions,
    )
    for reset in resetters:
        reset()
    yield
    for reset in resetters:
        reset()


@pytest.fixture(autouse=True)
def _forbid_non_loopback_http(monkeypatch):
    """Make an accidental unmocked outbound HTTP call fail at the test boundary."""

    real_request = requests.sessions.Session.request

    def guarded_request(session, method, url, *args, **kwargs):
        hostname = (urlsplit(str(url or "")).hostname or "").casefold().rstrip(".")
        if hostname not in {"localhost", "localhost.localdomain", "127.0.0.1", "::1"}:
            raise AssertionError(f"unmocked non-loopback HTTP request blocked: {hostname or 'invalid-host'}")
        return real_request(session, method, url, *args, **kwargs)

    monkeypatch.setattr(requests.sessions.Session, "request", guarded_request)
