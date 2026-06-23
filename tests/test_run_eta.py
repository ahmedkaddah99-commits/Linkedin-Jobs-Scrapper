import unittest
from datetime import datetime, timedelta, timezone

from backend.domain.models import RunRecord, StageResult
from backend.domain.run_eta import build_run_eta


class RunEtaTests(unittest.TestCase):
    def _completed_run(self, index: int) -> RunRecord:
        base = datetime(2026, 6, 1, tzinfo=timezone.utc) + timedelta(days=index)
        run = RunRecord.create(workspace_id="w", workflow_template_id="flow")
        run.status = "completed"
        run.queued_at = base.isoformat()
        run.started_at = (base + timedelta(seconds=20 + index)).isoformat()
        run.finished_at = (base + timedelta(seconds=180 + index * 5)).isoformat()
        run.stage_results = [
            StageResult(
                stage_id="search",
                stage_type="jobs.search",
                status="completed",
                started_at=run.started_at,
                finished_at=(base + timedelta(seconds=100 + index * 3)).isoformat(),
            ),
            StageResult(
                stage_id="documents",
                stage_type="documents.generate",
                status="completed",
                started_at=(base + timedelta(seconds=100 + index * 3)).isoformat(),
                finished_at=run.finished_at,
            ),
        ]
        return run

    def test_returns_range_from_matching_completed_runs(self):
        now = datetime(2026, 6, 20, tzinfo=timezone.utc)
        run = RunRecord.create(workspace_id="w", workflow_template_id="flow")
        run.status = "running"
        run.started_at = (now - timedelta(seconds=30)).isoformat()
        run.current_stage_id = "search"
        run.metadata["progress"] = {"started_at": run.started_at}

        eta = build_run_eta(
            run,
            [
                {"stage_id": "search", "stage_type": "jobs.search"},
                {"stage_id": "documents", "stage_type": "documents.generate"},
            ],
            [self._completed_run(index) for index in range(6)],
            now=now,
        )

        self.assertEqual(eta["state"], "estimated")
        self.assertGreater(eta["remaining_seconds_high"], eta["remaining_seconds_low"])
        self.assertEqual(eta["sample_count"], 6)
        self.assertEqual(eta["confidence"], "medium")

    def test_returns_estimating_when_history_is_weak(self):
        run = RunRecord.create(workspace_id="w", workflow_template_id="flow")
        run.status = "queued"
        eta = build_run_eta(
            run,
            [{"stage_id": "search", "stage_type": "jobs.search"}],
            [self._completed_run(1)],
        )
        self.assertEqual(eta["state"], "estimating")
        self.assertLess(eta["sample_count"], 3)


if __name__ == "__main__":
    unittest.main()
