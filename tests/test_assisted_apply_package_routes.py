from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.api.routes.assisted_apply_packages import _get_package_for_extension_post
from backend.api.routes.registry import ApiRouteContext


class _Handler:
    def __init__(self, payload: dict[str, object]):
        self.payload = payload
        self.response = None

    def _read_json_body(self):
        return self.payload

    def _send_json(self, payload, status=200, *, headers=None):
        self.response = (status, payload, headers)

    def _bearer_token(self):
        return "session_package_route"

    def _request_client_origin(self):
        return "chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


class _Application:
    def __init__(self):
        self.calls = []

    def get_application_package_for_extension(self, **kwargs):
        self.calls.append(kwargs)
        return {"packageId": kwargs["package_id"], "version": 1}


class AssistedApplyPackageRouteTests(unittest.TestCase):
    def _context(self, payload):
        handler = _Handler(payload)
        application = _Application()
        context = ApiRouteContext(
            application=application,
            handler=handler,
            method="POST",
            segments=("assisted-apply", "extension", "packages"),
            query={},
        )
        return context, handler, application

    def test_body_bearing_package_lookup_preserves_extension_origin(self):
        context, handler, application = self._context({"package_id": "package_123"})
        with patch(
            "backend.api.routes.assisted_apply_packages._authenticate_extension_session",
            return_value=(SimpleNamespace(user_id="owner"), SimpleNamespace()),
        ):
            _get_package_for_extension_post(context)

        self.assertEqual(handler.response[0], 200)
        self.assertEqual(application.calls, [{
            "package_id": "package_123",
            "raw_session": "session_package_route",
            "extension_origin": "chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        }])

    def test_body_bearing_package_lookup_rejects_unknown_fields(self):
        context, _handler, _application = self._context({"package_id": "package_123", "tab_id": 7})
        with patch(
            "backend.api.routes.assisted_apply_packages._authenticate_extension_session",
            return_value=(SimpleNamespace(user_id="owner"), SimpleNamespace()),
        ), self.assertRaisesRegex(ValueError, "Unsupported application package lookup keys"):
            _get_package_for_extension_post(context)


if __name__ == "__main__":
    unittest.main()
