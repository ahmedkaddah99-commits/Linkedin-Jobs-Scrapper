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


    Migration.from_callable(
        "025_work_experiences",
        "Create work experience records and merge suggestion storage.",
        _apply_work_experiences_migration,
    ),


)
# End of MIGRATIONS tuple
# End of MIGRATIONS tuple



# (trailing cleanup)




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

