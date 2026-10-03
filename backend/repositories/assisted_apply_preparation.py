from __future__ import annotations

from contextlib import contextmanager

from backend.domain.assisted_apply_preparation import AssistedApplyPreparation


class AssistedApplyPreparationRepository:
    """Durable, sanitized preparation state over the existing SQLite boundary."""

    def __init__(self, repositories) -> None:
        self._auth_repo = repositories.auth_repository

    @contextmanager
    def connection(self):
        if not hasattr(self._auth_repo, "_connect"):
            raise RuntimeError("Preparation repository requires a SQLite backend.")
        with self._auth_repo._connect() as connection:
            yield connection

    def create(self, preparation: AssistedApplyPreparation) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO assisted_apply_preparations
                (preparation_id, user_id, package_id, job_id, ats, application_url,
                 state, total_count, completed_count, error_category, attempt_count,
                 session_id, created_at, updated_at, expires_at, started_at, ready_at,
                 attention_at, cancelled_at, expired_at, last_report_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(preparation.to_dict().values()),
            )

    def get(self, preparation_id: str) -> AssistedApplyPreparation | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM assisted_apply_preparations WHERE preparation_id = ?",
                (str(preparation_id or "").strip(),),
            ).fetchone()
        return AssistedApplyPreparation.from_dict(dict(row)) if row else None

    def save(self, preparation: AssistedApplyPreparation) -> None:
        values = preparation.to_dict()
        with self.connection() as conn:
            updated = conn.execute(
                """
                UPDATE assisted_apply_preparations SET
                    state=?, total_count=?, completed_count=?, error_category=?,
                    attempt_count=?, session_id=?, updated_at=?, expires_at=?, started_at=?,
                    ready_at=?, attention_at=?, cancelled_at=?, expired_at=?,
                    last_report_id=?
                WHERE preparation_id=?
                """,
                (
                    values["state"], values["total_count"], values["completed_count"],
                    values["error_category"], values["attempt_count"], values["session_id"],
                    values["updated_at"], values["expires_at"], values["started_at"], values["ready_at"],
                    values["attention_at"], values["cancelled_at"], values["expired_at"],
                    values["last_report_id"], values["preparation_id"],
                ),
            ).rowcount
        if not updated:
            raise KeyError(f"Preparation '{preparation.preparation_id}' not found.")

    def record_report(self, preparation_id: str, report_id: str, report_type: str, fingerprint: str) -> bool:
        with self.connection() as conn:
            try:
                conn.execute(
                    "INSERT INTO assisted_apply_preparation_reports "
                    "(report_id, preparation_id, report_type, fingerprint, created_at) VALUES (?, ?, ?, ?, datetime('now'))",
                    (report_id, preparation_id, report_type, fingerprint),
                )
                return True
            except Exception as exc:
                if "UNIQUE" in str(exc).upper():
                    return False
                raise

    def report_fingerprint(self, report_id: str) -> str | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT fingerprint FROM assisted_apply_preparation_reports WHERE report_id = ?",
                (str(report_id or "").strip(),),
            ).fetchone()
        return str(row["fingerprint"]) if row else None

    def list_for_user(self, user_id: str) -> list[AssistedApplyPreparation]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM assisted_apply_preparations WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        return [AssistedApplyPreparation.from_dict(dict(row)) for row in rows]
