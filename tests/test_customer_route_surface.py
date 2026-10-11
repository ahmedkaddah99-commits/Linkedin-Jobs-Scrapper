from backend.api.routes import build_route_registry


def test_route_registry_excludes_removed_admin_surfaces():
    registry = build_route_registry()

    route_names = {route.name for route in registry._routes}

    assert not any(
        name.startswith(("admin.dashboard", "admin.users", "admin.tokens", "admin.secrets", "admin.analytics"))
        for name in route_names
    )
    assert {"admin.billing", "admin.settings", "admin.account.delete"} <= route_names
