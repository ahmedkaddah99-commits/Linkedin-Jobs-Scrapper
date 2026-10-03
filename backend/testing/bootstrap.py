from __future__ import annotations

import os
from pathlib import Path


def create_test_backend(base_dir: str | Path):
    """Create an isolated local backend for tests and fixture reports."""

    if str(os.environ.get("DATABASE_BACKEND") or "").strip().casefold() not in {"", "sqlite"}:
        raise RuntimeError("Test bootstrap rejected non-SQLite database configuration.")
    if str(os.environ.get("TURSO_DATABASE_URL") or "").strip():
        raise RuntimeError("Test bootstrap rejected remote/production database configuration.")
    if str(os.environ.get("RUNR_ENV") or "").strip().casefold() in {"prod", "production"}:
        raise RuntimeError("Test bootstrap rejected production runtime configuration.")
    if str(os.environ.get("RUNR_ACQUISITION_LIVE_NETWORK_ENABLED") or "").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        raise RuntimeError("Test bootstrap rejected live acquisition network authorization.")
    # Preserve explicit empty values so project dotenv loading cannot refill them.
    os.environ.update(
        {
            "RUNR_ENV": "test",
            "RUNR_TEST_MODE": "1",
            "DATABASE_BACKEND": "sqlite",
            "TURSO_DATABASE_URL": " ",
            "TURSO_AUTH_TOKEN": " ",
            "RUNR_ACQUISITION_LIVE_NETWORK_ENABLED": "false",
            "OBJECT_STORAGE_BACKEND": "local",
            "OBJECT_STORAGE_LOCAL_ROOT": " ",
        }
    )
    from backend.bootstrap import create_backend

    return create_backend(Path(base_dir), storage_backend="sqlite", test_mode=True)


__all__ = ["create_test_backend"]
