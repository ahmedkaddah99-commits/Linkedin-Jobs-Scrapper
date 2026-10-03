import io
import json
import logging
import os
import shutil
import sqlite3
import subprocess
import sys
import unittest
from contextlib import closing, redirect_stdout
from pathlib import Path

from backend.domain.models import RunPlan, RunRecord, UserRecord, WorkspaceDefinition
from backend.repositories.sqlite_backed import (
    SqliteAuthRepository,
    SqliteRunRepository,
    SqliteWorkspaceRepository,
)
from backend.security.redaction import REDACTED, public_run_summary, redact_sensitive_data
from backend.worker.logging_config import WorkerJsonFormatter


PRIVATE_CV = "Private Candidate Name\nprivate@example.com\nConfidential employment history"
PRIVATE_PROMPT = "Write a letter using private candidate details"


class LogPrivacyTests(unittest.TestCase):
    def _db_path(self, name: str) -> Path:
        path = Path.cwd() / ".backend_test_tmp" / name / "backend.sqlite3"
        if path.parent.exists():
            shutil.rmtree(path.parent, ignore_errors=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(path.parent, ignore_errors=True))
        return path

    def test_recursive_redaction_removes_documents_prompts_secrets_and_pii(self):
        payload = {
            "nested": {
                "workspace_cv_text": PRIVATE_CV,
                "prompt": PRIVATE_PROMPT,
                "email": "private@example.com",
                "safe_count": 3,
            },
            "items": [{"source_text": PRIVATE_CV}],
        }

        redacted = redact_sensitive_data(payload)
        serialized = json.dumps(redacted)

        self.assertNotIn(PRIVATE_CV, serialized)
        self.assertNotIn(PRIVATE_PROMPT, serialized)
        self.assertNotIn("private@example.com", serialized)
        self.assertEqual(redacted["nested"]["workspace_cv_text"], REDACTED)
        self.assertEqual(redacted["nested"]["safe_count"], 3)

    def test_cli_json_output_and_run_summary_never_print_full_run_payload(self):
        run = RunRecord.create(
            workspace_id="workspace_private",
            workflow_template_id="workflow_private",
            run_input_overrides={"prompt": PRIVATE_PROMPT},
        )
        run.run_plan = RunPlan(
            workflow_template_id="workflow_private",
            workspace_snapshot={"settings": {"workspace_cv_text": PRIVATE_CV}},
            workflow_snapshot={},
            resolved_run_settings={"workspace_cv_text": PRIVATE_CV},
        )

        output = io.StringIO()
        with redirect_stdout(output):
            print(json.dumps(redact_sensitive_data(public_run_summary(run))))

        rendered = output.getvalue()
        self.assertNotIn(PRIVATE_CV, rendered)
        self.assertNotIn(PRIVATE_PROMPT, rendered)
        self.assertNotIn("run_plan", rendered)
        self.assertIn(run.id, rendered)

        cli_environment = dict(os.environ)
        cli_environment.update(
            {
                "TURSO_DATABASE_URL": " ",
                "TURSO_AUTH_TOKEN": " ",
                "DATABASE_BACKEND": "sqlite",
                "RUNR_ENV": "development",
            }
        )
        cli_result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "from workspace_runner import _print_json; "
                    f"_print_json({run.to_dict()!r})"
                ),
            ],
            cwd=Path.cwd(),
            env=cli_environment,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertNotIn(PRIVATE_CV, cli_result.stdout)
        self.assertNotIn(PRIVATE_PROMPT, cli_result.stdout)

    def test_worker_formatter_redacts_sensitive_extra_fields(self):
        record = logging.LogRecord(
            name="backend.worker.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="worker_complete",
            args=(),
            exc_info=None,
        )
        record.workspace_cv_text = PRIVATE_CV
        record.error_message = PRIVATE_PROMPT

        rendered = WorkerJsonFormatter().format(record)

        self.assertNotIn(PRIVATE_CV, rendered)
        self.assertNotIn(PRIVATE_PROMPT, rendered)

    def test_sqlite_normalizes_user_workspace_and_run_document_text(self):
        db_path = self._db_path("normalized_private_documents")
        auth = SqliteAuthRepository(db_path)
        workspaces = SqliteWorkspaceRepository(db_path)
        runs = SqliteRunRepository(db_path)
        asset_id = "asset_private_cv"
        object_key = "users/user_private/workspace_cv/asset_private_cv/cv.pdf"

        user = UserRecord(
            user_id="user_private",
            email="private@example.com",
            metadata={
                "cv_text": PRIVATE_CV,
                "candidate_assets": [
                    {
                        "schema_version": "candidate_asset_descriptor_v1",
                        "asset_id": asset_id,
                        "asset_kind": "workspace_cv",
                        "display_name": "CV.pdf",
                        "file": {
                            "object_key": object_key,
                            "mime_type": "application/pdf",
                            "extension": "pdf",
                        },
                        "metadata": {"source_text": PRIVATE_CV},
                    }
                ],
            },
        )
        auth.upsert_user(user)

        workspace = WorkspaceDefinition(
            id="workspace_private",
            name="Private workspace",
            workflow_template_id="search_apply_v1",
            settings={
                "workspace_cv_asset_id": asset_id,
                "workspace_cv_asset_object_key": object_key,
                "workspace_cv_text": PRIVATE_CV,
            },
        )
        workspaces.upsert_workspace(workspace)

        run = RunRecord.create(
            workspace_id=workspace.id,
            workflow_template_id=workspace.workflow_template_id,
        )
        run.run_plan = RunPlan(
            workflow_template_id=workspace.workflow_template_id,
            workspace_snapshot={
                **workspace.to_dict(),
                "metadata": {"candidate_assets": [{"asset_id": asset_id, "metadata": {"source_text": PRIVATE_CV}}]},
            },
            workflow_snapshot={},
            resolved_run_settings=dict(workspace.settings),
        )
        runs.save(run)

        with closing(sqlite3.connect(db_path)) as connection:
            raw_user = connection.execute(
                "SELECT payload_json FROM users WHERE user_id = ?",
                (user.user_id,),
            ).fetchone()[0]
            raw_workspace = connection.execute(
                "SELECT payload_json FROM workspaces WHERE id = ?",
                (workspace.id,),
            ).fetchone()[0]
            raw_run = connection.execute(
                "SELECT payload_json || run_plan_json FROM runs WHERE id = ?",
                (run.id,),
            ).fetchone()[0]
            asset_row = connection.execute(
                "SELECT user_id, asset_kind, object_key FROM candidate_assets WHERE asset_id = ?",
                (asset_id,),
            ).fetchone()
            document_row = connection.execute(
                "SELECT source_text, object_key FROM candidate_documents WHERE asset_id = ?",
                (asset_id,),
            ).fetchone()

        self.assertNotIn(PRIVATE_CV, raw_user)
        self.assertNotIn("candidate_assets", raw_user)
        self.assertNotIn(PRIVATE_CV, raw_workspace)
        self.assertNotIn(PRIVATE_CV, raw_run)
        self.assertNotIn("candidate_assets", raw_run)
        self.assertEqual(asset_row, (user.user_id, "workspace_cv", object_key))
        self.assertEqual(document_row, (PRIVATE_CV, object_key))

        loaded_user = auth.get_user(user.user_id)
        loaded_workspace = workspaces.get_workspace(workspace.id)
        loaded_run = runs.get(run.id)
        self.assertEqual(loaded_user.metadata["cv_text"], PRIVATE_CV)
        self.assertEqual(
            loaded_user.metadata["candidate_assets"][0]["metadata"]["source_text"],
            PRIVATE_CV,
        )
        self.assertEqual(loaded_workspace.settings["workspace_cv_text"], PRIVATE_CV)
        self.assertEqual(
            loaded_run.run_plan.resolved_run_settings["workspace_cv_text"],
            PRIVATE_CV,
        )


if __name__ == "__main__":
    unittest.main()
