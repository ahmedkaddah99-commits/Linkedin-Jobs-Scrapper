from datetime import datetime, timezone
from pathlib import Path

from runr_automation.approvals import ApprovalManager
from runr_automation.pipeline import AutomationPipeline, PipelineIssue
from runr_automation.scope_router import build_scope_manifest, load_registry
from runr_automation.state import StateStore


class Projection:
    def mark_duplicate(self, *args):
        raise AssertionError("clear issue must not be marked duplicate")

    def mark_review(self, *args):
        raise AssertionError("clear issue must not require review")


def test_fake_issue_flows_through_analysis_and_implementation_to_approval_wait(tmp_path: Path) -> None:
    registry_file = tmp_path / "subsystems.yaml"
    registry_file.write_text(
        "subsystems:\n  - id: api\n    workstream: WS-1\n    owned_paths: [backend/**]\n",
        encoding="utf-8",
    )
    manifest = build_scope_manifest(
        load_registry(str(registry_file)), issue_id="linear-5", primary_subsystem="WS-01",
        allowed_paths=("backend/a.py",), required_tests=("pytest backend",),
    )
    store = StateStore(tmp_path / "state.db")
    pipeline = AutomationPipeline(store, Projection(), read_path=lambda _: "existing capability")
    issue = PipelineIssue("linear-5", "RUN-5", "Add bounded API", "API responds", "api", "fingerprint-1")

    result = pipeline.run(
        issue, manifest, candidates=(), model=lambda _: "unused",
        implement=lambda: (("backend/a.py",), "commit-1", "tests-pass-1"),
        now=datetime(2026, 9, 17, tzinfo=timezone.utc),
    )

    assert result.stages == ("deduplicate", "scope", "research", "parallelize", "implement", "validate")
    assert result.status == "awaiting_approval"
    assert result.approval_id
    assert ApprovalManager(store).authorized(result.action_context, now=datetime(2026, 9, 17, tzinfo=timezone.utc)) is False
