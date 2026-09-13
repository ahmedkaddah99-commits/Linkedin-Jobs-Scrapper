"""Operation-specific authorization for the acquisition domain.

The acquisition API historically used an administrator-only guard.  The
administrator compatibility rule is deliberately kept here, next to the new
permission policy, so adding granular permissions cannot silently revoke an
existing administrator's access.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from backend.domain.models import (
    ROLE_ADMIN,
    ROLE_EDITOR,
    ROLE_REVIEWER,
    ROLE_VIEWER,
    TOKEN_SCOPE_ADMIN,
)


ACQUISITION_PERMISSION_PREFIX = "acquisition."
ACQUISITION_PERMISSIONS = frozenset(
    {
        "acquisition.view",
        "acquisition.collect",
        "acquisition.enrich",
        "acquisition.review",
        "acquisition.override",
        "acquisition.duplicates",
        "acquisition.preview",
        "acquisition.publish",
        "acquisition.rollback",
        "acquisition.providers",
        "acquisition.audit",
    }
)


@dataclass(frozen=True)
class AcquisitionAdministratorMigrationPolicy:
    """Compatibility policy for administrators created before this contract."""

    version: str = "acquisition_permissions_v1"
    legacy_admin_role: str = ROLE_ADMIN
    legacy_admin_scope: str = TOKEN_SCOPE_ADMIN
    legacy_admin_grants_all: bool = True


ADMINISTRATOR_MIGRATION_POLICY = AcquisitionAdministratorMigrationPolicy()


ROLE_DEFAULT_ACQUISITION_PERMISSIONS = {
    ROLE_VIEWER: frozenset({"acquisition.view", "acquisition.preview"}),
    ROLE_REVIEWER: frozenset(
        {
            "acquisition.view",
            "acquisition.review",
            "acquisition.duplicates",
            "acquisition.preview",
        }
    ),
    ROLE_EDITOR: frozenset(
        {
            "acquisition.view",
            "acquisition.collect",
            "acquisition.enrich",
            "acquisition.review",
            "acquisition.duplicates",
            "acquisition.preview",
        }
    ),
    ROLE_ADMIN: ACQUISITION_PERMISSIONS,
}


def normalize_acquisition_permission(value: str) -> str:
    normalized = str(value or "").strip().casefold()
    if not normalized.startswith(ACQUISITION_PERMISSION_PREFIX):
        normalized = f"{ACQUISITION_PERMISSION_PREFIX}{normalized}"
    return normalized


def acquisition_permission_is_known(permission: str) -> bool:
    return normalize_acquisition_permission(permission) in ACQUISITION_PERMISSIONS


def default_acquisition_permissions_for_role(role: str) -> frozenset[str]:
    return ROLE_DEFAULT_ACQUISITION_PERMISSIONS.get(
        str(role or ROLE_VIEWER).strip().casefold(),
        frozenset(),
    )


def has_acquisition_permission(
    *,
    role: str,
    scopes: Iterable[str] = (),
    permission: str,
    policy: AcquisitionAdministratorMigrationPolicy = ADMINISTRATOR_MIGRATION_POLICY,
) -> bool:
    """Return whether a role/token may perform one acquisition operation."""

    normalized_permission = normalize_acquisition_permission(permission)
    if normalized_permission not in ACQUISITION_PERMISSIONS:
        return False
    normalized_role = str(role or ROLE_VIEWER).strip().casefold()
    normalized_scopes = {str(item or "").strip().casefold() for item in scopes}
    is_legacy_admin = policy.legacy_admin_grants_all and (
        normalized_role == str(policy.legacy_admin_role).casefold()
        or str(policy.legacy_admin_scope).casefold() in normalized_scopes
    )
    if is_legacy_admin:
        return True
    return normalized_permission in normalized_scopes or normalized_permission in {
        item.casefold() for item in default_acquisition_permissions_for_role(normalized_role)
    }


def require_acquisition_permission(
    *,
    role: str,
    scopes: Iterable[str] = (),
    permission: str,
    policy: AcquisitionAdministratorMigrationPolicy = ADMINISTRATOR_MIGRATION_POLICY,
) -> None:
    normalized_permission = normalize_acquisition_permission(permission)
    if not acquisition_permission_is_known(normalized_permission):
        raise ValueError(f"Unknown acquisition permission: {permission}")
    if not has_acquisition_permission(
        role=role,
        scopes=scopes,
        permission=normalized_permission,
        policy=policy,
    ):
        raise PermissionError(f"Missing permission: {normalized_permission}")


__all__ = [
    "ACQUISITION_PERMISSION_PREFIX",
    "ACQUISITION_PERMISSIONS",
    "ADMINISTRATOR_MIGRATION_POLICY",
    "AcquisitionAdministratorMigrationPolicy",
    "ROLE_DEFAULT_ACQUISITION_PERMISSIONS",
    "acquisition_permission_is_known",
    "default_acquisition_permissions_for_role",
    "has_acquisition_permission",
    "normalize_acquisition_permission",
    "require_acquisition_permission",
]
