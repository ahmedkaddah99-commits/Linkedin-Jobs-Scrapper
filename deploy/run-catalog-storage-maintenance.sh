#!/usr/bin/env sh
set -eu
project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$project_dir"
python_bin="${RUNR_PYTHON_BIN:-$project_dir/.venv/bin/python}"
state_root="${RUNR_ACQUISITION_STATE_ROOT:-/srv/runr/state}"
lock_root="${RUNR_ACQUISITION_LOCK_ROOT:-$state_root/locks}"
receipt_root="${RUNR_ACQUISITION_RECEIPT_ROOT:-/srv/runr/exports/receipts}"
mkdir -p "$lock_root" "$receipt_root"
# Use the publisher's existing lock: a release and its maintenance job cannot
# race to replace/delete publication headers. SQLite also rechecks pins in txn.
exec 9>"$lock_root/publisher.lock"
if ! flock -n 9; then
  echo 'Catalog publisher or maintenance already running' >&2
  exit 75
fi
receipt="$receipt_root/catalog-storage-maintenance-latest.json"
temporary="$(mktemp "$receipt_root/catalog-storage-maintenance-XXXXXXXX")"
history_temporary="$(mktemp "$receipt_root/catalog-history-pruning-XXXXXXXX")"
trap 'rm -f -- "$temporary" "$history_temporary"' EXIT
history_status=0
"$python_bin" scripts/prune_catalog_history.py --apply \
  --checkpoint "$state_root/catalog-history-pruning/checkpoint.json" \
  --batch-size "${RUNR_CATALOG_HISTORY_BATCH_SIZE:-10000}" \
  --max-seconds "${RUNR_CATALOG_HISTORY_MAX_SECONDS:-120}" > "$history_temporary" || history_status=$?
mv -- "$history_temporary" "$receipt_root/catalog-history-pruning-latest.jsonl"
if [ "$history_status" -ne 0 ]; then
  echo "History pruning failed ($history_status); continuing other retention phases" >&2
fi
"$python_bin" scripts/maintain_catalog_storage.py --apply \
  --data-dir "${RUNR_DATA_DIR:-/var/lib/runr/acquisition-data}" \
  --batch-size "${RUNR_CATALOG_STORAGE_BATCH_SIZE:-1000}" \
  --max-seconds "${RUNR_CATALOG_STORAGE_MAX_SECONDS:-300}" \
  --metrics-file "${RUNR_CATALOG_STORAGE_METRICS_FILE:-/var/lib/runr/observability/catalog-storage.prom}" \
  --max-batches "${RUNR_CATALOG_STORAGE_MAX_BATCHES:-1000}" > "$temporary"
mv -- "$temporary" "$receipt"
cat "$receipt"
exit "$history_status"
