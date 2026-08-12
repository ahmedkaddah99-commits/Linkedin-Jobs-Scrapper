from __future__ import annotations

from typing import TYPE_CHECKING, Any
import json

from backend.database.migrations import Migration
from backend.domain.models import utc_now_iso
from backend.repositories.document_payloads import (
    prepare_run_payload,
    prepare_user_payload,
    prepare_workspace_payload,
)
if TYPE_CHECKING:
    from backend.database.connection import DatabaseConnection

_APPLICATION_STATUS_HISTORY_SOURCES = {"manual", "gmail_sync", "auto_default"}


def _table_columns(connection: DatabaseConnection, table_name: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row["name"]) for row in rows}


def _ensure_run_column(connection: DatabaseConnection, column_name: str, column_sql: str) -> None:
    if column_name not in _table_columns(connection, "runs"):
        connection.execute(f"ALTER TABLE runs ADD COLUMN {column_name} {column_sql}")


def _ensure_user_column(connection: DatabaseConnection, column_name: str, column_sql: str) -> None:
    if column_name not in _table_columns(connection, "users"):
        connection.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_sql}")


def _ensure_table_column(
    connection: DatabaseConnection,
    table_name: str,
    column_name: str,
    column_sql: str,
) -> None:
    if column_name not in _table_columns(connection, table_name):
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")


def _apply_runtime_migration(connection: DatabaseConnection) -> None:
    _ensure_run_column(connection, "requested_by", "TEXT NOT NULL DEFAULT ''")
    _ensure_run_column(connection, "queued_at", "TEXT NOT NULL DEFAULT ''")
    _ensure_run_column(connection, "started_at", "TEXT NOT NULL DEFAULT ''")
    _ensure_run_column(connection, "finished_at", "TEXT NOT NULL DEFAULT ''")
    _ensure_run_column(connection, "current_stage_id", "TEXT NOT NULL DEFAULT ''")
    _ensure_run_column(connection, "last_error", "TEXT NOT NULL DEFAULT ''")
    _ensure_run_column(connection, "attempt_count", "INTEGER NOT NULL DEFAULT 0")
    _ensure_run_column(connection, "max_attempts", "INTEGER NOT NULL DEFAULT 1")
    _ensure_run_column(connection, "run_input_overrides_json", "TEXT NOT NULL DEFAULT '{}'")
    _ensure_run_column(connection, "run_plan_json", "TEXT NOT NULL DEFAULT '{}'")
    _ensure_run_column(connection, "metadata_json", "TEXT NOT NULL DEFAULT '{}'")

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS run_stage_results (
            run_id TEXT NOT NULL,
            sequence_no INTEGER NOT NULL,
            stage_id TEXT NOT NULL,
            stage_type TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT NOT NULL,
            error TEXT NOT NULL DEFAULT '',
            metrics_json TEXT NOT NULL DEFAULT '{}',
            output_keys_json TEXT NOT NULL DEFAULT '[]',
            artifact_ids_json TEXT NOT NULL DEFAULT '[]',
            PRIMARY KEY (run_id, sequence_no)
        );
        CREATE TABLE IF NOT EXISTS run_jobs (
            run_id TEXT NOT NULL,
            set_key TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            job_id TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            company TEXT NOT NULL DEFAULT '',
            source_type TEXT NOT NULL DEFAULT '',
            filter_status TEXT NOT NULL DEFAULT '',
            location_raw TEXT NOT NULL DEFAULT '',
            link TEXT NOT NULL DEFAULT '',
            source_url TEXT NOT NULL DEFAULT '',
            apply_link TEXT NOT NULL DEFAULT '',
            portal TEXT NOT NULL DEFAULT '',
            description_text TEXT NOT NULL DEFAULT '',
            manual_approved INTEGER NOT NULL DEFAULT 0,
            role_category_id TEXT NOT NULL DEFAULT '',
            role_category_name TEXT NOT NULL DEFAULT '',
            priority_rank INTEGER,
            payload_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (run_id, set_key, ordinal)
        );
        CREATE TABLE IF NOT EXISTS workers (
            worker_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            host_name TEXT NOT NULL DEFAULT '',
            process_id INTEGER NOT NULL DEFAULT 0,
            current_run_id TEXT NOT NULL DEFAULT '',
            started_at TEXT NOT NULL,
            last_heartbeat_at TEXT NOT NULL,
            lease_expires_at TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            payload_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_run_stage_results_run_sequence ON run_stage_results(run_id, sequence_no);
        CREATE INDEX IF NOT EXISTS idx_run_jobs_run_key_ordinal ON run_jobs(run_id, set_key, ordinal);
        CREATE INDEX IF NOT EXISTS idx_run_jobs_run_job_id ON run_jobs(run_id, job_id);
        CREATE INDEX IF NOT EXISTS idx_workers_status_lease ON workers(status, lease_expires_at);
        """
    )


def _apply_run_user_id_migration(connection: DatabaseConnection) -> None:
    _ensure_run_column(connection, "user_id", "TEXT NOT NULL DEFAULT ''")
    normalized_user_id_sql = (
        "CASE "
        "WHEN COALESCE(requested_by, '') LIKE 'api:%' THEN TRIM(SUBSTR(COALESCE(requested_by, ''), 5)) "
        "ELSE '' "
        "END"
    )
    connection.execute(
        (
            "UPDATE runs "
            f"SET user_id = {normalized_user_id_sql} "
            f"WHERE COALESCE(user_id, '') != {normalized_user_id_sql}"
        )
    )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_runs_user_id_created_at ON runs(user_id, created_at DESC)")


def _apply_billing_migration(connection: DatabaseConnection) -> None:
    _ensure_user_column(connection, "clerk_user_id", "TEXT NOT NULL DEFAULT ''")
    connection.executescript(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_clerk_user_id_unique
            ON users(clerk_user_id)
            WHERE clerk_user_id != '';
        CREATE TABLE IF NOT EXISTS subscriptions (
            subscription_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            plan_id TEXT NOT NULL DEFAULT 'free',
            status TEXT NOT NULL DEFAULT 'active',
            lemonsqueezy_subscription_id TEXT,
            lemonsqueezy_customer_id TEXT,
            lemonsqueezy_order_id TEXT,
            current_period_start TEXT,
            current_period_end TEXT,
            cancelled_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS subscription_events (
            event_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            plan_id TEXT,
            previous_plan_id TEXT,
            lemonsqueezy_event_name TEXT,
            occurred_at TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS quota_usage (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            quota_type TEXT NOT NULL,
            period TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, quota_type, period)
        );
        CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id);
        CREATE INDEX IF NOT EXISTS idx_subscription_events_user_id
            ON subscription_events(user_id, occurred_at);
        CREATE INDEX IF NOT EXISTS idx_quota_usage_user_period
            ON quota_usage(user_id, period, quota_type);
        """
    )


def _apply_creem_billing_migration(connection: DatabaseConnection) -> None:
    _ensure_table_column(connection, "subscriptions", "billing_provider", "TEXT NOT NULL DEFAULT 'creem'")
    _ensure_table_column(connection, "subscriptions", "creem_subscription_id", "TEXT NOT NULL DEFAULT ''")
    _ensure_table_column(connection, "subscriptions", "creem_customer_id", "TEXT NOT NULL DEFAULT ''")
    _ensure_table_column(connection, "subscriptions", "creem_order_id", "TEXT NOT NULL DEFAULT ''")
    _ensure_table_column(connection, "subscription_events", "billing_provider", "TEXT NOT NULL DEFAULT 'creem'")
    _ensure_table_column(connection, "subscription_events", "provider_event_name", "TEXT NOT NULL DEFAULT ''")
    connection.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_subscriptions_creem_subscription_id
            ON subscriptions(creem_subscription_id)
            WHERE creem_subscription_id != '';
        """
    )


def _apply_analytics_events_migration(connection: DatabaseConnection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS analytics_events (
            event_id TEXT PRIMARY KEY,
            event_name TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            user_id TEXT,
            workspace_id TEXT,
            run_id TEXT,
            job_id TEXT,
            review_id TEXT,
            session_id TEXT,
            route TEXT,
            source TEXT,
            payload_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_analytics_events_name_occurred_at
            ON analytics_events(event_name, occurred_at);
        CREATE INDEX IF NOT EXISTS idx_analytics_events_user_occurred_at
            ON analytics_events(user_id, occurred_at);
        CREATE INDEX IF NOT EXISTS idx_analytics_events_run_occurred_at
            ON analytics_events(run_id, occurred_at);
        """
    )


def _apply_app_config_migration(connection: DatabaseConnection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS app_config (
            config_key TEXT PRIMARY KEY,
            updated_at TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_app_config_updated_at
            ON app_config(updated_at);
        """
    )


def _apply_scrapeops_usage_ledger_migration(connection: DatabaseConnection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS scrapeops_usage_ledger (
            ledger_id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL DEFAULT '',
            target_url TEXT NOT NULL DEFAULT '',
            method TEXT NOT NULL DEFAULT 'scrapeops_proxy',
            request_mode TEXT NOT NULL DEFAULT 'basic',
            target_status_code INTEGER NOT NULL DEFAULT 0,
            provider_status_code INTEGER NOT NULL DEFAULT 0,
            latency_ms INTEGER NOT NULL DEFAULT 0,
            billed_credits_actual INTEGER,
            billed_credits_estimated INTEGER NOT NULL DEFAULT 0,
            usable_job_count INTEGER NOT NULL DEFAULT 0,
            error_category TEXT NOT NULL DEFAULT '',
            recorded_at TEXT NOT NULL,
            user_id TEXT NOT NULL DEFAULT '',
            workspace_id TEXT NOT NULL DEFAULT '',
            run_id TEXT NOT NULL DEFAULT '',
            route TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_scrapeops_usage_source_recorded_at
            ON scrapeops_usage_ledger(source_id, recorded_at);
        CREATE INDEX IF NOT EXISTS idx_scrapeops_usage_run_recorded_at
            ON scrapeops_usage_ledger(run_id, recorded_at);
        """
    )


def _apply_site_source_policy_migration(connection: DatabaseConnection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS site_source_policy (
            site_url TEXT PRIMARY KEY,
            site_type TEXT NOT NULL DEFAULT 'company',
            site_state TEXT NOT NULL DEFAULT 'pending'
                CHECK (site_state IN ('hot', 'selected', 'low_yield', 'paused', 'pending')),
            consecutive_zero_yield_runs INTEGER NOT NULL DEFAULT 0,
            last_jobs_found INTEGER NOT NULL DEFAULT 0,
            last_crawled_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_site_source_policy_type_state
            ON site_source_policy(site_type, site_state);
        """
    )


def _apply_site_job_url_history_migration(connection: DatabaseConnection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS site_job_url_history (
            job_url TEXT PRIMARY KEY,
            site_url TEXT NOT NULL DEFAULT '',
            source_group_url TEXT NOT NULL DEFAULT '',
            workspace_id TEXT NOT NULL DEFAULT '',
            run_id TEXT NOT NULL DEFAULT '',
            job_id TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            company TEXT NOT NULL DEFAULT '',
            location_raw TEXT NOT NULL DEFAULT '',
            last_status TEXT NOT NULL DEFAULT '',
            active_status TEXT NOT NULL DEFAULT 'unknown',
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            last_verified_at TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_site_job_url_history_site_seen
            ON site_job_url_history(site_url, last_seen_at);
        CREATE INDEX IF NOT EXISTS idx_site_job_url_history_run_seen
            ON site_job_url_history(run_id, last_seen_at);
        CREATE INDEX IF NOT EXISTS idx_site_job_url_history_active_seen
            ON site_job_url_history(active_status, last_seen_at);
        """
    )


def _apply_site_job_url_history_workspace_scope_migration(connection: DatabaseConnection) -> None:
    connection.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_site_job_url_history_site_seen
            ON site_job_url_history(site_url, last_seen_at);
        CREATE INDEX IF NOT EXISTS idx_site_job_url_history_run_seen
            ON site_job_url_history(run_id, last_seen_at);
        """
    )


def _apply_site_job_url_history_public_index_migration(connection: DatabaseConnection) -> None:
    columns = connection.execute("PRAGMA table_info(site_job_url_history)").fetchall()
    if not columns:
        _apply_site_job_url_history_migration(connection)
        return
    column_names = {str(row[1]) for row in columns}
    pk_columns = [
        str(row[1])
        for row in sorted((row for row in columns if int(row[5] or 0)), key=lambda row: int(row[5] or 0))
    ]
    if (
        pk_columns == ["job_url"]
        and {"payload_json", "active_status", "last_verified_at", "location_raw", "source_group_url"}.issubset(column_names)
    ):
        connection.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_site_job_url_history_site_seen
                ON site_job_url_history(site_url, last_seen_at);
            CREATE INDEX IF NOT EXISTS idx_site_job_url_history_run_seen
                ON site_job_url_history(run_id, last_seen_at);
            CREATE INDEX IF NOT EXISTS idx_site_job_url_history_active_seen
                ON site_job_url_history(active_status, last_seen_at);
            """
        )
        return

    connection.executescript(
        """
        ALTER TABLE site_job_url_history RENAME TO site_job_url_history_legacy_public_index;
        CREATE TABLE site_job_url_history (
            job_url TEXT PRIMARY KEY,
            site_url TEXT NOT NULL DEFAULT '',
            source_group_url TEXT NOT NULL DEFAULT '',
            workspace_id TEXT NOT NULL DEFAULT '',
            run_id TEXT NOT NULL DEFAULT '',
            job_id TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            company TEXT NOT NULL DEFAULT '',
            location_raw TEXT NOT NULL DEFAULT '',
            last_status TEXT NOT NULL DEFAULT '',
            active_status TEXT NOT NULL DEFAULT 'unknown',
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            last_verified_at TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}'
        );
        INSERT OR REPLACE INTO site_job_url_history (
            job_url,
            site_url,
            source_group_url,
            workspace_id,
            run_id,
            job_id,
            title,
            company,
            location_raw,
            last_status,
            active_status,
            first_seen_at,
            last_seen_at,
            last_verified_at,
            payload_json
        )
        SELECT
            job_url,
            site_url,
            '',
            workspace_id,
            run_id,
            job_id,
            title,
            company,
            '',
            last_status,
            CASE
                WHEN last_status IN ('accepted', 'cache_reused', 'keyword_filtered', 'old_posting') THEN 'active'
                WHEN last_status = 'inactive' THEN 'inactive'
                ELSE 'unknown'
            END,
            first_seen_at,
            last_seen_at,
            CASE
                WHEN last_status IN ('accepted', 'cache_reused') THEN last_seen_at
                ELSE ''
            END,
            '{}'
        FROM site_job_url_history_legacy_public_index
        ORDER BY last_seen_at ASC;
        DROP TABLE site_job_url_history_legacy_public_index;
        CREATE INDEX IF NOT EXISTS idx_site_job_url_history_site_seen
            ON site_job_url_history(site_url, last_seen_at);
        CREATE INDEX IF NOT EXISTS idx_site_job_url_history_run_seen
            ON site_job_url_history(run_id, last_seen_at);
        CREATE INDEX IF NOT EXISTS idx_site_job_url_history_active_seen
            ON site_job_url_history(active_status, last_seen_at);
        """
    )


def _apply_application_status_history_migration(connection: DatabaseConnection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS application_status_history (
            review_id TEXT,
            user_id TEXT,
            from_status TEXT,
            to_status TEXT,
            changed_at TEXT,
            source TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_application_status_history_review_changed_at
            ON application_status_history(review_id, changed_at);
        CREATE INDEX IF NOT EXISTS idx_application_status_history_user_changed_at
            ON application_status_history(user_id, changed_at);
        """
    )


def _normalize_application_status_history_entry(
    *,
    review_id: Any,
    user_id: Any,
    from_status: Any,
    to_status: Any,
    changed_at: Any = "",
    source: Any = "manual",
) -> dict[str, str]:
    normalized_review_id = str(review_id or "").strip()
    if not normalized_review_id:
        raise ValueError("review_id is required for application status history.")
    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        raise ValueError("user_id is required for application status history.")
    normalized_source = str(source or "manual").strip() or "manual"
    if normalized_source not in _APPLICATION_STATUS_HISTORY_SOURCES:
        raise ValueError(
            f"source must be one of: {sorted(_APPLICATION_STATUS_HISTORY_SOURCES)}"
        )
    return {
        "review_id": normalized_review_id,
        "user_id": normalized_user_id,
        "from_status": str(from_status or "").strip(),
        "to_status": str(to_status or "").strip(),
        "changed_at": str(changed_at or utc_now_iso()).strip(),
        "source": normalized_source,
    }


def _insert_application_status_history_row(
    connection: DatabaseConnection,
    entry: dict[str, str],
) -> None:
    connection.execute(
        (
            "INSERT INTO application_status_history "
            "(review_id, user_id, from_status, to_status, changed_at, source) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        ),
        (
            entry["review_id"],
            entry["user_id"],
            entry["from_status"],
            entry["to_status"],
            entry["changed_at"],
            entry["source"],
        ),
    )


def _upsert_candidate_document(connection: DatabaseConnection, payload: dict[str, Any]) -> None:
    source_text = str(payload.get("source_text") or "")
    asset_id = str(payload.get("asset_id") or "")
    if asset_id:
        existing = connection.execute(
            "SELECT source_text FROM candidate_documents WHERE document_id = ?",
            (str(payload.get("document_id") or ""),),
        ).fetchone()
        if existing is not None and str(existing["source_text"] or ""):
            return
    connection.execute(
        """
        INSERT INTO candidate_documents (
            document_id, user_id, asset_id, workspace_id, document_kind,
            object_key, char_count, source_text, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(document_id) DO UPDATE SET
            user_id=CASE WHEN excluded.user_id != '' THEN excluded.user_id ELSE candidate_documents.user_id END,
            asset_id=CASE WHEN excluded.asset_id != '' THEN excluded.asset_id ELSE candidate_documents.asset_id END,
            workspace_id=CASE WHEN excluded.workspace_id != '' THEN excluded.workspace_id ELSE candidate_documents.workspace_id END,
            document_kind=CASE WHEN excluded.document_kind != '' THEN excluded.document_kind ELSE candidate_documents.document_kind END,
            object_key=CASE WHEN excluded.object_key != '' THEN excluded.object_key ELSE candidate_documents.object_key END,
            char_count=CASE WHEN excluded.source_text != '' THEN excluded.char_count ELSE candidate_documents.char_count END,
            source_text=CASE WHEN excluded.source_text != '' THEN excluded.source_text ELSE candidate_documents.source_text END,
            updated_at=excluded.updated_at
        """,
        (
            str(payload.get("document_id") or ""),
            str(payload.get("user_id") or ""),
            asset_id,
            str(payload.get("workspace_id") or ""),
            str(payload.get("document_kind") or "workspace_cv"),
            str(payload.get("object_key") or ""),
            len(source_text),
            source_text,
            utc_now_iso(),
        ),
    )


def _upsert_candidate_asset(
    connection: DatabaseConnection,
    *,
    user_id: str,
    asset: dict[str, Any],
) -> None:
    file_payload = dict(asset.get("file") or {})
    metadata = dict(asset.get("metadata") or {})
    connection.execute(
        """
        INSERT INTO candidate_assets (
            asset_id, user_id, asset_kind, display_name, workspace_id, object_key,
            mime_type, extension, created_at, updated_at, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(asset_id) DO UPDATE SET
            user_id=excluded.user_id,
            asset_kind=excluded.asset_kind,
            display_name=excluded.display_name,
            workspace_id=excluded.workspace_id,
            object_key=excluded.object_key,
            mime_type=excluded.mime_type,
            extension=excluded.extension,
            created_at=excluded.created_at,
            updated_at=excluded.updated_at,
            payload_json=excluded.payload_json
        """,
        (
            str(asset.get("asset_id") or ""),
            user_id,
            str(asset.get("asset_kind") or ""),
            str(asset.get("display_name") or ""),
            str(asset.get("workspace_id") or ""),
            str(file_payload.get("object_key") or asset.get("object_key") or ""),
            str(file_payload.get("mime_type") or asset.get("mime_type") or ""),
            str(file_payload.get("extension") or asset.get("extension") or ""),
            str(metadata.get("created_at") or asset.get("created_at") or ""),
            utc_now_iso(),
            json.dumps(asset, ensure_ascii=False),
        ),
    )


def _apply_candidate_document_normalization_migration(connection: DatabaseConnection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS candidate_assets (
            asset_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            asset_kind TEXT NOT NULL DEFAULT '',
            display_name TEXT NOT NULL DEFAULT '',
            workspace_id TEXT NOT NULL DEFAULT '',
            object_key TEXT NOT NULL DEFAULT '',
            mime_type TEXT NOT NULL DEFAULT '',
            extension TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS candidate_documents (
            document_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL DEFAULT '',
            asset_id TEXT NOT NULL DEFAULT '',
            workspace_id TEXT NOT NULL DEFAULT '',
            document_kind TEXT NOT NULL DEFAULT '',
            object_key TEXT NOT NULL DEFAULT '',
            char_count INTEGER NOT NULL DEFAULT 0,
            source_text TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS workspace_document_bindings (
            workspace_id TEXT NOT NULL,
            binding_key TEXT NOT NULL,
            document_id TEXT NOT NULL,
            asset_id TEXT NOT NULL DEFAULT '',
            object_key TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            PRIMARY KEY (workspace_id, binding_key)
        );
        CREATE TABLE IF NOT EXISTS run_document_bindings (
            run_id TEXT NOT NULL,
            binding_key TEXT NOT NULL,
            document_id TEXT NOT NULL,
            asset_id TEXT NOT NULL DEFAULT '',
            object_key TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            PRIMARY KEY (run_id, binding_key)
        );
        CREATE INDEX IF NOT EXISTS idx_candidate_assets_user_kind_updated
            ON candidate_assets(user_id, asset_kind, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_candidate_assets_workspace
            ON candidate_assets(workspace_id, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_candidate_documents_asset
            ON candidate_documents(asset_id);
        CREATE INDEX IF NOT EXISTS idx_candidate_documents_user_kind
            ON candidate_documents(user_id, document_kind, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_workspace_document_bindings_document
            ON workspace_document_bindings(document_id);
        CREATE INDEX IF NOT EXISTS idx_run_document_bindings_document
            ON run_document_bindings(document_id);
        """
    )

    for row in connection.execute("SELECT user_id, payload_json FROM users").fetchall():
        payload = json.loads(str(row["payload_json"] or "{}"))
        clean, assets, documents = prepare_user_payload(payload)
        if assets is not None:
            for asset in assets:
                _upsert_candidate_asset(connection, user_id=str(row["user_id"]), asset=asset)
        for document in documents:
            _upsert_candidate_document(connection, document)
        connection.execute(
            "UPDATE users SET payload_json = ? WHERE user_id = ?",
            (json.dumps(clean, ensure_ascii=False), str(row["user_id"])),
        )

    for row in connection.execute("SELECT id, payload_json FROM workspaces").fetchall():
        payload = json.loads(str(row["payload_json"] or "{}"))
        clean, document = prepare_workspace_payload(payload)
        if document is not None:
            _upsert_candidate_document(
                connection,
                {
                    **document,
                    "document_kind": "workspace_cv",
                },
            )
            connection.execute(
                """
                INSERT INTO workspace_document_bindings (
                    workspace_id, binding_key, document_id, asset_id, object_key, updated_at
                ) VALUES (?, 'workspace_cv', ?, ?, ?, ?)
                ON CONFLICT(workspace_id, binding_key) DO UPDATE SET
                    document_id=excluded.document_id,
                    asset_id=excluded.asset_id,
                    object_key=excluded.object_key,
                    updated_at=excluded.updated_at
                """,
                (
                    document["workspace_id"],
                    document["document_id"],
                    document["asset_id"],
                    document["object_key"],
                    utc_now_iso(),
                ),
            )
        connection.execute(
            "UPDATE workspaces SET payload_json = ? WHERE id = ?",
            (json.dumps(clean, ensure_ascii=False), str(row["id"])),
        )

    for row in connection.execute("SELECT id, payload_json FROM runs").fetchall():
        payload = json.loads(str(row["payload_json"] or "{}"))
        clean, document = prepare_run_payload(payload)
        if document is not None:
            _upsert_candidate_document(
                connection,
                {
                    **document,
                    "document_kind": "workspace_cv",
                },
            )
            connection.execute(
                """
                INSERT INTO run_document_bindings (
                    run_id, binding_key, document_id, asset_id, object_key, updated_at
                ) VALUES (?, 'workspace_cv', ?, ?, ?, ?)
                ON CONFLICT(run_id, binding_key) DO UPDATE SET
                    document_id=excluded.document_id,
                    asset_id=excluded.asset_id,
                    object_key=excluded.object_key,
                    updated_at=excluded.updated_at
                """,
                (
                    document["run_id"],
                    document["document_id"],
                    document["asset_id"],
                    document["object_key"],
                    utc_now_iso(),
                ),
            )
        run_plan = dict(clean.get("run_plan") or {})
        connection.execute(
            """
            UPDATE runs
            SET payload_json = ?, run_input_overrides_json = ?, run_plan_json = ?, metadata_json = ?
            WHERE id = ?
            """,
            (
                json.dumps(clean, ensure_ascii=False),
                json.dumps(clean.get("run_input_overrides") or {}, ensure_ascii=False),
                json.dumps(run_plan, ensure_ascii=False),
                json.dumps(clean.get("metadata") or {}, ensure_ascii=False),
                str(row["id"]),
            ),
        )


def _apply_workspace_ownership_migration(connection: DatabaseConnection) -> None:
    _ensure_table_column(connection, "workspaces", "owner_user_id", "TEXT NOT NULL DEFAULT ''")
    user_ids = {
        str(row["user_id"] or "").strip()
        for row in connection.execute("SELECT user_id FROM users").fetchall()
        if str(row["user_id"] or "").strip()
    }
    sole_user_id = next(iter(user_ids)) if len(user_ids) == 1 else ""

    for row in connection.execute(
        "SELECT id, owner_user_id, payload_json FROM workspaces"
    ).fetchall():
        workspace_id = str(row["id"] or "").strip()
        payload = json.loads(str(row["payload_json"] or "{}"))
        owner_user_id = str(
            row["owner_user_id"]
            or payload.get("owner_user_id")
            or dict(payload.get("metadata") or {}).get("owner_user_id")
            or ""
        ).strip()
        if not owner_user_id:
            run_owner_rows = connection.execute(
                "SELECT DISTINCT user_id FROM runs WHERE workspace_id = ? AND user_id != ''",
                (workspace_id,),
            ).fetchall()
            run_owner_ids = {
                str(run_row["user_id"] or "").strip()
                for run_row in run_owner_rows
                if str(run_row["user_id"] or "").strip()
            }
            if len(run_owner_ids) == 1:
                owner_user_id = next(iter(run_owner_ids))
            elif not run_owner_ids:
                owner_user_id = sole_user_id

        payload["owner_user_id"] = owner_user_id
        connection.execute(
            "UPDATE workspaces SET owner_user_id = ?, payload_json = ? WHERE id = ?",
            (owner_user_id, json.dumps(payload, ensure_ascii=False), workspace_id),
        )

    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_workspaces_owner_user_id "
        "ON workspaces(owner_user_id, updated_at DESC)"
    )


def _apply_email_sync_start_date_migration(connection: DatabaseConnection) -> None:
    """015: Add email sync start date, status, and scheduling columns. Remove scan_depth/max_messages."""
    _ensure_user_column(connection, "email_sync_enabled", "INTEGER NOT NULL DEFAULT 0")
    _ensure_user_column(connection, "email_sync_start_date", "TEXT NOT NULL DEFAULT ''")
    _ensure_user_column(connection, "last_email_sync_at", "TEXT NOT NULL DEFAULT ''")
    _ensure_user_column(connection, "next_email_sync_at", "TEXT NOT NULL DEFAULT ''")
    _ensure_user_column(connection, "email_sync_status", "TEXT NOT NULL DEFAULT 'idle'")
    _ensure_user_column(connection, "email_sync_error", "TEXT NOT NULL DEFAULT ''")
    _ensure_user_column(connection, "last_processed_history_id", "TEXT NOT NULL DEFAULT ''")

    for row in connection.execute("SELECT user_id, payload_json FROM users").fetchall():
        payload = json.loads(str(row["payload_json"] or "{}"))
        tracker_config = dict(payload.get("tracker_email_integration") or {})
        if not tracker_config:
            continue
        tracker_config.pop("max_messages", None)
        tracker_config.pop("scan_window", None)
        tracker_config["email_sync_start_date"] = ""
        tracker_config["email_sync_enabled"] = False
        tracker_config["last_email_sync_at"] = ""
        tracker_config["next_email_sync_at"] = ""
        tracker_config["email_sync_status"] = "idle"
        tracker_config["email_sync_error"] = ""
        tracker_config["last_processed_history_id"] = ""
        payload["tracker_email_integration"] = tracker_config
        connection.execute(
            "UPDATE users SET payload_json = ? WHERE user_id = ?",
            (json.dumps(payload, ensure_ascii=False), str(row["user_id"])),
        )

    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_email_sync_enabled_next_at "
        "ON users(email_sync_enabled, next_email_sync_at)"
    )


def _apply_assisted_apply_connections_migration(connection: DatabaseConnection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS assisted_apply_connections (
            request_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            user_id TEXT NOT NULL DEFAULT '',
            extension_id TEXT NOT NULL,
            extension_origin TEXT NOT NULL,
            callback_url TEXT NOT NULL,
            client_state TEXT NOT NULL,
            pkce_challenge TEXT NOT NULL,
            installation_id TEXT NOT NULL,
            extension_version TEXT NOT NULL,
            request_expires_at TEXT NOT NULL,
            authorization_code_prefix TEXT NOT NULL DEFAULT '',
            authorization_code_hash TEXT NOT NULL DEFAULT '',
            authorization_code_expires_at TEXT NOT NULL DEFAULT '',
            authorized_at TEXT NOT NULL DEFAULT '',
            code_consumed_at TEXT NOT NULL DEFAULT '',
            session_token_prefix TEXT NOT NULL DEFAULT '',
            session_token_hash TEXT NOT NULL DEFAULT '',
            session_expires_at TEXT NOT NULL DEFAULT '',
            activated_at TEXT NOT NULL DEFAULT '',
            last_used_at TEXT NOT NULL DEFAULT '',
            rejected_at TEXT NOT NULL DEFAULT '',
            revoked_at TEXT NOT NULL DEFAULT '',
            expired_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_assisted_apply_connections_user_updated
            ON assisted_apply_connections(user_id, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_assisted_apply_connections_status_updated
            ON assisted_apply_connections(status, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_assisted_apply_connections_session_prefix
            ON assisted_apply_connections(session_token_prefix, status);
        """
    )


def _apply_application_packages_migration(connection: DatabaseConnection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS application_packages (
            package_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            job_id TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL,
            schema_version INTEGER NOT NULL DEFAULT 1,
            launch_tab_binding_id TEXT NOT NULL DEFAULT '',
            launch_tab_binding_expires_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            launched_at TEXT NOT NULL DEFAULT '',
            bound_at TEXT NOT NULL DEFAULT '',
            expired_at TEXT NOT NULL DEFAULT '',
            consumed_at TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_application_packages_user_job
            ON application_packages(user_id, job_id, version DESC);
        CREATE INDEX IF NOT EXISTS idx_application_packages_status_created
            ON application_packages(status, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_application_packages_binding
            ON application_packages(launch_tab_binding_id)
            WHERE launch_tab_binding_id != '';
        """
    )


def _apply_assisted_apply_corrections_migration(connection: DatabaseConnection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS assisted_apply_corrections (
            correction_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            source_package_id TEXT NOT NULL,
            source_job_id TEXT NOT NULL,
            field_intent TEXT NOT NULL,
            corrected_value TEXT NOT NULL,
            scope TEXT NOT NULL CHECK (scope IN ('country', 'role', 'company', 'global')),
            scope_key TEXT NOT NULL,
            provenance TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            superseded_at TEXT NOT NULL DEFAULT '',
            superseded_by TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_assisted_apply_corrections_match
            ON assisted_apply_corrections(user_id, field_intent, scope, scope_key, expires_at)
            WHERE superseded_at = '';
        CREATE TABLE IF NOT EXISTS assisted_apply_correction_audit (
            audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            correction_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            details_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_assisted_apply_correction_audit_owner
            ON assisted_apply_correction_audit(user_id, occurred_at DESC);
        """
    )


def _apply_assisted_apply_document_grants_migration(connection: DatabaseConnection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS assisted_apply_document_grants (
            grant_id TEXT PRIMARY KEY,
            grant_token_prefix TEXT NOT NULL,
            grant_token_hash TEXT NOT NULL,
            user_id TEXT NOT NULL,
            connection_request_id TEXT NOT NULL,
            extension_origin TEXT NOT NULL,
            package_id TEXT NOT NULL,
            document_id TEXT NOT NULL,
            document_version INTEGER NOT NULL DEFAULT 1,
            asset_id TEXT NOT NULL,
            object_key TEXT NOT NULL,
            file_name TEXT NOT NULL,
            mime_type TEXT NOT NULL,
            expected_size INTEGER NOT NULL,
            expected_sha256_hex TEXT NOT NULL,
            status TEXT NOT NULL,
            failure_reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            consumed_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_assisted_apply_document_grants_token
            ON assisted_apply_document_grants(grant_token_prefix, status);
        CREATE INDEX IF NOT EXISTS idx_assisted_apply_document_grants_package
            ON assisted_apply_document_grants(package_id, document_id, created_at DESC);
        """
    )


def _apply_assisted_apply_tracker_confirmation_migration(connection: DatabaseConnection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS assisted_apply_submission_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            package_id TEXT NOT NULL,
            package_version INTEGER NOT NULL,
            adapter TEXT NOT NULL CHECK (adapter IN ('greenhouse', 'lever')),
            adapter_version TEXT NOT NULL,
            event_type TEXT NOT NULL CHECK (
                event_type IN ('possible_success', 'user_confirmed', 'user_declined')
            ),
            evidence_category TEXT NOT NULL CHECK (
                evidence_category IN ('success_banner', 'confirmation_page', 'url_transition')
            ),
            occurred_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_assisted_apply_submission_events_owner
            ON assisted_apply_submission_events(user_id, occurred_at DESC);
        CREATE TABLE IF NOT EXISTS assisted_apply_tracker_records (
            tracker_record_id TEXT PRIMARY KEY,
            idempotency_key TEXT NOT NULL UNIQUE,
            user_id TEXT NOT NULL,
            job_id TEXT NOT NULL,
            package_id TEXT NOT NULL,
            package_version INTEGER NOT NULL,
            adapter TEXT NOT NULL,
            adapter_version TEXT NOT NULL,
            document_versions_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_assisted_apply_tracker_records_owner
            ON assisted_apply_tracker_records(user_id, created_at DESC);
        """
    )


def _apply_assisted_apply_document_grant_intents_migration(connection: DatabaseConnection) -> None:
    connection.execute(
        "ALTER TABLE assisted_apply_document_grants ADD COLUMN upload_field_intent TEXT NOT NULL DEFAULT ''"
    )


def _apply_assisted_apply_preparations_migration(connection: DatabaseConnection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS assisted_apply_preparations (
            preparation_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            package_id TEXT NOT NULL,
            job_id TEXT NOT NULL,
            ats TEXT NOT NULL,
            application_url TEXT NOT NULL,
            state TEXT NOT NULL,
            total_count INTEGER NOT NULL DEFAULT 0,
            completed_count INTEGER NOT NULL DEFAULT 0,
            error_category TEXT NOT NULL DEFAULT '',
            attempt_count INTEGER NOT NULL DEFAULT 1,
            session_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            started_at TEXT NOT NULL DEFAULT '',
            ready_at TEXT NOT NULL DEFAULT '',
            attention_at TEXT NOT NULL DEFAULT '',
            cancelled_at TEXT NOT NULL DEFAULT '',
            expired_at TEXT NOT NULL DEFAULT '',
            last_report_id TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_assisted_apply_preparations_user_created
            ON assisted_apply_preparations(user_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_assisted_apply_preparations_package
            ON assisted_apply_preparations(package_id, created_at DESC);
        CREATE TABLE IF NOT EXISTS assisted_apply_preparation_reports (
            report_id TEXT PRIMARY KEY,
            preparation_id TEXT NOT NULL,
            report_type TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_assisted_apply_preparation_reports_session
            ON assisted_apply_preparation_reports(preparation_id, created_at DESC);
        """
    )


def _apply_career_profiles_migration(connection: DatabaseConnection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS career_profiles (
            profile_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            preferred_language TEXT NOT NULL DEFAULT 'en',
            target_direction TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'not_started',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_career_profiles_user_updated
            ON career_profiles(user_id, updated_at DESC);
        """
    )


def _apply_career_profiles_workspace_binding_migration(connection: DatabaseConnection) -> None:
    connection.executescript(
        """
        ALTER TABLE career_profiles ADD COLUMN bound_workspace_id TEXT NOT NULL DEFAULT '';
        """
    )



def _apply_career_profiles_baseline_cv_migration(connection: DatabaseConnection) -> None:
    connection.executescript(
        """
        ALTER TABLE career_profiles ADD COLUMN baseline_cv_asset_id TEXT NOT NULL DEFAULT '';
        ALTER TABLE career_profiles ADD COLUMN baseline_cv_display_name TEXT NOT NULL DEFAULT '';
        ALTER TABLE career_profiles ADD COLUMN baseline_cv_extraction_date TEXT NOT NULL DEFAULT '';
        ALTER TABLE career_profiles ADD COLUMN baseline_cv_source_version TEXT NOT NULL DEFAULT '';
        """
    )






def _apply_work_experiences_migration(connection: DatabaseConnection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS work_experiences (
            experience_id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            employer TEXT NOT NULL DEFAULT '',
            job_title TEXT NOT NULL DEFAULT '',
            location TEXT NOT NULL DEFAULT '',
            start_date TEXT NOT NULL DEFAULT '',
            end_date TEXT NOT NULL DEFAULT '',
            employment_type TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            source_kind TEXT NOT NULL DEFAULT 'manual',
            source_asset_ids_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'active',
            merged_into_id TEXT NOT NULL DEFAULT '',
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_work_experiences_profile
            ON work_experiences(profile_id, status, sort_order);
        CREATE INDEX IF NOT EXISTS idx_work_experiences_profile_updated
            ON work_experiences(profile_id, updated_at DESC);

        CREATE TABLE IF NOT EXISTS work_experience_merge_suggestions (
            suggestion_id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            experience_ids_json TEXT NOT NULL DEFAULT '[]',
            suggested_merged_record_json TEXT NOT NULL DEFAULT '{}',
            match_score REAL NOT NULL DEFAULT 0.0,
            match_reason TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_work_experience_merge_suggestions_profile
            ON work_experience_merge_suggestions(profile_id, status);
        """
    )



def _apply_profile_versioning_migration(connection: DatabaseConnection) -> None:
    """Create profile version, CV version, and generation provenance tables (CP-025)."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS profile_versions (
            version_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            version_no INTEGER NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT 'saved',
            workspace_snapshot_json TEXT NOT NULL DEFAULT '{}',
            resolved_settings_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            run_id TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_profile_versions_workspace_version
            ON profile_versions(workspace_id, version_no DESC);
        CREATE INDEX IF NOT EXISTS idx_profile_versions_run
            ON profile_versions(run_id)
            WHERE run_id != '';

        CREATE TABLE IF NOT EXISTS cv_asset_versions (
            version_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            asset_id TEXT NOT NULL DEFAULT '',
            version_no INTEGER NOT NULL,
            source TEXT NOT NULL DEFAULT 'uploaded',
            display_name TEXT NOT NULL DEFAULT '',
            object_key TEXT NOT NULL DEFAULT '',
            mime_type TEXT NOT NULL DEFAULT '',
            extension TEXT NOT NULL DEFAULT '',
            char_count INTEGER NOT NULL DEFAULT 0,
            cv_text_sha256 TEXT NOT NULL DEFAULT '',
            source_text_preview TEXT NOT NULL DEFAULT '',
            extraction_timestamp TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            run_id TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_cv_asset_versions_workspace_version
            ON cv_asset_versions(workspace_id, version_no DESC);
        CREATE INDEX IF NOT EXISTS idx_cv_asset_versions_asset
            ON cv_asset_versions(asset_id, version_no DESC);

        CREATE TABLE IF NOT EXISTS generation_provenance (
            provenance_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            workspace_id TEXT NOT NULL DEFAULT '',
            job_id TEXT NOT NULL DEFAULT '',
            profile_version_id TEXT NOT NULL DEFAULT '',
            profile_version_no INTEGER NOT NULL DEFAULT 0,
            cv_asset_version_id TEXT NOT NULL DEFAULT '',
            cv_asset_version_no INTEGER NOT NULL DEFAULT 0,
            evidence_set_key TEXT NOT NULL DEFAULT '',
            evidence_job_count INTEGER NOT NULL DEFAULT 0,
            generation_pipeline_version TEXT NOT NULL DEFAULT '',
            generation_mode TEXT NOT NULL DEFAULT '',
            generation_fingerprint TEXT NOT NULL DEFAULT '',
            renderer_version TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_generation_provenance_run
            ON generation_provenance(run_id, job_id);
        CREATE INDEX IF NOT EXISTS idx_generation_provenance_workspace
            ON generation_provenance(workspace_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_generation_provenance_profile_version
            ON generation_provenance(profile_version_id, created_at DESC);
        """
    )




def _apply_evidence_storage_migration(connection: DatabaseConnection) -> None:
    """Create evidence and evidence state history tables for CP-028."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS evidence (
            evidence_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL DEFAULT '',
            run_id TEXT NOT NULL DEFAULT '',
            kind TEXT NOT NULL DEFAULT 'evidence',
            state TEXT NOT NULL DEFAULT 'draft',
            label TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            source_ref TEXT NOT NULL DEFAULT '',
            source_type TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS evidence_state_history (
            history_id TEXT PRIMARY KEY,
            evidence_id TEXT NOT NULL,
            from_state TEXT NOT NULL DEFAULT '',
            to_state TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            actor TEXT NOT NULL DEFAULT '',
            occurred_at TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_evidence_workspace_state
            ON evidence(workspace_id, state);
        CREATE INDEX IF NOT EXISTS idx_evidence_run_id
            ON evidence(run_id);
        CREATE INDEX IF NOT EXISTS idx_evidence_kind_state
            ON evidence(kind, state);
        CREATE INDEX IF NOT EXISTS idx_evidence_state_history_evidence
            ON evidence_state_history(evidence_id, occurred_at DESC);
        """
    )


def _apply_phase_a_acquisition_migration(connection: DatabaseConnection) -> None:
    """Create system-owned Phase A acquisition and catalog storage."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS acquisition_targets (
            target_id TEXT PRIMARY KEY,
            target_kind TEXT NOT NULL,
            display_name TEXT NOT NULL,
            canonical_target_url TEXT NOT NULL,
            provenance_url TEXT NOT NULL DEFAULT '',
            request_url TEXT NOT NULL,
            connector TEXT NOT NULL,
            provider TEXT NOT NULL DEFAULT '',
            source_token TEXT NOT NULL DEFAULT '',
            policy_version TEXT NOT NULL,
            maturity_state TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 0,
            publication_enabled INTEGER NOT NULL DEFAULT 0,
            max_direct_requests INTEGER NOT NULL DEFAULT 3,
            request_mode TEXT NOT NULL DEFAULT 'direct',
            zero_yield_streak INTEGER NOT NULL DEFAULT 0,
            last_attempt_at TEXT NOT NULL DEFAULT '',
            last_success_at TEXT NOT NULL DEFAULT '',
            last_state_transition_at TEXT NOT NULL DEFAULT '',
            state_transition_reason TEXT NOT NULL DEFAULT '',
            config_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_acquisition_targets_state
            ON acquisition_targets(maturity_state, enabled);

        CREATE TABLE IF NOT EXISTS acquisition_cycles (
            cycle_id TEXT PRIMARY KEY,
            window_key TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            lease_owner TEXT NOT NULL DEFAULT '',
            lease_expires_at TEXT NOT NULL DEFAULT '',
            scheduled_at TEXT NOT NULL,
            started_at TEXT NOT NULL DEFAULT '',
            completed_at TEXT NOT NULL DEFAULT '',
            forecast_requests INTEGER NOT NULL DEFAULT 0,
            forecast_credits INTEGER NOT NULL DEFAULT 0,
            reserved_requests INTEGER NOT NULL DEFAULT 0,
            reserved_credits INTEGER NOT NULL DEFAULT 0,
            actual_requests INTEGER NOT NULL DEFAULT 0,
            actual_credits INTEGER NOT NULL DEFAULT 0,
            jobs_observed INTEGER NOT NULL DEFAULT 0,
            jobs_new INTEGER NOT NULL DEFAULT 0,
            jobs_updated INTEGER NOT NULL DEFAULT 0,
            jobs_unchanged INTEGER NOT NULL DEFAULT 0,
            jobs_closed INTEGER NOT NULL DEFAULT 0,
            jobs_rejected INTEGER NOT NULL DEFAULT 0,
            jobs_duplicates INTEGER NOT NULL DEFAULT 0,
            jobs_published INTEGER NOT NULL DEFAULT 0,
            publication_id TEXT NOT NULL DEFAULT '',
            error_code TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_acquisition_cycles_status
            ON acquisition_cycles(status, scheduled_at DESC);

        CREATE TABLE IF NOT EXISTS acquisition_tasks (
            task_id TEXT PRIMARY KEY,
            cycle_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            status TEXT NOT NULL,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            lease_owner TEXT NOT NULL DEFAULT '',
            lease_expires_at TEXT NOT NULL DEFAULT '',
            started_at TEXT NOT NULL DEFAULT '',
            completed_at TEXT NOT NULL DEFAULT '',
            complete_snapshot INTEGER NOT NULL DEFAULT 0,
            valid_snapshot INTEGER NOT NULL DEFAULT 0,
            credible_evidence INTEGER NOT NULL DEFAULT 0,
            requests_avoided INTEGER NOT NULL DEFAULT 0,
            credits_avoided INTEGER NOT NULL DEFAULT 0,
            jobs_observed INTEGER NOT NULL DEFAULT 0,
            jobs_new INTEGER NOT NULL DEFAULT 0,
            jobs_updated INTEGER NOT NULL DEFAULT 0,
            jobs_unchanged INTEGER NOT NULL DEFAULT 0,
            jobs_closed INTEGER NOT NULL DEFAULT 0,
            jobs_rejected INTEGER NOT NULL DEFAULT 0,
            jobs_duplicates INTEGER NOT NULL DEFAULT 0,
            error_code TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(cycle_id, target_id)
        );
        CREATE INDEX IF NOT EXISTS idx_acquisition_tasks_claim
            ON acquisition_tasks(cycle_id, status, created_at);

        CREATE TABLE IF NOT EXISTS acquisition_target_attempts (
            attempt_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            cycle_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            attempt_number INTEGER NOT NULL,
            status TEXT NOT NULL,
            complete_snapshot INTEGER NOT NULL DEFAULT 0,
            valid_snapshot INTEGER NOT NULL DEFAULT 0,
            credible_evidence INTEGER NOT NULL DEFAULT 0,
            request_count INTEGER NOT NULL DEFAULT 0,
            credits_actual INTEGER NOT NULL DEFAULT 0,
            jobs_found INTEGER NOT NULL DEFAULT 0,
            state_before TEXT NOT NULL DEFAULT '',
            state_after TEXT NOT NULL DEFAULT '',
            reason TEXT NOT NULL DEFAULT '',
            error_code TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            started_at TEXT NOT NULL,
            completed_at TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_acquisition_target_attempts_target
            ON acquisition_target_attempts(target_id, started_at DESC);

        CREATE TABLE IF NOT EXISTS acquisition_requests (
            request_id TEXT PRIMARY KEY,
            idempotency_key TEXT NOT NULL UNIQUE,
            cycle_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            request_url TEXT NOT NULL,
            method TEXT NOT NULL,
            mode TEXT NOT NULL,
            request_kind TEXT NOT NULL,
            status TEXT NOT NULL,
            provider_status INTEGER NOT NULL DEFAULT 0,
            credits_estimated INTEGER NOT NULL DEFAULT 0,
            credits_actual INTEGER NOT NULL DEFAULT 0,
            jobs_returned INTEGER NOT NULL DEFAULT 0,
            resolved_url TEXT NOT NULL DEFAULT '',
            detail_json TEXT NOT NULL DEFAULT '{}',
            started_at TEXT NOT NULL,
            completed_at TEXT NOT NULL DEFAULT '',
            error_code TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_acquisition_requests_target
            ON acquisition_requests(target_id, started_at DESC);

        CREATE TABLE IF NOT EXISTS acquisition_budget_reservations (
            reservation_id TEXT PRIMARY KEY,
            idempotency_key TEXT NOT NULL UNIQUE,
            cycle_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            request_limit INTEGER NOT NULL DEFAULT 0,
            credit_limit INTEGER NOT NULL DEFAULT 0,
            requests_reserved INTEGER NOT NULL DEFAULT 0,
            credits_reserved INTEGER NOT NULL DEFAULT 0,
            requests_actual INTEGER NOT NULL DEFAULT 0,
            credits_actual INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            reconciled_at TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS canonical_companies (
            company_id TEXT PRIMARY KEY,
            canonical_name TEXT NOT NULL,
            entity_kind TEXT NOT NULL DEFAULT 'employer',
            provenance_url TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(canonical_name, entity_kind)
        );

        CREATE TABLE IF NOT EXISTS canonical_jobs (
            canonical_job_id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL,
            identity_key TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            location TEXT NOT NULL DEFAULT '',
            canonical_url TEXT NOT NULL DEFAULT '',
            lifecycle_state TEXT NOT NULL DEFAULT 'active',
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            last_verified_at TEXT NOT NULL DEFAULT '',
            absence_count INTEGER NOT NULL DEFAULT 0,
            current_version_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_canonical_jobs_lifecycle
            ON canonical_jobs(lifecycle_state, last_verified_at DESC);

        CREATE TABLE IF NOT EXISTS canonical_job_url_aliases (
            alias_id TEXT PRIMARY KEY,
            canonical_job_id TEXT NOT NULL,
            url TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            UNIQUE(canonical_job_id, url)
        );
        CREATE INDEX IF NOT EXISTS idx_canonical_job_url_aliases_url
            ON canonical_job_url_aliases(url);

        CREATE TABLE IF NOT EXISTS canonical_job_relationships (
            relationship_id TEXT PRIMARY KEY,
            canonical_job_id TEXT NOT NULL,
            related_job_id TEXT NOT NULL,
            relationship_type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(canonical_job_id, related_job_id, relationship_type)
        );

        CREATE TABLE IF NOT EXISTS job_source_observations (
            observation_id TEXT PRIMARY KEY,
            canonical_job_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            cycle_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            external_job_id TEXT NOT NULL,
            original_url TEXT NOT NULL DEFAULT '',
            apply_url TEXT NOT NULL DEFAULT '',
            source_ats TEXT NOT NULL DEFAULT '',
            content_hash TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}',
            observed_at TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            UNIQUE(target_id, cycle_id, external_job_id)
        );
        CREATE INDEX IF NOT EXISTS idx_job_source_observations_lookup
            ON job_source_observations(target_id, external_job_id, observed_at DESC);

        CREATE TABLE IF NOT EXISTS job_posting_versions (
            version_id TEXT PRIMARY KEY,
            canonical_job_id TEXT NOT NULL,
            version_number INTEGER NOT NULL,
            content_hash TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            location TEXT NOT NULL DEFAULT '',
            apply_url TEXT NOT NULL DEFAULT '',
            source_observation_id TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            UNIQUE(canonical_job_id, version_number)
        );

        CREATE TABLE IF NOT EXISTS acquisition_publications (
            publication_id TEXT PRIMARY KEY,
            cycle_id TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            snapshot_json TEXT NOT NULL DEFAULT '[]',
            published_at TEXT NOT NULL,
            valid_until TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS acquisition_publication_jobs (
            publication_id TEXT NOT NULL,
            canonical_job_id TEXT NOT NULL,
            PRIMARY KEY(publication_id, canonical_job_id)
        );
        """
    )


def _apply_phase_a_publication_head_migration(connection: DatabaseConnection) -> None:
    """Add a singleton pointer for the currently served valid publication."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS acquisition_publication_head (
            head_id INTEGER PRIMARY KEY CHECK (head_id = 1),
            publication_id TEXT NOT NULL UNIQUE,
            updated_at TEXT NOT NULL
        );
        """
    )


def _apply_phase_a_published_jobs_migration(connection: DatabaseConnection) -> None:
    """Keep per-target published-job counts on durable acquisition tasks."""
    _ensure_table_column(connection, "acquisition_tasks", "jobs_published", "INTEGER NOT NULL DEFAULT 0")


def _apply_phase_a_request_state_migration(connection: DatabaseConnection) -> None:
    """Add write-ahead dispatch and uncertain-outcome metadata."""
    _ensure_table_column(connection, "acquisition_requests", "dispatch_started_at", "TEXT NOT NULL DEFAULT ''")
    _ensure_table_column(connection, "acquisition_requests", "latency_ms", "INTEGER NOT NULL DEFAULT 0")
    _ensure_table_column(connection, "acquisition_requests", "recovery_state", "TEXT NOT NULL DEFAULT ''")
    _ensure_table_column(
        connection,
        "acquisition_requests",
        "uncertain_external_outcome",
        "INTEGER NOT NULL DEFAULT 0",
    )


def _apply_phase_b_catalog_migration(connection: DatabaseConnection) -> None:
    """Add durable Phase B rejection evidence without changing Phase A tables."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS acquisition_job_rejections (
            rejection_id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL,
            cycle_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            external_job_id TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            reason_code TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            detail_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_acquisition_job_rejections_target
            ON acquisition_job_rejections(target_id, observed_at DESC);
        CREATE INDEX IF NOT EXISTS idx_acquisition_job_rejections_request
            ON acquisition_job_rejections(request_id);
        """
    )


def _apply_phase_b_catalog_correctness_migration(connection: DatabaseConnection) -> None:
    """Add source-scoped identity, lifecycle, replay, and immutability contracts."""
    _ensure_table_column(connection, "canonical_jobs", "identity_signature", "TEXT NOT NULL DEFAULT ''")
    connection.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_canonical_jobs_identity_signature
            ON canonical_jobs(identity_signature, lifecycle_state, first_seen_at);

        CREATE TABLE IF NOT EXISTS canonical_job_external_ids (
            external_id_id TEXT PRIMARY KEY,
            canonical_job_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            external_job_id TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            UNIQUE(source_id, external_job_id)
        );
        CREATE INDEX IF NOT EXISTS idx_canonical_job_external_ids_job
            ON canonical_job_external_ids(canonical_job_id, source_id);

        CREATE TABLE IF NOT EXISTS job_source_states (
            source_state_id TEXT PRIMARY KEY,
            target_id TEXT NOT NULL,
            canonical_job_id TEXT NOT NULL,
            external_job_id TEXT NOT NULL,
            lifecycle_state TEXT NOT NULL DEFAULT 'unknown',
            absence_count INTEGER NOT NULL DEFAULT 0,
            grace_attempts INTEGER NOT NULL DEFAULT 3,
            last_seen_at TEXT NOT NULL DEFAULT '',
            last_checked_at TEXT NOT NULL DEFAULT '',
            last_cycle_id TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            UNIQUE(target_id, external_job_id)
        );
        CREATE INDEX IF NOT EXISTS idx_job_source_states_job
            ON job_source_states(canonical_job_id, lifecycle_state, target_id);

        CREATE TABLE IF NOT EXISTS job_source_observation_relationships (
            relationship_id TEXT PRIMARY KEY,
            observation_id TEXT NOT NULL,
            related_observation_id TEXT NOT NULL,
            relationship_type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(observation_id, related_observation_id, relationship_type)
        );
        CREATE INDEX IF NOT EXISTS idx_job_source_observation_relationships_observation
            ON job_source_observation_relationships(observation_id, relationship_type);

        CREATE UNIQUE INDEX IF NOT EXISTS idx_acquisition_job_rejections_replay
            ON acquisition_job_rejections(request_id, external_job_id, title, reason_code);

        CREATE TRIGGER IF NOT EXISTS trg_job_posting_versions_immutable_update
        BEFORE UPDATE ON job_posting_versions
        BEGIN
            SELECT RAISE(ABORT, 'job_posting_versions are immutable');
        END;

        CREATE TRIGGER IF NOT EXISTS trg_job_posting_versions_immutable_delete
        BEFORE DELETE ON job_posting_versions
        BEGIN
            SELECT RAISE(ABORT, 'job_posting_versions are immutable');
        END;
        """
    )


def _apply_phase_c_personalized_jobs_migration(connection: DatabaseConnection) -> None:
    """Create user-owned preferences, dispositions, events, and evaluations."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS personalized_search_preferences (
            user_id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL DEFAULT '',
            revision INTEGER NOT NULL DEFAULT 1,
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS personalized_saved_searches (
            saved_search_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL DEFAULT 'Default search',
            payload_json TEXT NOT NULL DEFAULT '{}',
            is_default INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS personalized_job_dispositions (
            user_id TEXT NOT NULL,
            canonical_job_id TEXT NOT NULL,
            state TEXT NOT NULL,
            source_of_change TEXT NOT NULL DEFAULT 'user',
            reason_code TEXT NOT NULL DEFAULT '',
            applied_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, canonical_job_id)
        );
        CREATE INDEX IF NOT EXISTS idx_personalized_dispositions_user_state
            ON personalized_job_dispositions(user_id, state, updated_at DESC);

        CREATE TABLE IF NOT EXISTS personalized_job_events (
            event_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            canonical_job_id TEXT NOT NULL DEFAULT '',
            event_name TEXT NOT NULL,
            reason_code TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}',
            occurred_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_personalized_events_user_time
            ON personalized_job_events(user_id, occurred_at DESC);

        CREATE TABLE IF NOT EXISTS personalized_job_evaluations (
            user_id TEXT NOT NULL,
            canonical_job_id TEXT NOT NULL,
            job_version_id TEXT NOT NULL DEFAULT '',
            preferences_revision INTEGER NOT NULL DEFAULT 0,
            evaluator_version TEXT NOT NULL,
            state TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (
                user_id, canonical_job_id, job_version_id,
                preferences_revision, evaluator_version
            )
        );
        CREATE INDEX IF NOT EXISTS idx_personalized_evaluations_user_job
            ON personalized_job_evaluations(user_id, canonical_job_id, updated_at DESC);
        """
    )


def _apply_phase_e_job_intelligence_migration(connection: DatabaseConnection) -> None:
    """Cache description intelligence against immutable job versions."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS job_description_intelligence (
            version_id TEXT PRIMARY KEY,
            canonical_job_id TEXT NOT NULL,
            content_hash TEXT NOT NULL DEFAULT '',
            summary_json TEXT NOT NULL DEFAULT '{}',
            structured_json TEXT NOT NULL DEFAULT '{}',
            original_json TEXT NOT NULL DEFAULT '{}',
            provider TEXT NOT NULL DEFAULT '',
            model TEXT NOT NULL DEFAULT '',
            prompt_version TEXT NOT NULL DEFAULT '',
            generated_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_job_description_intelligence_job
            ON job_description_intelligence(canonical_job_id, generated_at DESC);
        """
    )


def _apply_phase_f_company_profiles_migration(connection: DatabaseConnection) -> None:
    """Store shared company enrichment without making it a job visibility gate."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS canonical_company_profiles (
            company_id TEXT PRIMARY KEY,
            profile_json TEXT NOT NULL DEFAULT '{}',
            logo_object_key TEXT NOT NULL DEFAULT '',
            logo_source_url TEXT NOT NULL DEFAULT '',
            logo_content_hash TEXT NOT NULL DEFAULT '',
            logo_content_type TEXT NOT NULL DEFAULT '',
            logo_verified_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_canonical_company_profiles_updated
            ON canonical_company_profiles(updated_at DESC);
        """
    )


def _apply_phase_f_company_enrichment_migration(connection: DatabaseConnection) -> None:
    """Track bounded company-target enrichment work independently of jobs."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS company_enrichment_targets (
            company_id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'pending',
            lease_owner TEXT NOT NULL DEFAULT '',
            lease_expires_at TEXT NOT NULL DEFAULT '',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            last_attempt_at TEXT NOT NULL DEFAULT '',
            last_success_at TEXT NOT NULL DEFAULT '',
            next_attempt_at TEXT NOT NULL DEFAULT '',
            last_error TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_company_enrichment_targets_due
            ON company_enrichment_targets(next_attempt_at, last_success_at, company_id);

        CREATE TABLE IF NOT EXISTS company_enrichment_attempts (
            attempt_id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL,
            cycle_key TEXT NOT NULL,
            idempotency_key TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            request_count INTEGER NOT NULL DEFAULT 0,
            cost_units REAL NOT NULL DEFAULT 0,
            fields_available INTEGER NOT NULL DEFAULT 0,
            fields_written INTEGER NOT NULL DEFAULT 0,
            logo_cached INTEGER NOT NULL DEFAULT 0,
            yield_json TEXT NOT NULL DEFAULT '{}',
            error_code TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            started_at TEXT NOT NULL,
            finished_at TEXT NOT NULL DEFAULT '',
            UNIQUE(company_id, cycle_key)
        );
        CREATE INDEX IF NOT EXISTS idx_company_enrichment_attempts_company
            ON company_enrichment_attempts(company_id, started_at DESC);
        CREATE INDEX IF NOT EXISTS idx_company_enrichment_attempts_cycle
            ON company_enrichment_attempts(cycle_key, status);
        """
    )


def _apply_phase_g_applicant_competition_migration(connection: DatabaseConnection) -> None:
    """Store source-backed applicant observations without changing catalog visibility."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS job_applicant_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            canonical_job_id TEXT NOT NULL,
            source_observation_id TEXT NOT NULL UNIQUE,
            source_ats TEXT NOT NULL DEFAULT '',
            applicant_count_exact INTEGER,
            applicant_count_min INTEGER,
            applicant_count_max INTEGER,
            applicant_count_label TEXT NOT NULL DEFAULT '',
            posting_time TEXT NOT NULL DEFAULT '',
            first_seen_at TEXT NOT NULL DEFAULT '',
            last_verified_at TEXT NOT NULL DEFAULT '',
            observed_at TEXT NOT NULL,
            apply_method TEXT NOT NULL DEFAULT '',
            easy_apply_marker INTEGER NOT NULL DEFAULT 0,
            freshness_status TEXT NOT NULL DEFAULT 'unknown',
            provenance_url TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_job_applicant_snapshots_job_time
            ON job_applicant_snapshots(canonical_job_id, observed_at DESC, snapshot_id DESC);
        CREATE INDEX IF NOT EXISTS idx_job_applicant_snapshots_source_observation
            ON job_applicant_snapshots(source_observation_id);
        """
    )


def _apply_phase_e_async_intelligence_migration(connection: DatabaseConnection) -> None:
    """Store immutable intelligence keys and work awaiting a worker."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS job_intelligence_cache (
            cache_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL DEFAULT '',
            canonical_job_id TEXT NOT NULL,
            job_version_id TEXT NOT NULL,
            profile_version_id TEXT NOT NULL DEFAULT '',
            cv_version_id TEXT NOT NULL DEFAULT '',
            evidence_version_id TEXT NOT NULL DEFAULT '',
            evaluator_version TEXT NOT NULL,
            input_hash TEXT NOT NULL,
            intelligence_kind TEXT NOT NULL,
            state TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            generated_at TEXT NOT NULL DEFAULT '',
            UNIQUE (
                user_id, canonical_job_id, job_version_id, profile_version_id,
                cv_version_id, evidence_version_id, evaluator_version, input_hash,
                intelligence_kind
            )
        );
        CREATE INDEX IF NOT EXISTS idx_job_intelligence_cache_lookup
            ON job_intelligence_cache(user_id, canonical_job_id, intelligence_kind, updated_at DESC);
        CREATE TABLE IF NOT EXISTS job_intelligence_queue (
            cache_id TEXT PRIMARY KEY,
            state TEXT NOT NULL DEFAULT 'queued',
            attempts INTEGER NOT NULL DEFAULT 0,
            requested_at TEXT NOT NULL,
            claimed_at TEXT NOT NULL DEFAULT '',
            completed_at TEXT NOT NULL DEFAULT '',
            last_error TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_job_intelligence_queue_state
            ON job_intelligence_queue(state, requested_at, cache_id);
        """
    )


def _apply_phase_g_applicant_boundary_migration(connection: DatabaseConnection) -> None:
    """Add explicit apply/provenance columns to the append-only snapshot table."""

    _ensure_table_column(connection, "job_applicant_snapshots", "apply_url", "TEXT NOT NULL DEFAULT ''")
    _ensure_table_column(connection, "job_applicant_snapshots", "source_provenance", "TEXT NOT NULL DEFAULT ''")
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_job_applicant_snapshots_observation "
        "ON job_applicant_snapshots(source_observation_id)"
    )


def _apply_admin_job_import_dashboard_migration(connection: DatabaseConnection) -> None:
    """Create durable admin import, review, publication and audit state."""

    _ensure_table_column(connection, "acquisition_publications", "previous_publication_id", "TEXT NOT NULL DEFAULT ''")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS admin_job_imports (
            import_id TEXT PRIMARY KEY,
            idempotency_key TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            requested_by TEXT NOT NULL DEFAULT '',
            source_ids_json TEXT NOT NULL DEFAULT '[]',
            scope_json TEXT NOT NULL DEFAULT '{}',
            plan_json TEXT NOT NULL DEFAULT '{}',
            cycle_id TEXT NOT NULL DEFAULT '',
            preview_publication_id TEXT NOT NULL DEFAULT '',
            publication_id TEXT NOT NULL DEFAULT '',
            error_code TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            started_at TEXT NOT NULL DEFAULT '',
            completed_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_admin_job_imports_status
            ON admin_job_imports(status, created_at DESC);

        CREATE TABLE IF NOT EXISTS admin_job_review_decisions (
            decision_id TEXT PRIMARY KEY,
            import_id TEXT NOT NULL,
            canonical_job_id TEXT NOT NULL,
            decision TEXT NOT NULL DEFAULT '',
            reason_code TEXT NOT NULL DEFAULT '',
            actor_user_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            undone_at TEXT NOT NULL DEFAULT '',
            UNIQUE(import_id, canonical_job_id)
        );
        CREATE INDEX IF NOT EXISTS idx_admin_job_review_decisions_job
            ON admin_job_review_decisions(canonical_job_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS admin_job_audit_events (
            event_id TEXT PRIMARY KEY,
            import_id TEXT NOT NULL DEFAULT '',
            actor_user_id TEXT NOT NULL DEFAULT '',
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_admin_job_audit_events_import
            ON admin_job_audit_events(import_id, created_at DESC);
        """
    )


def _apply_acquisition_quality_migration(connection: DatabaseConnection) -> None:
    """Add shared provenance, warning, reconciliation, and repair state.

    These tables are additive.  They do not alter publication gates and keep
    immutable posting history intact while allowing safe repair annotations.
    """

    for table, column, definition in (
        ("acquisition_tasks", "reconciliation_json", "TEXT NOT NULL DEFAULT '{}'"),
        ("acquisition_tasks", "quality_warnings_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("job_source_observations", "source_display_name", "TEXT NOT NULL DEFAULT ''"),
        ("job_source_observations", "source_token", "TEXT NOT NULL DEFAULT ''"),
        ("job_source_observations", "source_connector", "TEXT NOT NULL DEFAULT ''"),
        ("job_source_observations", "application_url", "TEXT NOT NULL DEFAULT ''"),
        ("job_source_observations", "application_classification", "TEXT NOT NULL DEFAULT 'unknown'"),
        ("job_source_observations", "quality_warnings_json", "TEXT NOT NULL DEFAULT '[]'"),
    ):
        _ensure_table_column(connection, table, column, definition)
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS canonical_company_aliases (
            alias_id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL,
            alias_key TEXT NOT NULL,
            alias_display TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT '',
            confidence TEXT NOT NULL DEFAULT 'verified',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(alias_key)
        );
        CREATE INDEX IF NOT EXISTS idx_canonical_company_aliases_company
            ON canonical_company_aliases(company_id, alias_key);

        CREATE TABLE IF NOT EXISTS acquisition_quality_events (
            event_id TEXT PRIMARY KEY,
            cycle_id TEXT NOT NULL DEFAULT '',
            task_id TEXT NOT NULL DEFAULT '',
            target_id TEXT NOT NULL DEFAULT '',
            canonical_job_id TEXT NOT NULL DEFAULT '',
            company_id TEXT NOT NULL DEFAULT '',
            employer_name TEXT NOT NULL DEFAULT '',
            connector TEXT NOT NULL DEFAULT '',
            source_token TEXT NOT NULL DEFAULT '',
            warning_code TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'warning',
            details_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_acquisition_quality_events_cycle
            ON acquisition_quality_events(cycle_id, warning_code, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_acquisition_quality_events_dimensions
            ON acquisition_quality_events(connector, target_id, employer_name, warning_code);

        CREATE TABLE IF NOT EXISTS acquisition_version_quality (
            version_id TEXT PRIMARY KEY,
            canonical_job_id TEXT NOT NULL,
            stable_content_hash TEXT NOT NULL DEFAULT '',
            redundant INTEGER NOT NULL DEFAULT 0,
            report_json TEXT NOT NULL DEFAULT '{}',
            calculated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_acquisition_version_quality_job
            ON acquisition_version_quality(canonical_job_id, stable_content_hash, redundant);
        """
    )


def _apply_unified_acquisition_mapping_migration(connection: DatabaseConnection) -> None:
    """Add versioned connector-independent projections and reprocessing state.

    All tables are additive.  Source observations remain the evidence layer;
    normalized outputs, provenance, quality reports, and repair runs are
    append-only or upsertable projections keyed by rule version.
    """

    for table, column, definition in (
        ("job_source_observations", "raw_payload_json", "TEXT NOT NULL DEFAULT '{}'"),
        ("job_source_observations", "raw_content_hash", "TEXT NOT NULL DEFAULT ''"),
        ("job_source_observations", "rule_version", "TEXT NOT NULL DEFAULT ''"),
        ("canonical_jobs", "published_at", "TEXT NOT NULL DEFAULT ''"),
        ("canonical_jobs", "source_updated_at", "TEXT NOT NULL DEFAULT ''"),
        ("canonical_jobs", "closed_at", "TEXT NOT NULL DEFAULT ''"),
        ("canonical_jobs", "last_reprocessed_at", "TEXT NOT NULL DEFAULT ''"),
        ("acquisition_publications", "rule_version", "TEXT NOT NULL DEFAULT ''"),
    ):
        _ensure_table_column(connection, table, column, definition)
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS acquisition_stage_results (
            stage_result_id TEXT PRIMARY KEY,
            execution_id TEXT NOT NULL,
            stage_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            rule_version TEXT NOT NULL DEFAULT '',
            started_at TEXT NOT NULL DEFAULT '',
            completed_at TEXT NOT NULL DEFAULT '',
            metrics_json TEXT NOT NULL DEFAULT '{}',
            checkpoint_json TEXT NOT NULL DEFAULT '{}',
            error_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(execution_id, stage_name)
        );
        CREATE INDEX IF NOT EXISTS idx_acquisition_stage_results_execution
            ON acquisition_stage_results(execution_id, stage_name);

        CREATE TABLE IF NOT EXISTS acquisition_rule_outputs (
            output_id TEXT PRIMARY KEY,
            execution_id TEXT NOT NULL DEFAULT '',
            entity_kind TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            source_observation_id TEXT NOT NULL DEFAULT '',
            stage_name TEXT NOT NULL,
            rule_version TEXT NOT NULL,
            semantic_hash TEXT NOT NULL DEFAULT '',
            output_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            UNIQUE(entity_kind, entity_id, source_observation_id, stage_name, rule_version)
        );
        CREATE INDEX IF NOT EXISTS idx_acquisition_rule_outputs_entity
            ON acquisition_rule_outputs(entity_kind, entity_id, stage_name, created_at DESC);

        CREATE TABLE IF NOT EXISTS acquisition_field_provenance (
            provenance_id TEXT PRIMARY KEY,
            entity_kind TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            field_name TEXT NOT NULL,
            source_observation_id TEXT NOT NULL DEFAULT '',
            raw_value_json TEXT NOT NULL DEFAULT 'null',
            normalized_value_json TEXT NOT NULL DEFAULT 'null',
            state TEXT NOT NULL DEFAULT 'unknown',
            source TEXT NOT NULL DEFAULT '',
            source_field TEXT NOT NULL DEFAULT '',
            extraction_method TEXT NOT NULL DEFAULT '',
            evidence_json TEXT NOT NULL DEFAULT 'null',
            confidence REAL NOT NULL DEFAULT 0,
            observed_at TEXT NOT NULL DEFAULT '',
            rule_version TEXT NOT NULL,
            selected INTEGER NOT NULL DEFAULT 0,
            selection_reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            UNIQUE(entity_kind, entity_id, field_name, source_observation_id, rule_version)
        );
        CREATE INDEX IF NOT EXISTS idx_acquisition_field_provenance_entity
            ON acquisition_field_provenance(entity_kind, entity_id, field_name, observed_at DESC);
        CREATE INDEX IF NOT EXISTS idx_acquisition_field_provenance_state
            ON acquisition_field_provenance(state, rule_version, observed_at DESC);

        CREATE TABLE IF NOT EXISTS acquisition_completeness_reports (
            report_id TEXT PRIMARY KEY,
            entity_kind TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            rule_version TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'unknown',
            report_json TEXT NOT NULL DEFAULT '{}',
            calculated_at TEXT NOT NULL,
            UNIQUE(entity_kind, entity_id, rule_version)
        );
        CREATE INDEX IF NOT EXISTS idx_acquisition_completeness_entity
            ON acquisition_completeness_reports(entity_kind, state, calculated_at DESC);

        CREATE TABLE IF NOT EXISTS acquisition_reprocessing_runs (
            reprocessing_id TEXT PRIMARY KEY,
            idempotency_key TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'planned',
            rule_version TEXT NOT NULL,
            environment_json TEXT NOT NULL DEFAULT '{}',
            scope_json TEXT NOT NULL DEFAULT '{}',
            plan_json TEXT NOT NULL DEFAULT '{}',
            checkpoint_json TEXT NOT NULL DEFAULT '{}',
            counts_json TEXT NOT NULL DEFAULT '{}',
            backup_json TEXT NOT NULL DEFAULT '{}',
            error_json TEXT NOT NULL DEFAULT '{}',
            started_at TEXT NOT NULL DEFAULT '',
            completed_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_acquisition_reprocessing_status
            ON acquisition_reprocessing_runs(status, created_at DESC);

        CREATE TABLE IF NOT EXISTS acquisition_duplicate_clusters (
            cluster_id TEXT PRIMARY KEY,
            state TEXT NOT NULL DEFAULT 'candidate',
            confidence REAL NOT NULL DEFAULT 0,
            reasons_json TEXT NOT NULL DEFAULT '[]',
            review_history_json TEXT NOT NULL DEFAULT '[]',
            rule_version TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS acquisition_duplicate_members (
            cluster_id TEXT NOT NULL,
            canonical_job_id TEXT NOT NULL,
            member_score REAL NOT NULL DEFAULT 0,
            member_reasons_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            PRIMARY KEY(cluster_id, canonical_job_id)
        );
        CREATE INDEX IF NOT EXISTS idx_acquisition_duplicate_members_job
            ON acquisition_duplicate_members(canonical_job_id, cluster_id);

        CREATE TABLE IF NOT EXISTS canonical_company_urls (
            company_url_id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL,
            url_type TEXT NOT NULL,
            url TEXT NOT NULL,
            canonical_url TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT '',
            source_observation_id TEXT NOT NULL DEFAULT '',
            first_seen_at TEXT NOT NULL DEFAULT '',
            last_seen_at TEXT NOT NULL DEFAULT '',
            validation_status TEXT NOT NULL DEFAULT 'not_validated',
            redirect_target TEXT NOT NULL DEFAULT '',
            selected_primary INTEGER NOT NULL DEFAULT 0,
            rule_version TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(company_id, url_type, canonical_url)
        );
        CREATE INDEX IF NOT EXISTS idx_canonical_company_urls_company
            ON canonical_company_urls(company_id, url_type, selected_primary DESC);

        CREATE TABLE IF NOT EXISTS company_logo_enrichments (
            logo_enrichment_id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            source_url TEXT NOT NULL DEFAULT '',
            object_key TEXT NOT NULL DEFAULT '',
            content_hash TEXT NOT NULL DEFAULT '',
            content_type TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'unknown',
            terms_metadata_json TEXT NOT NULL DEFAULT '{}',
            provenance_json TEXT NOT NULL DEFAULT '{}',
            observed_at TEXT NOT NULL DEFAULT '',
            rule_version TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(company_id, provider, content_hash, rule_version)
        );
        CREATE INDEX IF NOT EXISTS idx_company_logo_enrichments_company
            ON company_logo_enrichments(company_id, updated_at DESC);

        CREATE TRIGGER IF NOT EXISTS trg_job_source_observations_immutable_update
        BEFORE UPDATE ON job_source_observations
        BEGIN
            SELECT RAISE(ABORT, 'job_source_observations are immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_job_source_observations_immutable_delete
        BEFORE DELETE ON job_source_observations
        BEGIN
            SELECT RAISE(ABORT, 'job_source_observations are immutable');
        END;
        """
    )


def _apply_acquisition_reprocessing_lease_migration(connection: DatabaseConnection) -> None:
    """Add an additive owner lease for resumable reprocessing runs.

    The lease is operational metadata only.  It does not alter observations,
    posting versions, or any canonical record, and it allows a stale process
    to be reclaimed with a compare-and-swap update.
    """

    _ensure_table_column(connection, "acquisition_reprocessing_runs", "lease_token", "TEXT NOT NULL DEFAULT ''")
    _ensure_table_column(connection, "acquisition_reprocessing_runs", "lease_expires_at", "TEXT NOT NULL DEFAULT ''")
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_acquisition_reprocessing_lease
            ON acquisition_reprocessing_runs(status, lease_expires_at, updated_at)
        """
    )


def _apply_acquisition_source_quarantine_migration(connection: DatabaseConnection) -> None:
    """Persist fixture/test source quarantine without deleting evidence."""

    _ensure_table_column(connection, "acquisition_targets", "quarantined", "INTEGER NOT NULL DEFAULT 0")
    _ensure_table_column(connection, "acquisition_targets", "quarantine_reason", "TEXT NOT NULL DEFAULT ''")
    _ensure_table_column(connection, "acquisition_targets", "quarantined_at", "TEXT NOT NULL DEFAULT ''")
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_acquisition_targets_quarantine
            ON acquisition_targets(quarantined, target_kind, enabled)
        """
    )
    now = utc_now_iso()
    connection.execute(
        """
        UPDATE acquisition_targets
        SET quarantined=1,
            quarantine_reason=CASE WHEN quarantine_reason='' THEN 'fixture_or_test_target' ELSE quarantine_reason END,
            quarantined_at=CASE WHEN quarantined_at='' THEN ? ELSE quarantined_at END,
            enabled=0,
            publication_enabled=0,
            maturity_state='quarantined',
            state_transition_reason='fixture_or_test_target_quarantined',
            updated_at=?
        WHERE target_kind='fixture' OR target_id IN ('fixture_source', 'x')
        """,
        (now, now),
    )


def _apply_product_completion_wave_migration(connection: DatabaseConnection) -> None:
    """Add append-only duplicate decisions and connector capability snapshots."""

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS acquisition_duplicate_decisions (
            decision_id TEXT PRIMARY KEY,
            cluster_id TEXT NOT NULL,
            decision TEXT NOT NULL,
            actor_user_id TEXT NOT NULL DEFAULT '',
            reason TEXT NOT NULL DEFAULT '',
            evidence_json TEXT NOT NULL DEFAULT '{}',
            affected_ids_json TEXT NOT NULL DEFAULT '[]',
            rule_version TEXT NOT NULL DEFAULT '',
            supersedes_decision_id TEXT NOT NULL DEFAULT '',
            undone_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_acquisition_duplicate_decisions_cluster
            ON acquisition_duplicate_decisions(cluster_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS acquisition_connector_capability_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            connector TEXT NOT NULL,
            target_id TEXT NOT NULL DEFAULT '',
            capability_json TEXT NOT NULL DEFAULT '{}',
            raw_retention_json TEXT NOT NULL DEFAULT '{}',
            observed_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_acquisition_connector_capabilities_connector
            ON acquisition_connector_capability_snapshots(connector, target_id, observed_at DESC);
        """
    )


def _apply_posting_identity_anchor_migration(connection: DatabaseConnection) -> None:
    """Persist the immutable URL-based posting-age anchor."""

    for column, definition in (
        ("posting_anchor_at", "TEXT NOT NULL DEFAULT ''"),
        ("posting_anchor_source", "TEXT NOT NULL DEFAULT ''"),
        ("posting_anchor_precision", "TEXT NOT NULL DEFAULT ''"),
    ):
        _ensure_table_column(connection, "canonical_jobs", column, definition)
    jobs = connection.execute(
        "SELECT canonical_job_id, first_seen_at FROM canonical_jobs WHERE posting_anchor_at=''"
    ).fetchall()
    for job in jobs:
        anchor_at = str(job["first_seen_at"] or "")
        anchor_source = "first_seen_at"
        anchor_precision = "capture_timestamp"
        observation = connection.execute(
            """
            SELECT payload_json
            FROM job_source_observations
            WHERE canonical_job_id=?
            ORDER BY observed_at ASC, observation_id ASC
            LIMIT 1
            """,
            (str(job["canonical_job_id"]),),
        ).fetchone()
        if observation is not None:
            try:
                payload = json.loads(str(observation["payload_json"] or "{}"))
            except (TypeError, ValueError):
                payload = {}
            timestamps = payload.get("source_timestamps") if isinstance(payload, dict) else {}
            fields = timestamps.get("fields") if isinstance(timestamps, dict) else {}
            posted = fields.get("source_posted_at") if isinstance(fields, dict) else {}
            source_value = str(posted.get("value") or "") if isinstance(posted, dict) else ""
            if source_value:
                anchor_at = source_value
                anchor_source = "source_posted_age" if str(posted.get("state") or "").casefold() == "inferred" else "source_posted_at"
                anchor_precision = "relative_source_age" if anchor_source == "source_posted_age" else "source_timestamp"
        connection.execute(
            """
            UPDATE canonical_jobs
            SET posting_anchor_at=?, posting_anchor_source=?, posting_anchor_precision=?
            WHERE canonical_job_id=?
            """,
            (anchor_at, anchor_source, anchor_precision, str(job["canonical_job_id"])),
        )
    connection.execute(
        """
        UPDATE canonical_jobs
        SET posting_anchor_source=CASE WHEN posting_anchor_source='' THEN 'first_seen_at' ELSE posting_anchor_source END,
            posting_anchor_precision=CASE WHEN posting_anchor_precision='' THEN 'capture_timestamp' ELSE posting_anchor_precision END
        WHERE posting_anchor_source='' OR posting_anchor_precision=''
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_canonical_jobs_posting_anchor
            ON canonical_jobs(posting_anchor_at, posting_anchor_source)
        """
    )


def _apply_enrichment_foundation_migration(connection: DatabaseConnection) -> None:
    """Create inactive, provider-neutral enrichment evidence and cache state.

    These tables are additive.  They do not reference or mutate immutable source
    observations, posting versions, canonical jobs, or publication heads.
    """

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS enrichment_evidence (
            evidence_id TEXT PRIMARY KEY,
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            field_path TEXT NOT NULL,
            input_fingerprint TEXT NOT NULL,
            raw_value_json TEXT NOT NULL DEFAULT 'null',
            raw_evidence_excerpt TEXT NOT NULL DEFAULT '',
            raw_storage_permitted INTEGER NOT NULL DEFAULT 0,
            normalized_candidate_json TEXT NOT NULL DEFAULT 'null',
            candidate_id TEXT NOT NULL DEFAULT '',
            provider_id TEXT NOT NULL DEFAULT '',
            adapter_version TEXT NOT NULL DEFAULT '',
            dataset_version TEXT NOT NULL DEFAULT '',
            snapshot_version TEXT NOT NULL DEFAULT '',
            source_uri TEXT NOT NULL DEFAULT '',
            source_record_id TEXT NOT NULL DEFAULT '',
            source_field TEXT NOT NULL DEFAULT '',
            extraction_method TEXT NOT NULL DEFAULT '',
            observed_at TEXT NOT NULL DEFAULT '',
            retrieved_at TEXT NOT NULL DEFAULT '',
            licence_id TEXT NOT NULL DEFAULT '',
            licence_url TEXT NOT NULL DEFAULT '',
            attribution TEXT NOT NULL DEFAULT '',
            terms_url TEXT NOT NULL DEFAULT '',
            privacy_class TEXT NOT NULL DEFAULT '',
            retention_class TEXT NOT NULL DEFAULT '',
            content_hash TEXT NOT NULL DEFAULT '',
            rule_version TEXT NOT NULL DEFAULT '',
            model_version TEXT NOT NULL DEFAULT '',
            prompt_version TEXT NOT NULL DEFAULT '',
            provider_score REAL,
            calibrated_confidence REAL,
            result_state TEXT NOT NULL,
            selected INTEGER NOT NULL DEFAULT 0,
            conflict_group TEXT NOT NULL DEFAULT '',
            reviewer_decision TEXT NOT NULL DEFAULT '',
            reviewer_reason TEXT NOT NULL DEFAULT '',
            reviewer_id TEXT NOT NULL DEFAULT '',
            reviewed_at TEXT NOT NULL DEFAULT '',
            superseded_evidence_id TEXT NOT NULL DEFAULT '',
            request_count INTEGER NOT NULL DEFAULT 0,
            latency_ms REAL NOT NULL DEFAULT 0,
            cost_units REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_enrichment_evidence_target
            ON enrichment_evidence(target_type, target_id, field_path, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_enrichment_evidence_fingerprint
            ON enrichment_evidence(input_fingerprint, provider_id, rule_version, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_enrichment_evidence_state
            ON enrichment_evidence(result_state, selected, created_at DESC);

        CREATE TRIGGER IF NOT EXISTS trg_enrichment_evidence_immutable_update
        BEFORE UPDATE ON enrichment_evidence
        BEGIN
            SELECT RAISE(ABORT, 'enrichment_evidence is append-only');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_enrichment_evidence_immutable_delete
        BEFORE DELETE ON enrichment_evidence
        BEGIN
            SELECT RAISE(ABORT, 'enrichment_evidence is append-only');
        END;

        CREATE TABLE IF NOT EXISTS enrichment_version_registry (
            version_id TEXT PRIMARY KEY,
            version_kind TEXT NOT NULL,
            version_key TEXT NOT NULL,
            version_value TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 0,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            activated_at TEXT NOT NULL DEFAULT '',
            deactivated_at TEXT NOT NULL DEFAULT '',
            UNIQUE(version_kind, version_key, version_value)
        );
        CREATE INDEX IF NOT EXISTS idx_enrichment_versions_active
            ON enrichment_version_registry(version_kind, version_key, is_active, created_at DESC);

        CREATE TABLE IF NOT EXISTS enrichment_cache_entries (
            cache_key TEXT PRIMARY KEY,
            input_fingerprint TEXT NOT NULL,
            provider_id TEXT NOT NULL,
            adapter_version TEXT NOT NULL DEFAULT '',
            dataset_version TEXT NOT NULL DEFAULT '',
            rule_version TEXT NOT NULL DEFAULT '',
            policy_version TEXT NOT NULL DEFAULT '',
            result_state TEXT NOT NULL,
            result_json TEXT NOT NULL DEFAULT '{}',
            raw_storage_permitted INTEGER NOT NULL DEFAULT 0,
            observed_at TEXT NOT NULL DEFAULT '',
            retrieved_at TEXT NOT NULL DEFAULT '',
            expires_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_enrichment_cache_expiry
            ON enrichment_cache_entries(expires_at, provider_id, result_state);
        CREATE INDEX IF NOT EXISTS idx_enrichment_cache_input
            ON enrichment_cache_entries(input_fingerprint, provider_id, rule_version, policy_version);
        """
    )

def _apply_company_identity_reconciliation_migration(connection: DatabaseConnection) -> None:
    """Add explicit company identity, URL lifecycle, and review evidence.

    The company table is rebuilt only to remove its legacy name-based unique
    constraint. All existing rows are copied; immutable source evidence is not
    removed or rewritten.
    """

    if _table_columns(connection, "canonical_companies"):
        connection.execute("ALTER TABLE canonical_companies RENAME TO canonical_companies_identity_legacy")
        connection.executescript(
            """
            CREATE TABLE canonical_companies (
                company_id TEXT PRIMARY KEY,
                canonical_name TEXT NOT NULL,
                entity_kind TEXT NOT NULL DEFAULT 'employer'
                    CHECK (entity_kind IN ('employer', 'source', 'fixture', 'quarantined', 'unknown')),
                provenance_url TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            INSERT INTO canonical_companies (
                company_id, canonical_name, entity_kind, provenance_url, created_at, updated_at
            )
            SELECT company_id, canonical_name,
                   CASE entity_kind
                       WHEN 'source' THEN 'source'
                       WHEN 'fixture' THEN 'fixture'
                       WHEN 'quarantined' THEN 'quarantined'
                       WHEN 'unknown' THEN 'unknown'
                       ELSE 'employer'
                   END,
                   provenance_url, created_at, updated_at
            FROM canonical_companies_identity_legacy;
            DROP TABLE canonical_companies_identity_legacy;
            """
        )

    for table, column, definition in (
        ("canonical_company_profiles", "profile_status", "TEXT NOT NULL DEFAULT 'absent'"),
        ("canonical_company_urls", "url_lifecycle", "TEXT NOT NULL DEFAULT 'discovered'"),
        ("canonical_company_urls", "validation_reason", "TEXT NOT NULL DEFAULT ''"),
        ("canonical_company_urls", "ignored_reason", "TEXT NOT NULL DEFAULT ''"),
        ("canonical_company_urls", "occurrence_count", "INTEGER NOT NULL DEFAULT 1"),
        ("canonical_company_urls", "source_target_id", "TEXT NOT NULL DEFAULT ''"),
    ):
        _ensure_table_column(connection, table, column, definition)

    connection.execute(
        """
        UPDATE canonical_company_urls
        SET url_type=CASE url_type
                WHEN 'ats_board' THEN 'ats_jobs'
                WHEN 'application_host' THEN 'ats_jobs'
                WHEN 'employer_jobs' THEN 'careers'
                WHEN 'social_profile' THEN 'other'
                WHEN 'enrichment' THEN 'other'
                ELSE url_type
            END,
            url_lifecycle=CASE
                WHEN validation_status IN ('invalid', 'blocked') THEN 'invalid'
                WHEN validation_status IN ('valid', 'validated', 'verified') THEN 'validated'
                WHEN validation_status='configured_official' THEN 'configured_official'
                ELSE 'discovered'
            END
        """
    )
    connection.execute(
        """
        UPDATE canonical_company_profiles
        SET profile_status=CASE
            WHEN profile_json IS NULL OR profile_json='' OR profile_json='{}' THEN 'absent'
            WHEN profile_json LIKE '%conflicted%' THEN 'conflicted'
            WHEN profile_json LIKE '%known%' THEN 'incomplete'
            ELSE 'absent'
        END
        """
    )
    connection.execute(
        """
        UPDATE canonical_companies
        SET entity_kind=CASE
            WHEN EXISTS (
                SELECT 1
                FROM canonical_jobs j
                JOIN job_source_observations o ON o.canonical_job_id=j.canonical_job_id
                JOIN acquisition_targets t ON t.target_id=o.target_id
                WHERE j.company_id=canonical_companies.company_id
                  AND (t.target_kind='fixture' OR t.quarantined=1)
            ) THEN CASE WHEN EXISTS (
                SELECT 1
                FROM canonical_jobs j
                JOIN job_source_observations o ON o.canonical_job_id=j.canonical_job_id
                JOIN acquisition_targets t ON t.target_id=o.target_id
                WHERE j.company_id=canonical_companies.company_id AND t.target_kind='fixture'
            ) THEN 'fixture' ELSE 'quarantined' END
            WHEN entity_kind IN ('fixture', 'quarantined', 'source') THEN entity_kind
            ELSE 'employer'
        END,
            updated_at=updated_at
        WHERE EXISTS (
            SELECT 1
            FROM canonical_jobs j
            JOIN job_source_observations o ON o.canonical_job_id=j.canonical_job_id
            JOIN acquisition_targets t ON t.target_id=o.target_id
            WHERE j.company_id=canonical_companies.company_id
        )
        """
    )
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS company_identity_keys (
            identity_key TEXT PRIMARY KEY,
            company_id TEXT NOT NULL,
            identity_type TEXT NOT NULL DEFAULT 'external',
            source TEXT NOT NULL DEFAULT '',
            evidence_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_company_identity_keys_company
            ON company_identity_keys(company_id, identity_type);

        CREATE TABLE IF NOT EXISTS company_identity_evidence (
            evidence_id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL DEFAULT '',
            observed_name TEXT NOT NULL DEFAULT '',
            normalized_name TEXT NOT NULL DEFAULT '',
            identity_key TEXT NOT NULL DEFAULT '',
            target_id TEXT NOT NULL DEFAULT '',
            source_observation_id TEXT NOT NULL DEFAULT '',
            evidence_type TEXT NOT NULL DEFAULT 'source_observation',
            evidence_url TEXT NOT NULL DEFAULT '',
            evidence_json TEXT NOT NULL DEFAULT '{}',
            confidence REAL NOT NULL DEFAULT 0,
            link_state TEXT NOT NULL DEFAULT 'needs_review',
            review_required INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_company_identity_evidence_company
            ON company_identity_evidence(company_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_company_identity_evidence_review
            ON company_identity_evidence(link_state, review_required, created_at DESC);

        CREATE TABLE IF NOT EXISTS company_link_candidates (
            candidate_id TEXT PRIMARY KEY,
            observed_name TEXT NOT NULL DEFAULT '',
            normalized_name TEXT NOT NULL DEFAULT '',
            candidate_company_id TEXT NOT NULL DEFAULT '',
            target_id TEXT NOT NULL DEFAULT '',
            source_observation_id TEXT NOT NULL DEFAULT '',
            decision TEXT NOT NULL DEFAULT 'needs_review',
            confidence REAL NOT NULL DEFAULT 0,
            review_required INTEGER NOT NULL DEFAULT 1,
            evidence_json TEXT NOT NULL DEFAULT '{}',
            reason TEXT NOT NULL DEFAULT '',
            reviewer_id TEXT NOT NULL DEFAULT '',
            reviewed_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_company_link_candidates_review
            ON company_link_candidates(decision, review_required, created_at DESC);

        CREATE TABLE IF NOT EXISTS canonical_company_url_occurrences (
            occurrence_id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL DEFAULT '',
            url_type TEXT NOT NULL,
            url TEXT NOT NULL DEFAULT '',
            canonical_url TEXT NOT NULL DEFAULT '',
            url_lifecycle TEXT NOT NULL DEFAULT 'discovered',
            source TEXT NOT NULL DEFAULT '',
            source_observation_id TEXT NOT NULL DEFAULT '',
            target_id TEXT NOT NULL DEFAULT '',
            import_id TEXT NOT NULL DEFAULT '',
            checked_in_path TEXT NOT NULL DEFAULT '',
            persisted_company_url_id TEXT NOT NULL DEFAULT '',
            evidence_json TEXT NOT NULL DEFAULT '{}',
            validation_reason TEXT NOT NULL DEFAULT '',
            ignored_reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_company_url_occurrences_lookup
            ON canonical_company_url_occurrences(company_id, url_type, canonical_url, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_company_url_occurrences_lifecycle
            ON canonical_company_url_occurrences(url_lifecycle, created_at DESC);

        CREATE TRIGGER IF NOT EXISTS trg_company_identity_evidence_immutable_update
        BEFORE UPDATE ON company_identity_evidence
        BEGIN
            SELECT RAISE(ABORT, 'company_identity_evidence is append-only');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_company_identity_evidence_immutable_delete
        BEFORE DELETE ON company_identity_evidence
        BEGIN
            SELECT RAISE(ABORT, 'company_identity_evidence is append-only');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_company_url_occurrences_immutable_update
        BEFORE UPDATE ON canonical_company_url_occurrences
        BEGIN
            SELECT RAISE(ABORT, 'canonical_company_url_occurrences are append-only');
        END;
        CREATE TRIGGER IF NOT EXISTS trg_company_url_occurrences_immutable_delete
        BEFORE DELETE ON canonical_company_url_occurrences
        BEGIN
            SELECT RAISE(ABORT, 'canonical_company_url_occurrences are append-only');
        END;
        """
    )
    now = utc_now_iso()
    for row in connection.execute("SELECT company_id FROM canonical_companies").fetchall():
        company_id = str(row["company_id"] or "")
        connection.execute(
            """
            INSERT OR IGNORE INTO company_identity_keys (
                identity_key, company_id, identity_type, source, evidence_json, created_at, updated_at
            ) VALUES (?, ?, 'legacy_company_id', 'migration', '{}', ?, ?)
            """,
            (f"legacy-company:{company_id}", company_id, now, now),
        )


MIGRATIONS = (
    Migration.from_callable(
        "001_runtime_normalization",
        "Normalize run runtime fields and create runtime tables.",
        _apply_runtime_migration,
        dependencies=(_table_columns, _ensure_run_column),
    ),
    Migration.from_callable(
        "002_analytics_events",
        "Create analytics event storage and indexes.",
        _apply_analytics_events_migration,
    ),
    Migration.from_callable(
        "003_application_status_history",
        "Create application status history storage and indexes.",
        _apply_application_status_history_migration,
    ),
    Migration.from_callable(
        "004_runs_user_id",
        "Add and backfill the normalized run user ID.",
        _apply_run_user_id_migration,
        dependencies=(_table_columns, _ensure_run_column),
    ),
    Migration.from_callable(
        "005_billing",
        "Create billing, subscription, and quota storage.",
        _apply_billing_migration,
        dependencies=(_table_columns, _ensure_user_column),
    ),
    Migration.from_callable(
        "006_app_config",
        "Create application configuration storage.",
        _apply_app_config_migration,
    ),
    Migration.from_callable(
        "007_scrapeops_usage_ledger",
        "Create the ScrapeOps usage ledger.",
        _apply_scrapeops_usage_ledger_migration,
    ),
    Migration.from_callable(
        "008_site_source_policy",
        "Create site source policy storage.",
        _apply_site_source_policy_migration,
    ),
    Migration.from_callable(
        "009_site_job_url_history",
        "Create public job URL history storage.",
        _apply_site_job_url_history_migration,
    ),
    Migration.from_callable(
        "010_site_job_url_history_workspace_scope",
        "Preserve site job URL history lookup indexes.",
        _apply_site_job_url_history_workspace_scope_migration,
    ),
    Migration.from_callable(
        "011_site_job_url_history_public_index",
        "Normalize site job URL history to a public URL index.",
        _apply_site_job_url_history_public_index_migration,
        dependencies=(_apply_site_job_url_history_migration,),
    ),
    Migration.from_callable(
        "012_creem_billing",
        "Add Creem billing provider identifiers.",
        _apply_creem_billing_migration,
        dependencies=(_table_columns, _ensure_table_column),
    ),
    Migration.from_callable(
        "013_candidate_document_normalization",
        "Normalize candidate assets and private document text out of aggregate JSON payloads.",
        _apply_candidate_document_normalization_migration,
        dependencies=(
            _upsert_candidate_asset,
            _upsert_candidate_document,
            prepare_user_payload,
            prepare_workspace_payload,
            prepare_run_payload,
        ),
    ),
    Migration.from_callable(
        "014_workspace_ownership",
        "Add workspace ownership and safely backfill legacy workspaces.",
        _apply_workspace_ownership_migration,
        dependencies=(_table_columns, _ensure_table_column),
    ),
    Migration.from_callable(
        "015_email_sync_start_date",
        "Add email sync start date, status, and scheduling columns. Remove scan_depth.",
        _apply_email_sync_start_date_migration,
        dependencies=(_table_columns, _ensure_user_column),
    ),
    Migration.from_callable(
        "016_assisted_apply_connections",
        "Create one-time Assisted Apply connection and extension session storage.",
        _apply_assisted_apply_connections_migration,
    ),
    Migration.from_callable(
        "017_application_packages",
        "Create immutable application package storage for Assisted Apply.",
        _apply_application_packages_migration,
    ),
    Migration.from_callable(
        "018_assisted_apply_corrections",
        "Create scoped, auditable Assisted Apply correction storage.",
        _apply_assisted_apply_corrections_migration,
    ),
    Migration.from_callable(
        "019_assisted_apply_document_grants",
        "Create one-time, session-bound Assisted Apply document grants and audit records.",
        _apply_assisted_apply_document_grants_migration,
    ),
    Migration.from_callable(
        "020_assisted_apply_tracker_confirmation",
        "Create bounded Assisted Apply outcome events and idempotent Tracker records.",
        _apply_assisted_apply_tracker_confirmation_migration,
    ),
    Migration.from_callable(
        "021_career_profiles",
        "Create career profile storage for career profile lifecycle management.",
        _apply_career_profiles_migration,
    ),
    Migration.from_callable(
        "022_career_profiles_workspace_binding",
        "Add workspace binding column to career profiles.",
        _apply_career_profiles_workspace_binding_migration,
    ),
    Migration.from_callable(
        "023_career_profiles_baseline_cv",
        "Add baseline CV fields to career profiles.",
        _apply_career_profiles_baseline_cv_migration,
    ),
    Migration.from_callable(
        "024_evidence_state_tracking",
        "Create evidence and evidence state history tables for CP-028 state visibility.",
        _apply_evidence_storage_migration,
    ),
    Migration.from_callable(
        "025_work_experiences",
        "Create work experience records and merge suggestion storage.",
        _apply_work_experiences_migration,
    ),
    Migration.from_callable(
        "026_profile_versioning",
        "Create profile version, CV version, and generation provenance tables (CP-025).",
        _apply_profile_versioning_migration,
    ),
    Migration.from_callable(
        "027_assisted_apply_preparations",
        "Create disabled-by-default durable Assisted Apply preparation state and sanitized report idempotency storage.",
        _apply_assisted_apply_preparations_migration,
    ),
    Migration.from_callable(
        "028_assisted_apply_document_grant_intents",
        "Bind one-time document grants to adapter-declared upload field intents.",
        _apply_assisted_apply_document_grant_intents_migration,
    ),
    Migration.from_callable(
        "029_phase_a_acquisition",
        "Create system-owned Phase A acquisition, canonical catalog, and publication storage.",
        _apply_phase_a_acquisition_migration,
    ),
    Migration.from_callable(
        "030_phase_a_publication_head",
        "Create the singleton valid-publication head for the Phase A catalog.",
        _apply_phase_a_publication_head_migration,
    ),
    Migration.from_callable(
        "031_phase_a_published_jobs",
        "Add per-target published-job counts to Phase A acquisition tasks.",
        _apply_phase_a_published_jobs_migration,
        dependencies=(_table_columns, _ensure_table_column),
    ),
    Migration.from_callable(
        "032_phase_a_request_state",
        "Add write-ahead dispatch and uncertain-outcome request metadata.",
        _apply_phase_a_request_state_migration,
        dependencies=(_table_columns, _ensure_table_column),
    ),
    Migration.from_callable(
        "033_phase_b_catalog",
        "Add durable Phase B normalization rejection evidence.",
        _apply_phase_b_catalog_migration,
    ),
    Migration.from_callable(
        "034_phase_c_personalized_jobs",
        "Create user-scoped personalized jobs state and evaluation storage.",
        _apply_phase_c_personalized_jobs_migration,
    ),
    Migration.from_callable(
        "035_phase_e_job_intelligence",
        "Cache version-keyed job summaries and structured descriptions.",
        _apply_phase_e_job_intelligence_migration,
    ),
    Migration.from_callable(
        "036_phase_f_company_profiles",
        "Store provenance-aware canonical company enrichment and logo metadata.",
        _apply_phase_f_company_profiles_migration,
    ),
    Migration.from_callable(
        "037_phase_g_applicant_competition",
        "Store source-backed applicant competition snapshots and freshness metadata.",
        _apply_phase_g_applicant_competition_migration,
    ),
    Migration.from_callable(
        "038_phase_e_async_intelligence",
        "Add immutable intelligence cache keys and asynchronous precompute work.",
        _apply_phase_e_async_intelligence_migration,
    ),
    Migration.from_callable(
        "039_phase_b_catalog_correctness",
        "Add source-scoped catalog identity, lifecycle, replay, and immutable-version contracts.",
        _apply_phase_b_catalog_correctness_migration,
        dependencies=(_table_columns, _ensure_table_column),
    ),
    Migration.from_callable(
        "040_phase_f_company_enrichment",
        "Track bounded, idempotent company-target enrichment attempts and yield.",
        _apply_phase_f_company_enrichment_migration,
    ),
    Migration.from_callable(
        "041_phase_g_applicant_boundary",
        "Add explicit official-apply and internal-provenance fields for inactive applicant snapshots.",
        _apply_phase_g_applicant_boundary_migration,
        dependencies=(_table_columns, _ensure_table_column),
    ),
    Migration.from_callable(
        "042_admin_job_import_dashboard",
        "Create durable admin job import, review, publication and audit state.",
        _apply_admin_job_import_dashboard_migration,
        dependencies=(_table_columns, _ensure_table_column),
    ),
    Migration.from_callable(
        "043_acquisition_quality_contract",
        "Add shared acquisition quality, provenance, reconciliation, and repair annotations.",
        _apply_acquisition_quality_migration,
        dependencies=(_table_columns, _ensure_table_column),
    ),
    Migration.from_callable(
        "044_unified_acquisition_mapping",
        "Add connector-independent mapping, provenance, enrichment, duplicate, and resumable reprocessing state.",
        _apply_unified_acquisition_mapping_migration,
        dependencies=(_table_columns, _ensure_table_column),
    ),
    Migration.from_callable(
        "045_acquisition_reprocessing_leases",
        "Add compare-and-swap ownership leases for resumable acquisition reprocessing.",
        _apply_acquisition_reprocessing_lease_migration,
        dependencies=(_table_columns, _ensure_table_column),
    ),
    Migration.from_callable(
        "046_acquisition_source_quarantine",
        "Persist fixture/test source quarantine without deleting immutable acquisition evidence.",
        _apply_acquisition_source_quarantine_migration,
        dependencies=(_table_columns, _ensure_table_column),
    ),
    Migration.from_callable(
        "047_product_completion_wave",
        "Add append-only duplicate decision history and connector capability snapshots.",
        _apply_product_completion_wave_migration,
    ),
    Migration.from_callable(
        "048_posting_identity_anchor",
        "Persist URL-based identity and immutable first-observed posting-age anchors.",
        _apply_posting_identity_anchor_migration,
        dependencies=(_table_columns, _ensure_table_column),
    ),
    Migration.from_callable(
        "049_enrichment_foundation",
        "Create inactive provider-neutral enrichment evidence, version, and cache state.",
        _apply_enrichment_foundation_migration,
    ),
    Migration.from_callable(
        "054_company_identity_reconciliation",
        "Add explicit company entity kinds, profile status, URL lifecycle/type evidence, and read-only reconciliation state.",
        _apply_company_identity_reconciliation_migration,
        dependencies=(_table_columns, _ensure_table_column),
    ),
)
