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

mkdir -p "$receipt_root" "$lock_root"
exec 9>"$lock_root/publisher.lock"
if ! flock -n 9; then
  echo "producer-state publisher is already running" >&2
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

set +e
"$python_bin" scripts/publish_producer_states.py \
  --manifest "$manifest" \
  --linkedin-state "$linkedin_state_db" \
  --employer-state "$employer_state_db" \
  --data-dir "$data_dir" \
  --source-version "${RUNR_SOURCE_VERSION:-unknown}" \
  $crosswalk_arg \
  > "$metrics_path" 2>&1
exit_code=$?
set -e
if [ "$exit_code" -eq 0 ]; then status="succeeded"; fi
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
