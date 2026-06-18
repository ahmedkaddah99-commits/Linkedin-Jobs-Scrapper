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

case "$role" in
  api)
    exec python workspace_runner.py \
      --data-dir "$data_dir" \
      --storage "$storage_backend" \
      --log-level "$log_level" \
      serve-api \
      --host 0.0.0.0 \
      --port "${PORT:-8000}" \
      "$@"
    ;;
  worker)
    exec python workspace_runner.py \
      --data-dir "$data_dir" \
      --storage "$storage_backend" \
      --log-level "$log_level" \
      run-worker \
      --worker-id "${WORKER_ID:-render_worker}" \
      "$@"
    ;;
  process-next)
    exec python workspace_runner.py \
      --data-dir "$data_dir" \
      --storage "$storage_backend" \
      --log-level "$log_level" \
      process-next \
      --worker-id "${WORKER_ID:-render_cron}" \
      "$@"
    ;;
  migrate)
    exec python -m backend.database.migrate "$@"
    ;;
  *)
    echo "Unknown role: $role" >&2
    echo "Supported roles: api, worker, process-next, migrate" >&2
    exit 64
    ;;
esac
