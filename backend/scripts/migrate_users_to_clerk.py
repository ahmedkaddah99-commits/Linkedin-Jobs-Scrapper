from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.bootstrap import create_backend
from backend.config.plans import DEFAULT_PLAN_ID
from backend.domain.models import ROLE_ADMIN
from backend.integrations.clerk import create_user, find_user_by_email, find_user_by_external_id


def _normalized_public_role(user_role: str) -> str:
    return "admin" if str(user_role or "").strip().lower() == ROLE_ADMIN else "user"


def migrate_users_to_clerk(*, data_dir: str, storage_backend: str) -> dict[str, int]:
    application = create_backend(data_dir, storage_backend=storage_backend)
    repository = application.repositories.auth_repository
    list_candidates = getattr(repository, "list_user_rows_for_clerk_migration", None)
    if not callable(list_candidates):
        raise RuntimeError("The configured auth repository does not support Clerk migration helpers.")

    migrated = 0
    skipped = 0
    reused_existing = 0

    for row in list_candidates():
        user_id = str(row.get("user_id") or "").strip()
        clerk_user_id = str(row.get("clerk_user_id") or "").strip()
        if not user_id:
            continue
        if clerk_user_id:
            skipped += 1
            print(f"[skip] {user_id} already mapped to Clerk user {clerk_user_id}")
            continue

        user = application.get_user(user_id)
        public_metadata = {
            "plan_id": DEFAULT_PLAN_ID,
            "role": _normalized_public_role(user.role),
        }
        private_metadata = {
            "legacy_user_id": user.user_id,
        }

        existing_clerk_user: dict[str, Any] | None = find_user_by_external_id(user.user_id)
        if existing_clerk_user is None and user.email:
            existing_clerk_user = find_user_by_email(user.email)

        if existing_clerk_user is None:
            created_user = create_user(
                email=user.email,
                display_name=user.display_name,
                external_id=user.user_id,
                public_metadata=public_metadata,
                private_metadata=private_metadata,
                created_at=user.created_at,
            )
            existing_clerk_user = created_user
            migrated += 1
            print(f"[migrated] {user.user_id} -> {existing_clerk_user.get('id')}")
        else:
            reused_existing += 1
            print(f"[reused] {user.user_id} -> {existing_clerk_user.get('id')}")

        resolved_clerk_user_id = str(existing_clerk_user.get("id") or "").strip()
        if not resolved_clerk_user_id:
            raise RuntimeError(f"Clerk did not return a user id for local user '{user.user_id}'.")
        repository.set_user_clerk_user_id(user.user_id, resolved_clerk_user_id)

    return {
        "migrated": migrated,
        "reused_existing": reused_existing,
        "skipped": skipped,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Create Clerk users for existing Runr users and store the mapping.")
    parser.add_argument("--data-dir", default=".backend_data", help="Backend data directory. Defaults to .backend_data")
    parser.add_argument("--storage-backend", default="sqlite", help="Storage backend. Defaults to sqlite")
    args = parser.parse_args()

    result = migrate_users_to_clerk(data_dir=str(args.data_dir), storage_backend=str(args.storage_backend))
    print(
        "Completed Clerk migration: "
        f"{result['migrated']} created, "
        f"{result['reused_existing']} reused, "
        f"{result['skipped']} skipped."
    )


if __name__ == "__main__":
    main()
