import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.config import (
    EnvironmentValidationError,
    get_environment_validation_errors,
    load_project_dotenv,
    read_environment_settings,
    validate_environment,
)


class EnvironmentConfigTests(unittest.TestCase):
    def _write_layered_env(self, root: Path) -> None:
        (root / ".env").write_text(
            "RUNR_TEST_LAYER=project\nRUNR_PROJECT_ONLY=project\n",
            encoding="utf-8",
        )
        (root / "dev.env").write_text(
            "RUNR_TEST_LAYER=development\nRUNR_DEV_ONLY=development\n",
            encoding="utf-8",
        )
        user_config = root / "user_config"
        user_config.mkdir()
        (user_config / ".env").write_text(
            "RUNR_TEST_LAYER=user\nRUNR_USER_ONLY=user\n",
            encoding="utf-8",
        )

    def test_dotenv_layers_override_earlier_files_but_preserve_injected_environment(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self._write_layered_env(root)
            previous_cwd = Path.cwd()
            try:
                os.chdir(root)
                with patch.dict(
                    os.environ,
                    {
                        "RUNR_TEST_LAYER": "injected",
                    },
                    clear=False,
                ):
                    load_project_dotenv()

                    self.assertEqual(os.environ["RUNR_TEST_LAYER"], "injected")
                    self.assertEqual(os.environ["RUNR_PROJECT_ONLY"], "project")
                    self.assertEqual(os.environ["RUNR_DEV_ONLY"], "development")
                    self.assertEqual(os.environ["RUNR_USER_ONLY"], "user")
            finally:
                os.chdir(previous_cwd)

    def test_dotenv_later_files_win_for_values_not_injected_before_loading(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self._write_layered_env(root)
            previous_cwd = Path.cwd()
            try:
                os.chdir(root)
                with patch.dict(os.environ, {}, clear=True):
                    load_project_dotenv()
                    self.assertEqual(os.environ["RUNR_TEST_LAYER"], "user")
            finally:
                os.chdir(previous_cwd)

    def test_dotenv_override_true_allows_files_to_replace_injected_values(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self._write_layered_env(root)
            previous_cwd = Path.cwd()
            try:
                os.chdir(root)
                with patch.dict(os.environ, {"RUNR_TEST_LAYER": "injected"}, clear=False):
                    load_project_dotenv(override=True)
                    self.assertEqual(os.environ["RUNR_TEST_LAYER"], "user")
            finally:
                os.chdir(previous_cwd)

    def test_local_development_defaults_are_valid(self):
        settings = validate_environment({})

        self.assertEqual(settings.runr_env, "development")
        self.assertEqual(settings.database_backend, "sqlite")
        self.assertEqual(settings.object_storage_backend, "local")
        self.assertFalse(settings.is_production)

    def test_production_requires_turso_and_remote_object_storage(self):
        errors = get_environment_validation_errors({"RUNR_ENV": "production"})

        self.assertIn("Production requires DATABASE_BACKEND=turso", errors)
        self.assertIn("Production requires OBJECT_STORAGE_BACKEND=s3 or r2", errors)
        self.assertIn("TURSO_DATABASE_URL is required for Turso and production", errors)
        self.assertIn("S3_BUCKET is required for S3-compatible and production object storage", errors)

        with self.assertRaises(EnvironmentValidationError):
            validate_environment({"RUNR_ENV": "production"})

    def test_unknown_runtime_environment_is_rejected(self):
        with self.assertRaises(EnvironmentValidationError):
            validate_environment({"RUNR_ENV": "prodution"})

    def test_complete_production_contract_is_valid(self):
        environ = {
            "RUNR_ENV": "production",
            "DATABASE_BACKEND": "turso",
            "TURSO_DATABASE_URL": "libsql://runr-prod.example.turso.io",
            "TURSO_AUTH_TOKEN": "example-production-token",
            "OBJECT_STORAGE_BACKEND": "r2",
            "S3_ENDPOINT_URL": "https://example-account.r2.cloudflarestorage.com",
            "S3_ACCESS_KEY_ID": "example-access-key",
            "S3_SECRET_ACCESS_KEY": "example-secret-key",
            "S3_BUCKET": "runr-production",
            "S3_REGION": "auto",
            "S3_SIGNED_URL_TTL_SECONDS": "600",
        }

        settings = validate_environment(environ)

        self.assertTrue(settings.is_production)
        self.assertEqual(settings.s3_signed_url_ttl_seconds, 600)
        self.assertEqual(read_environment_settings(environ), settings)


if __name__ == "__main__":
    unittest.main()
