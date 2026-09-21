#!/usr/bin/env sh
set -eu

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$project_dir"
python_bin="${RUNR_PYTHON_BIN:-$project_dir/.venv/bin/python}"
manifest="${RUNR_ACQUISITION_MANIFEST:-/srv/runr/shared/inputs/SOURCE_ELIGIBILITY_MANIFEST_RC005_RECONCILED.json}"
state_root="${RUNR_ACQUISITION_STATE_ROOT:-/srv/runr/state}"
linkedin_state_db="${RUNR_LINKEDIN_STATE_DB:-$state_root/linkedin/master_linkedin_jobs_state.db}"
employer_state_db="${RUNR_EMPLOYER_STATE_DB:-$state_root/employer/master_employer_jobs_state.db}"
data_dir="${RUNR_DATA_DIR:-/var/lib/runr/acquisition-data}"
export_root="${RUNR_ACQUISITION_EXPORT_ROOT:-/srv/runr/exports}"
receipt_root="${RUNR_ACQUISITION_RECEIPT_ROOT:-$export_root/receipts}"
lock_root="${RUNR_ACQUISITION_LOCK_ROOT:-$state_root/locks}"
run_timeout="${RUNR_PUBLISHER_RUN_TIMEOUT_SECONDS:-900}"

# Ownership: this wrapper is invoked only by the publisher timer. It holds
# the publisher lock and both source locks, so an overlapping collector exits
# 75 and the timer skips that occurrence. timeout 900 returns 124 and the
# receipt records the failed publication.

case "$run_timeout" in
  ''|*[!0-9]*|0)
    echo "Publisher run timeout must be a positive integer: $run_timeout" >&2
    exit 64
    ;;
esac

mkdir -p "$receipt_root" "$lock_root"
exec 9>"$lock_root/publisher.lock"

emit_telemetry() {
  reason="$1"
  code="$2"
  started="${3:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
  finished="${4:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
  commit="$(printf %s "${RUNR_SOURCE_VERSION:-${RUNR_RELEASE_COMMIT:-}}" | tr -d '"\\')"
  printf '{"schema_version":"runr.producer.telemetry.v1","source":"publisher","reason_code":"%s","exit_code":%s,"started_at":"%s","finished_at":"%s","release_commit":"%s"}\n' \
    "$reason" "$code" "$started" "$finished" "$commit" \
    > "$receipt_root/publisher-latest-telemetry.json"
  cat "$receipt_root/publisher-latest-telemetry.json"
}

if ! flock -n 9; then
  echo "producer-state publisher is already running" >&2
  emit_telemetry lock_overlap 75
  exit 75
fi
# Read the two producer databases under the same locks used by their
# collectors. This is the source barrier that makes an incremental snapshot
# consistent without copying or replaying the full catalogs.
exec 7>"$lock_root/linkedin.lock"
if ! flock -n 7; then
  echo "linkedin acquisition is running; publisher will retry" >&2
  emit_telemetry lock_overlap 75
  exit 75
fi
exec 8>"$lock_root/employer.lock"
if ! flock -n 8; then
  echo "employer acquisition is running; publisher will retry" >&2
  emit_telemetry lock_overlap 75
  exit 75
fi

started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
metrics_path="$receipt_root/publisher-latest-metrics.json"
receipt_path="$receipt_root/publisher-latest.json"
status="failed"
exit_code=1
crosswalk_arg=""
if [ -n "${RUNR_COMPANY_IDENTITY_CROSSWALK:-}" ]; then
  crosswalk_arg="--identity-crosswalk $RUNR_COMPANY_IDENTITY_CROSSWALK"
fi
skip_status_only_arg=""
if [ "${RUNR_PUBLISHER_SKIP_STATUS_ONLY:-0}" = "1" ]; then
  skip_status_only_arg="--skip-status-only"
fi

set +e
timeout --foreground "$run_timeout" "$python_bin" scripts/publish_producer_states.py \
  --manifest "$manifest" \
  --linkedin-state "$linkedin_state_db" \
  --employer-state "$employer_state_db" \
  --data-dir "$data_dir" \
  --source-version "${RUNR_SOURCE_VERSION:-unknown}" \
  $crosswalk_arg \
  $skip_status_only_arg \
  > "$metrics_path" 2>&1
exit_code=$?
set -e
if [ "$exit_code" -eq 0 ]; then status="succeeded"; fi
if [ "$exit_code" -eq 0 ]; then reason="ok"; else reason="failed"; fi
emit_telemetry "$reason" "$exit_code" "$started_at" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cat "$metrics_path"
"$python_bin" scripts/write_acquisition_receipt.py \
  --source publisher \
  --status "$status" \
  --exit-code "$exit_code" \
  --started-at "$started_at" \
  --finished-at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --metrics "$metrics_path" \
  --output "$receipt_path" \
  --release-commit "${RUNR_SOURCE_VERSION:-${RUNR_RELEASE_COMMIT:-}}" \
  > "$receipt_root/publisher-receipt-write.json"

exit "$exit_code"
