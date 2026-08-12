"""Server-owned acquisition primitives for the Phase A catalog tracer bullet."""

from backend.acquisition.manifest import PHASE_A_TARGETS, load_phase_a_manifest
from backend.acquisition.permissions import (
    ACQUISITION_PERMISSIONS,
    ADMINISTRATOR_MIGRATION_POLICY,
    AcquisitionAdministratorMigrationPolicy,
    default_acquisition_permissions_for_role,
    has_acquisition_permission,
    normalize_acquisition_permission,
    require_acquisition_permission,
)

__all__ = [
    "PHASE_A_TARGETS",
    "load_phase_a_manifest",
    "ACQUISITION_PERMISSIONS",
    "ADMINISTRATOR_MIGRATION_POLICY",
    "AcquisitionAdministratorMigrationPolicy",
    "default_acquisition_permissions_for_role",
    "has_acquisition_permission",
    "normalize_acquisition_permission",
    "require_acquisition_permission",
]
