#!/usr/bin/env sh
set -eu

PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$PROJECT_DIR"

role="${1:-api}"
if [ "$#" -gt 0 ]; then
  shift
fi

data_dir="${RUNR_DATA_DIR:-.backend_data}"
storage_backend="${RUNR_STORAGE_BACKEND:-sqlite}"
log_level="${RUNR_LOG_LEVEL:-INFO}"
python_bin="${RUNR_PYTHON_BIN:-}"
if [ -z "$python_bin" ] && [ -x "$PROJECT_DIR/.venv/bin/python" ]; then
  python_bin="$PROJECT_DIR/.venv/bin/python"
fi
if [ -z "$python_bin" ]; then
  python_bin="python"
fi

emit_release_metadata() {
  service="$1"
  worker_role="${2:-}"
  "$python_bin" -m backend.deployment.release_contract \
    --service "$service" \
    --worker-role "$worker_role"
}

case "$role" in
  api)
    emit_release_metadata api
    exec "$python_bin" workspace_runner.py \
      --data-dir "$data_dir" \
      --storage "$storage_backend" \
      --log-level "$log_level" \
      serve-api \
      --host 0.0.0.0 \
      --port "${PORT:-8000}" \
      "$@"
    ;;
  worker)
    emit_release_metadata worker "${WORKER_ROLE:-customer}"
    exec "$python_bin" workspace_runner.py \
      --data-dir "$data_dir" \
      --storage "$storage_backend" \
      --log-level "$log_level" \
      run-worker \
      --worker-id "${WORKER_ID:-render_worker}" \
      --worker-role "${WORKER_ROLE:-customer}" \
      "$@"
    ;;
  process-next)
    emit_release_metadata worker "${WORKER_ROLE:-customer}"
    exec "$python_bin" workspace_runner.py \
      --data-dir "$data_dir" \
      --storage "$storage_backend" \
      --log-level "$log_level" \
      process-next \
      --worker-id "${WORKER_ID:-render_cron}" \
      --worker-role "${WORKER_ROLE:-customer}" \
      "$@"
    ;;
  migrate)
    emit_release_metadata api
    exec "$python_bin" -m backend.database.migrate "$@"
    ;;
  *)
    echo "Unknown role: $role" >&2
    echo "Supported roles: api, worker, process-next, migrate" >&2
    exit 64
    ;;
esac
