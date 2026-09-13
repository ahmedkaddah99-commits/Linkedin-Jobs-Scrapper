from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Iterable


RELEASE_METADATA_SCHEMA_VERSION = "runr.release.v1"
RELEASE_CONTRACT_VERSION = "runr-contract-v1"
DEFAULT_MIGRATION_HEAD = "058_customer_task_queue"
SERVICES = frozenset({"frontend", "api", "worker"})

# These frontend modules are runtime inputs to the server-side CV PDF renderer.
# A normal page/component change must stay frontend-only; a renderer change
# must rebuild both runtime images as well as the static frontend.
FRONTEND_RUNTIME_PATHS = frozenset(
    {
        "frontend/scripts/render-cv-pdf.mjs",
        "frontend/src/lib/cvStudio.js",
        "frontend/src/lib/cvSocialLinks.js",
        "frontend/package.json",
        "frontend/package-lock.json",
    }
)

_ALL_SERVICE_PATHS = frozenset({"render.yaml"})
_API_ONLY_PATHS = frozenset({"Dockerfile.api"})
_WORKER_ONLY_PATHS = frozenset({"Dockerfile.worker"})
_SHARED_RUNTIME_PATHS = frozenset(
    {
        "requirements-linux.txt",
        "workspace_runner.py",
        "deploy/start.sh",
    }
)


def _normalize_path(path: object) -> str:
    value = str(path or "").strip().replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return str(PurePosixPath(value)) if value else ""


def affected_services(changed_paths: Iterable[object]) -> set[str]:
    """Return deployment services whose runtime/build contract is affected.

    The mapping is intentionally conservative for shared Python/runtime files:
    API and worker images are rebuilt together. Documentation, tests, and
    unrelated repository files have no deployment impact by themselves.
    """

    services: set[str] = set()
    for raw_path in changed_paths:
        path = _normalize_path(raw_path)
        if not path:
            continue
        if path in _ALL_SERVICE_PATHS:
            return set(SERVICES)
        if path in _API_ONLY_PATHS:
            services.add("api")
            continue
        if path in _WORKER_ONLY_PATHS:
            services.add("worker")
            continue
        if path in FRONTEND_RUNTIME_PATHS:
            services.update({"frontend", "api", "worker"})
            continue
        if path.startswith("frontend/"):
            services.add("frontend")
            continue
        if path in _SHARED_RUNTIME_PATHS or path.startswith("backend/"):
            services.update({"api", "worker"})
            continue
        if path.startswith("scripts/"):
            services.add("worker")
    return services


def _environment_value(*names: str, default: str = "") -> str:
    for name in names:
        value = str(os.getenv(name) or "").strip()
        if value and value.casefold() not in {"unknown", "unset", "none"}:
            return value
    return default


@dataclass(frozen=True, slots=True)
class ReleaseMetadata:
    schema_version: str
    service: str
    branch: str
    commit: str
    contract_version: str
    migration_head: str
    worker_role: str
    worker_version: str
    built_at: str

    @classmethod
    def from_environment(
        cls,
        *,
        service: str,
        worker_role: str = "",
        now: datetime | None = None,
    ) -> "ReleaseMetadata":
        normalized_service = str(service or "").strip().casefold()
        if normalized_service not in SERVICES:
            raise ValueError(f"Unknown release service: {service!r}")
        timestamp = now or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return cls(
            schema_version=RELEASE_METADATA_SCHEMA_VERSION,
            service=normalized_service,
            branch=_environment_value(
                "RUNR_RELEASE_BRANCH",
                "RENDER_GIT_BRANCH",
                default="unknown",
            ),
            commit=_environment_value(
                "RUNR_RELEASE_COMMIT",
                "RENDER_GIT_COMMIT",
                default="unknown",
            ),
            contract_version=_environment_value(
                "RUNR_RELEASE_CONTRACT_VERSION",
                default=RELEASE_CONTRACT_VERSION,
            ),
            migration_head=_environment_value(
                "RUNR_MIGRATION_HEAD",
                default=DEFAULT_MIGRATION_HEAD,
            ),
            worker_role=str(worker_role or os.getenv("WORKER_ROLE") or "").strip(),
            worker_version=_environment_value("RUNR_WORKER_VERSION", default=""),
            built_at=timestamp.astimezone(timezone.utc).isoformat(),
        )

    def to_dict(self) -> dict[str, str]:
        return {key: str(value) for key, value in asdict(self).items()}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=True)


def are_release_contracts_compatible(client_contract: object, server_contract: object) -> bool:
    """Check the stable protocol shared by old and new release images."""

    client = str(client_contract or "").strip()
    server = str(server_contract or "").strip()
    return bool(client and server and client == server == RELEASE_CONTRACT_VERSION)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print redacted Runr release metadata.")
    parser.add_argument("--service", required=True, choices=sorted(SERVICES))
    parser.add_argument("--worker-role", default="")
    args = parser.parse_args(argv)
    print(ReleaseMetadata.from_environment(service=args.service, worker_role=args.worker_role).to_json())
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by the runtime entrypoint
    raise SystemExit(main())
