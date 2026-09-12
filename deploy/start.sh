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
python_bin="${RUNR_PYTHON_BIN:-$PROJECT_DIR/.venv/bin/python}"
if [ ! -x "$python_bin" ]; then
  echo "Missing required project interpreter: $python_bin" >&2
  exit 1
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
      --host "${RUNR_API_HOST:-0.0.0.0}" \
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
  acquisition)
    # Dedicated VPS acquisition entrypoint. The role is pinned to acquisition
    # so the Render customer worker cannot claim acquisition cycles.
    emit_release_metadata worker acquisition
    exec "$python_bin" workspace_runner.py \
      --data-dir "$data_dir" \
      --storage "$storage_backend" \
      --log-level "$log_level" \
      run-worker \
      --worker-id "${WORKER_ID:-vps_acquisition_worker}" \
      --worker-role acquisition \
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
    echo "Supported roles: api, worker, acquisition, process-next, migrate" >&2
    exit 64
    ;;
esac
