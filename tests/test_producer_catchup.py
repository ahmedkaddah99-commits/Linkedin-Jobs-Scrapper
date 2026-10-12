from datetime import datetime, timedelta, timezone
import sqlite3
import json
import shutil

import pytest

from scripts.run_producer_catchup import delivery_complete
from scripts.publish_producer_states import run_delivery, BackfillControls
from tests.test_producer_state_delivery import _manifest, _seed_producer_states


def test_completion_requires_both_sources_and_capture_boundary():
    rows = [{"source": source, "bootstrap_complete": 1, "source_watermark": "2026-10-12T00:00:00Z"}
            for source in ("linkedin", "employer_site")]
    assert delivery_complete(rows, "2026-10-12T00:00:00Z")
    assert not delivery_complete(rows[:1], "2026-10-12T00:00:00Z")
    assert not delivery_complete(rows, "2026-10-13T00:00:00Z")
    rows[0]["bootstrap_complete"] = 0
    assert not delivery_complete(rows, "2026-10-12T00:00:00Z")


def test_frozen_delivery_never_advances_past_capture_and_finishes_empty_window(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNR_ENV", "test")
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    manifest = _manifest(tmp_path)
    linkedin, employer = _seed_producer_states(tmp_path)
    boundary = (datetime.now(timezone.utc) - timedelta(seconds=5)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    kwargs = dict(manifest_path=manifest, linkedin_state=linkedin, employer_state=employer,
                  data_dir=tmp_path / "catalog", source_version="snapshot-test",
                  snapshot_captured_at=boundary, controls=BackfillControls(batch_size=1))
    for _ in range(10):
        run_delivery(**kwargs)
        with sqlite3.connect(tmp_path / "catalog/backend.sqlite3") as con:
            rows = con.execute("SELECT bootstrap_complete,source_watermark FROM acquisition_publisher_checkpoints").fetchall()
        assert all(not watermark or watermark <= boundary for _, watermark in rows)
        if len(rows) == 2 and all(complete and watermark == boundary for complete, watermark in rows):
            break
    else:
        pytest.fail("Frozen exact-size bootstrap did not finish")
    with sqlite3.connect(tmp_path / "catalog/backend.sqlite3") as con:
        con.execute("UPDATE acquisition_publisher_checkpoints SET source_watermark='2099-01-01T00:00:00Z'")
    with pytest.raises(ValueError, match="newer than"):
        run_delivery(**kwargs)


def test_outcome_audit_is_durable_and_does_not_claim_app_readiness(tmp_path, monkeypatch):
    from scripts.audit_producer_catchup import audit
    monkeypatch.setenv("RUNR_ENV", "test")
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    manifest = _manifest(tmp_path)
    linkedin, employer = _seed_producer_states(tmp_path)
    catalog = tmp_path / "catalog"
    run_delivery(manifest_path=manifest, linkedin_state=linkedin, employer_state=employer,
                 data_dir=catalog, source_version="audit-test")
    operation = tmp_path / "operation"
    operation.mkdir()
    shutil.copy2(linkedin, operation / "linkedin.db")
    shutil.copy2(employer, operation / "employer.db")
    (operation / "snapshot.json").write_text(json.dumps({"manifest": str(manifest), "crosswalk": None}))
    first = audit(operation, catalog / "backend.sqlite3")
    second = audit(operation, catalog / "backend.sqlite3")
    assert first["source_rows"] > 0
    assert first["outcomes"] == second["outcomes"]
    assert first["ready"] is False
    with sqlite3.connect(operation / "outcomes.sqlite3") as con:
        assert con.execute("SELECT count(*) FROM targets").fetchone()[0] == first["source_rows"]
