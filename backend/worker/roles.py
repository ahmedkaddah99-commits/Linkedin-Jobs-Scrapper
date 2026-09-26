"""Worker role and task-family contract used at queue-claim boundaries."""

from __future__ import annotations

WORKER_ROLE_CUSTOMER = "customer"
WORKER_ROLE_ACQUISITION = "acquisition"
WORKER_ROLES = (WORKER_ROLE_CUSTOMER, WORKER_ROLE_ACQUISITION)
WORKER_VERSION_DEFAULT = "rc018-v1"

TASK_FAMILY_CUSTOMER = "customer"
TASK_FAMILY_ACQUISITION = "acquisition"


def normalize_worker_role(role: str | None) -> str:
    normalized = str(role or WORKER_ROLE_CUSTOMER).strip().casefold()
    if normalized not in WORKER_ROLES:
        allowed = ", ".join(WORKER_ROLES)
        raise ValueError(f"Unknown worker role '{role}'. Expected one of: {allowed}.")
    return normalized


def allowed_task_families(role: str) -> list[str]:
    normalized = normalize_worker_role(role)
    if normalized == WORKER_ROLE_ACQUISITION:
        return [TASK_FAMILY_ACQUISITION]
    return [TASK_FAMILY_CUSTOMER]
