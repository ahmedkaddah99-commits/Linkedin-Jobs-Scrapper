"""Regression tests for bounded collection in document/dashboard endpoints."""
import sys, unittest
from unittest.mock import MagicMock, patch

# Mock heavy import chain to avoid full backend bootstrap
for mod in [
    "backend.capabilities", "backend.capabilities.reusable_packages",
    "backend.capabilities.tailored_documents", "backend.capabilities.networking",
    "backend.capabilities.tracker", "backend.connectors", "backend.profiles",
    "backend.orchestration", "backend.integrations.clerk",
    "backend.integrations.creem", "backend.integrations.scrapeops",
    "backend.worker", "backend.career_memory", "backend.tools",
    "backend.config.plans", "backend.config.job_seeker",
    "backend.domain.phase0_contracts", "backend.domain.ats_export_gate",
    "backend.domain.run_eta", "backend.security.redaction",
    "backend.storage.factory", "backend.storage.readiness",
    "backend.storage.materialization", "backend.storage.local",
    "backend.storage.s3", "backend.storage.keys", "backend.security.auth",
    "backend.application.services", "backend.application.domain_services",
    "backend.application.run_services", "backend.application.tracker_services",
    "backend.application.quota", "backend.application.assisted_apply_service",
    "backend.application.contracts", "backend.database", "backend.adapters",
    "backend.bootstrap", "backend.config.env_schema",
]:
    sys.modules[mod] = MagicMock()

from backend.api.server import (  # noqa: E402
    _MAX_AUTHORIZED_RUNS, _MAX_DOCUMENT_ARTIFACT_EXPANSION,
    _MAX_CANDIDATE_ASSETS_IN_DOCUMENTS, _MAX_HISTORY_ROWS_DASHBOARD,
    _collect_authorized_runs, _expand_artifact_entries,
)



def _mock_user(uid="user-1"):
    u = MagicMock(); u.user_id = uid; u.role = "user"
    u.allowed_workspace_ids = []; u.display_name = "Test"; u.email = "t@e.com"
    u.metadata = {}; return u

def _mock_ws(ws_id="ws-1"):
    w = MagicMock(); w.id = ws_id; w.name = f"WS {ws_id}"
    w.owner_user_id = "user-1"; w.workspace_type = "standard"
    w.settings = {}; w.profiles = []; w.sources = []; w.metadata = {}
    w.description = ""; w.prompt_sets = []; w.feature_flags = {}
    w.workflow_template_id = "tmpl-1"; return w

def _mock_run(run_id="run-1", ws_id="ws-1", status="completed"):
    r = MagicMock(); r.id = run_id; r.workspace_id = ws_id; r.status = status
    r.created_at = "2026-01-01T00:00:00Z"; r.updated_at = "2026-01-01T00:00:00Z"
    r.queued_at = ""; r.started_at = ""; r.finished_at = ""
    r.attempt_count = 1; r.max_attempts = 1; r.current_stage_id = ""
    r.last_error = ""; r.stage_results = []; r.final_job_set_keys = []
    r.is_test_run = False; r.metadata = {}; r.run_plan = None
    r.workflow_template_id = "tmpl-1"; return r

def _mock_artifact(aid="art-1", path=""):
    a = MagicMock(); a.artifact_id = aid; a.artifact_type = "generated_cv"
    a.path = path; a.metadata = {}; return a

def _mock_app():
    a = MagicMock(); a.list_workspaces.return_value = []
    a.list_runs.return_value = []
    r = MagicMock(); r.job_store = MagicMock()
    r.job_store.load_all_job_sets.return_value = {}
    r.job_store.load_job_sets_for_runs = None
    r.review_store = MagicMock(); r.review_store.list_reviews.return_value = []
    r.review_store.list_reviews_for_runs = None
    r.artifact_store = MagicMock()
    r.artifact_store.load_artifacts.return_value = []
    r.artifact_store.load_artifacts_for_runs = None
    r.auth_repository = MagicMock(); a.repositories = r
    a.user_can_access_workspace.return_value = True
    a.user_can_access_run.return_value = True; return a


class BoundedRunsTests(unittest.TestCase):
    def test_respects_max_authorized_runs(self):
        app = _mock_app(); user = _mock_user()
        _collect_authorized_runs(app, user, run_limit=2000)
        app.list_runs.assert_called_once()
        self.assertEqual(app.list_runs.call_args[1]["limit"], _MAX_AUTHORIZED_RUNS)
    def test_accepts_lower_limit(self):
        app = _mock_app(); user = _mock_user()
        _collect_authorized_runs(app, user, run_limit=50)
        self.assertEqual(app.list_runs.call_args[1]["limit"], 50)
    def test_defaults_to_max(self):
        app = _mock_app(); user = _mock_user()
        _collect_authorized_runs(app, user)
        self.assertEqual(app.list_runs.call_args[1]["limit"], _MAX_AUTHORIZED_RUNS)


class BoundedArtifactTests(unittest.TestCase):
    @patch("backend.api.server.Path")
    def test_expansion_bounded(self, mock_path_cls):
        mp = MagicMock(); mp.exists.return_value = True
        mp.is_dir.return_value = True
        mp.suffix = ""; mp.name = "test"
        n = _MAX_DOCUMENT_ARTIFACT_EXPANSION + 100
        paths = []
        for i in range(n):
            c = MagicMock(); c.is_file.return_value = True; c.suffix = ".pdf"
            c.name = f"file_{i}.pdf"; c.as_posix.return_value = f"file_{i}.pdf"
            c.stat.return_value.st_mtime = 0; paths.append(c)
        mp.rglob.return_value = paths
        run = _mock_run(); ws = _mock_ws(); art = _mock_artifact("art-1")
        with patch("backend.api.server._build_artifact_entry", return_value={"a": "x"}):
            entries = _expand_artifact_entries(run, ws, art)
        self.assertLessEqual(len(entries), _MAX_DOCUMENT_ARTIFACT_EXPANSION)


class BoundedConstantsTests(unittest.TestCase):
    def test_constants_within_safe_range(self):
        self.assertLessEqual(_MAX_HISTORY_ROWS_DASHBOARD, 2000)
        self.assertGreater(_MAX_HISTORY_ROWS_DASHBOARD, 0)
        self.assertLessEqual(_MAX_AUTHORIZED_RUNS, 500)
        self.assertGreater(_MAX_AUTHORIZED_RUNS, 0)
        self.assertLessEqual(_MAX_DOCUMENT_ARTIFACT_EXPANSION, 2000)
        self.assertGreater(_MAX_DOCUMENT_ARTIFACT_EXPANSION, 0)
        self.assertLessEqual(_MAX_CANDIDATE_ASSETS_IN_DOCUMENTS, 500)
        self.assertGreater(_MAX_CANDIDATE_ASSETS_IN_DOCUMENTS, 0)


if __name__ == "__main__":
    unittest.main()
