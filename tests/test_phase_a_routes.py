import unittest
from unittest.mock import Mock

from backend.api.routes import build_route_registry
from backend.api.routes.registry import ApiRouteContext


class _Handler:
    def __init__(self):
        self.payload = None
        self.admin_calls = 0

    def _require_identity(self):
        return object(), object()

    def _require_admin(self):
        self.admin_calls += 1
        return object(), object()

    def _send_json(self, payload, status=200, *, headers=None):
        self.payload = (status, payload)

    def _read_json_body(self):
        return {}


class PhaseARouteTests(unittest.TestCase):
    def test_read_catalog_is_read_only_and_admin_reports_are_protected_routes(self):
        registry = build_route_registry()
        handler = _Handler()
        application = Mock()
        application.get_public_acquisition_catalog.return_value = {
            "jobs": [],
            "total": 0,
            "publication": None,
            "freshness": "unpublished",
        }
        catalog_context = ApiRouteContext(
            application=application,
            handler=handler,
            method="GET",
            segments=("personalized-jobs",),
            query={},
        )

        self.assertTrue(registry.dispatch(catalog_context, auth_required=True))
        application.run_due_acquisition.assert_not_called()
        self.assertEqual(handler.payload[1]["freshness"], "unpublished")

        application.list_acquisition_cycles.return_value = []
        admin_context = ApiRouteContext(
            application=application,
            handler=handler,
            method="GET",
            segments=("admin", "acquisition", "cycles"),
            query={},
        )
        self.assertTrue(registry.dispatch(admin_context, auth_required=True))
        self.assertEqual(handler.admin_calls, 1)
        self.assertEqual(handler.payload, (200, {"cycles": []}))

        self.assertFalse(registry.dispatch(catalog_context, auth_required=False))

    def test_normal_user_cannot_recover_or_mutate_acquisition_configuration(self):
        registry = build_route_registry()

        class _NormalUserHandler(_Handler):
            def _require_admin(self):
                raise PermissionError("Admin access required.")

        handler = _NormalUserHandler()
        application = Mock()
        recovery_context = ApiRouteContext(
            application=application,
            handler=handler,
            method="POST",
            segments=("admin", "acquisition", "recover"),
            query={},
        )
        with self.assertRaises(PermissionError):
            registry.dispatch(recovery_context, auth_required=True)
        application.recover_acquisition_cycle.assert_not_called()

        for method, segments in (
            ("POST", ("acquisition",)),
            ("POST", ("personalized-jobs", "refresh")),
            ("POST", ("personalized-jobs", "save-search")),
            ("PUT", ("admin", "acquisition", "targets", "n26_greenhouse", "enable")),
            ("PUT", ("admin", "acquisition", "manifest")),
            ("POST", ("admin", "acquisition", "requests", "request-1", "decision")),
        ):
            context = ApiRouteContext(
                application=application,
                handler=handler,
                method=method,
                segments=segments,
                query={},
            )
            if segments[0] == "admin":
                try:
                    handled = registry.dispatch(context, auth_required=True)
                except PermissionError:
                    pass
                else:
                    self.assertFalse(handled)
            else:
                self.assertFalse(registry.dispatch(context, auth_required=True))

        self.assertEqual(application.method_calls, [])


if __name__ == "__main__":
    unittest.main()
