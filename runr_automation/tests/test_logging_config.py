import json
import logging
from pathlib import Path

from runr_automation.logging_config import configure_logging


def test_structured_rotating_log_redacts_secrets(tmp_path: Path) -> None:
    logger = configure_logging(tmp_path, max_bytes=10_000, backup_count=2)
    logger.info("provider failed token=definitely-not-a-real-secret", extra={"issue_id": "RUN-5", "job_id": "job-1"})
    for handler in logger.handlers:
        handler.flush()

    payload = json.loads((tmp_path / "logs" / "controller.jsonl").read_text(encoding="utf-8"))
    assert payload["issue_id"] == "RUN-5"
    assert "definitely-not-a-real-secret" not in payload["message"]
    assert "[REDACTED]" in payload["message"]
