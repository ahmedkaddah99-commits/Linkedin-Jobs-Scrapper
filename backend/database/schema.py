BASE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_id TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL,
    checksum TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS workflow_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    workflow_template_id TEXT NOT NULL,
    workspace_type TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(workflow_template_id) REFERENCES workflow_templates(id)
);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    workflow_template_id TEXT NOT NULL,
    status TEXT NOT NULL,
    requested_by TEXT NOT NULL DEFAULT '',
    user_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    queued_at TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL DEFAULT '',
    finished_at TEXT NOT NULL DEFAULT '',
    current_stage_id TEXT NOT NULL DEFAULT '',
    last_error TEXT NOT NULL DEFAULT '',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 1,
    run_input_overrides_json TEXT NOT NULL DEFAULT '{}',
    run_plan_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS run_job_sets (
    run_id TEXT NOT NULL,
    set_key TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (run_id, set_key)
);
CREATE TABLE IF NOT EXISTS run_blobs (
    run_id TEXT NOT NULL,
    blob_key TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (run_id, blob_key)
);
CREATE TABLE IF NOT EXISTS artifacts (
    run_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    path TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (run_id, artifact_id)
);
CREATE TABLE IF NOT EXISTS reviews (
    review_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    status TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS application_status_history (
    review_id TEXT,
    user_id TEXT,
    from_status TEXT,
    to_status TEXT,
    changed_at TEXT,
    source TEXT
);
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL,
    is_active INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
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
CREATE TABLE IF NOT EXISTS api_tokens (
    token_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    token_prefix TEXT NOT NULL,
    is_active INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS secrets (
    secret_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_updated_at ON runs(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_status_updated_at ON runs(status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_workspace_updated_at ON runs(workspace_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_workspaces_template_id ON workspaces(workflow_template_id);
CREATE INDEX IF NOT EXISTS idx_reviews_run_updated_at ON reviews(run_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_application_status_history_review_changed_at
    ON application_status_history(review_id, changed_at);
CREATE INDEX IF NOT EXISTS idx_application_status_history_user_changed_at
    ON application_status_history(user_id, changed_at);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
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
CREATE INDEX IF NOT EXISTS idx_api_tokens_user_id ON api_tokens(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_api_tokens_prefix_active
    ON api_tokens(token_prefix, is_active, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_secrets_workspace_id ON secrets(workspace_id, updated_at DESC);
"""
