"""Tests for bounded loading in API collection functions.

Verifies that tracker, documents, and dashboard data collection
respects limits and does not load unbounded history into memory.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from backend.api.server import (
    _TRACKER_ENTRIES_HARD_LIMIT,
    _collect_authorized_runs,
    _collect_tracker_entries,
)


class BoundedAuthorizedRunsTests(unittest.TestCase):
    def setUp(self):
        self.application = MagicMock()
        self.user = MagicMock()
        self.user.user_id = "test-user"
        self.user.role = "user"
        workspace = MagicMock()
        workspace.id = "ws-1"
        workspace.owner_user_id = "test-user"
        self.application.list_workspaces.return_value = [workspace]

    def test_max_runs_default_is_200(self):
        self.application.list_runs.return_value = []
        _collect_authorized_runs(self.application, self.user)
        call_kwargs = self.application.list_runs.call_args[1]
        self.assertEqual(call_kwargs["limit"], 200)

    def test_max_runs_respected(self):
        self.application.list_runs.return_value = []
        _collect_authorized_runs(self.application, self.user, max_runs=50)
        call_kwargs = self.application.list_runs.call_args[1]
        self.assertEqual(call_kwargs["limit"], 50)

    def test_max_runs_clamped_to_500(self):
        self.application.list_runs.return_value = []
        _collect_authorized_runs(self.application, self.user, max_runs=1000)
        call_kwargs = self.application.list_runs.call_args[1]
        self.assertEqual(call_kwargs["limit"], 500)

    def test_max_runs_minimum_is_10(self):
        self.application.list_runs.return_value = []
        _collect_authorized_runs(self.application, self.user, max_runs=0)
        call_kwargs = self.application.list_runs.call_args[1]
        self.assertEqual(call_kwargs["limit"], 10)


class BoundedTrackerEntriesTests(unittest.TestCase):
    def setUp(self):
        self.application = MagicMock()
        self.user = MagicMock()
        self.user.user_id = "test-user"
        self.user.role = "user"
        self.workspace = MagicMock()
        self.workspace.id = "ws-1"
        self.workspace.owner_user_id = "test-user"
        self.workspace.name = "Test Workspace"
        self.application.list_workspaces.return_value = [self.workspace]
        self.runs = []
        for i in range(10):
            run = MagicMock()
            run.id = f"run-{i}"
            run.workspace_id = "ws-1"
            run.normalized_user_id = "test-user"
            run.is_test_run = False
            self.runs.append(run)
        self.application.list_runs.return_value = self.runs
        self.reviews = {}
        for run in self.runs:
            review = MagicMock()
            review.review_id = f"review-{run.id}"
            review.run_id = run.id
            review.job_id = f"job-{run.id}"
            review.decision = "approved"
            review.status = "approved"
            review.metadata = {}
            review.notes = ""
            review.updated_at = "2024-01-01T00:00:00"
            self.reviews[run.id] = [review]
        self.application.repositories.job_store.load_job_sets_for_runs.return_value = {
            run.id: {"final": [MagicMock(
                job_id=f"job-{run.id}", title=f"Job {i}", company="ACME",
                apply_link="", link="", source_url="", location_raw="",
                description_text="", extra_fields={}, priority_rank=None,
                portal="", source_type="linkedin",
            )]}
            for i, run in enumerate(self.runs)
        }
        self.application.repositories.review_store.list_reviews_for_runs.return_value = self.reviews
        self.application.repositories.artifact_store.load_artifacts_for_runs.return_value = {
            run.id: [] for run in self.runs
        }

    def test_tracker_entries_hard_limit_exists(self):
        self.assertGreater(_TRACKER_ENTRIES_HARD_LIMIT, 0)
        self.assertEqual(_TRACKER_ENTRIES_HARD_LIMIT, 2000)

    @patch("backend.api.server._collect_document_entries")
    @patch("backend.api.server._index_tracker_documents")
    def test_tracker_respects_max_entries(self, mock_index, mock_docs):
        mock_docs.return_value = []
        mock_index.return_value = ({}, [])
        _collect_tracker_entries(self.application, self.user, max_entries=5)
        call_kwargs = self.application.list_runs.call_args[1]
        self.assertEqual(call_kwargs["limit"], 50)  # floor of 50

    @patch("backend.api.server._collect_document_entries")
    @patch("backend.api.server._index_tracker_documents")
    def test_tracker_clamped_to_hard_limit(self, mock_index, mock_docs):
        mock_docs.return_value = []
        mock_index.return_value = ({}, [])
        _collect_tracker_entries(
            self.application, self.user, max_entries=_TRACKER_ENTRIES_HARD_LIMIT + 5000
        )
        call_kwargs = self.application.list_runs.call_args[1]
        self.assertLessEqual(call_kwargs["limit"], 500)
