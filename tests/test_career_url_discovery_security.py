from __future__ import annotations

import json
import os
import shutil
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from backend import create_backend
from backend.api.server import build_handler


class CareerUrlDiscoverySecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path.cwd() / ".backend_test_tmp" / "career_url_discovery_security"
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.environment = patch.dict(
            os.environ,
            {
                "RUNR_ENV": "test",
                "DATABASE_BACKEND": "sqlite",
                "TURSO_DATABASE_URL": "",
                "TURSO_AUTH_TOKEN": "",
                "OBJECT_STORAGE_BACKEND": "local",
                "OBJECT_STORAGE_LOCAL_ROOT": "",
                "RUNR_DISABLE_QUOTAS": "1",
            },
            clear=False,
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

        self.app = create_backend(self.temp_dir)
        self.user = self.app.upsert_user(
            {
                "email": "editor@example.com",
                "display_name": "Editor",
                "role": "editor",
            }
        )
        _, self.token = self.app.issue_api_token(user_id=self.user.user_id, name="editor-token")
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            build_handler(self.app, allowed_origins={"http://127.0.0.1:4173"}),
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.thread.join, 2)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def _request(self, *, authenticated: bool, path: str, payload: dict | None = None) -> tuple[int, dict]:
        connection = HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
        headers = {"Content-Type": "application/json"}
        if authenticated:
            headers["Authorization"] = f"Bearer {self.token}"
        connection.request("POST", path, body=json.dumps(payload or {}), headers=headers)
        response = connection.getresponse()
        body = response.read().decode("utf-8")
        connection.close()
        return response.status, json.loads(body) if body else {}

    def test_authenticated_non_admin_cannot_trigger_career_discovery(self):
        with patch("backend.api.server.run_career_url_discovery") as discovery:
            status, payload = self._request(
                authenticated=True,
                path="/career-url-discovery/run",
                payload={"homepage_url": "https://example.com", "use_rendered_fallback": True},
            )

        self.assertEqual(status, 403, payload)
        discovery.assert_not_called()
        self.assertEqual(self.app.repositories.acquisition_store.list_cycles(limit=100, offset=0), [])

    def test_unauthenticated_cannot_trigger_career_discovery(self):
        with patch("backend.api.server.run_career_url_discovery") as discovery:
            status, _ = self._request(authenticated=False, path="/career-url-discovery/run")

        self.assertEqual(status, 401)
        discovery.assert_not_called()

    def test_non_admin_cannot_access_acquisition_publication_mutations(self):
        paths = (
            "/admin/acquisition/rollout/configure",
            "/admin/acquisition/rollout/advance",
            "/admin/acquisition/targets/qonto_lever/validate",
            "/admin/acquisition/staging/publication-test/promote",
            "/admin/acquisition/requests/request-test/decision",
            "/admin/acquisition/recover",
        )

        for path in paths:
            with self.subTest(path=path):
                status, _ = self._request(authenticated=True, path=path)
                self.assertEqual(status, 403)


if __name__ == "__main__":
    unittest.main()
