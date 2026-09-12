#!/usr/bin/env sh
set -eu

source_name="${1:-}"
case "$source_name" in
  linkedin|employer) ;;
  *) echo "usage: run-acquisition-source.sh linkedin|employer" >&2; exit 64 ;;
esac

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$project_dir"
python_bin="${RUNR_PYTHON_BIN:-$project_dir/.venv/bin/python}"
manifest="${RUNR_ACQUISITION_MANIFEST:-/srv/runr/shared/inputs/SOURCE_ELIGIBILITY_MANIFEST_RC005_RECONCILED.json}"
runtime_manifest="${RUNR_ACQUISITION_DATA_MANIFEST:-$project_dir/deploy/acquisition-data-manifest.json}"
state_root="${RUNR_ACQUISITION_STATE_ROOT:-/srv/runr/state}"
export_root="${RUNR_ACQUISITION_EXPORT_ROOT:-/srv/runr/exports}"
receipt_root="${RUNR_ACQUISITION_RECEIPT_ROOT:-$export_root/receipts}"
lock_root="${RUNR_ACQUISITION_LOCK_ROOT:-$state_root/locks}"
include_single_source="${RUNR_ACQUISITION_INCLUDE_SINGLE_SOURCE:-1}"
total_cap="${RUNR_ACQUISITION_MAX_REQUESTS:-30}"

if [ "$source_name" = "linkedin" ]; then
  state_dir="${RUNR_LINKEDIN_STATE_DIR:-$state_root/linkedin}"
  output_dir="$export_root/linkedin"
  state_role="linkedin"
  source_cap="${RUNR_LINKEDIN_MAX_REQUESTS:-20}"
  pagination_report="${RUNR_LINKEDIN_PAGINATION_REPORT:-/srv/runr/shared/inputs/linkedin/linkedin_endpoint_pagination_validation.json}"
  filters_report="${RUNR_LINKEDIN_FILTERS_REPORT:-/srv/runr/shared/inputs/linkedin/linkedin_guest_endpoint_filter_validation.json}"
else
  state_dir="${RUNR_EMPLOYER_STATE_DIR:-$state_root/employer}"
  output_dir="$export_root/employer"
  state_role="employer"
  source_cap="${RUNR_EMPLOYER_MAX_REQUESTS:-10}"
fi

is_positive_integer() {
  case "$1" in
    ''|*[!0-9]*|0) return 1 ;;
    *) return 0 ;;
  esac
}

if ! is_positive_integer "$total_cap" || ! is_positive_integer "$source_cap"; then
  echo "Acquisition caps must be positive: total=$total_cap source=$source_cap" >&2
  exit 64
fi
other_cap="${RUNR_EMPLOYER_MAX_REQUESTS:-10}"
if [ "$source_name" = "employer" ]; then other_cap="${RUNR_LINKEDIN_MAX_REQUESTS:-20}"; fi
if ! is_positive_integer "$other_cap" || [ "$((source_cap + other_cap))" -gt "$total_cap" ]; then
  echo "Per-source acquisition request caps exceed the positive total cap." >&2
  exit 64
fi

mkdir -p "$output_dir" "$receipt_root" "$lock_root"
lock_file="$lock_root/$source_name.lock"
exec 9>"$lock_file"
if ! flock -n 9; then
  echo "$source_name acquisition is already running" >&2
  exit 75
fi

started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
metrics_path="$receipt_root/${source_name}-latest-metrics.json"
receipt_path="$receipt_root/${source_name}-latest.json"
status="failed"
exit_code=1

set +e
"$python_bin" deploy/validate_acquisition_runtime.py \
  --manifest "$runtime_manifest" \
  --role "$state_role" \
  --allow-state-drift \
  > "$receipt_root/${source_name}-validation.json"
validation_code=$?
if [ "$validation_code" -eq 0 ]; then
  if [ "$source_name" = "linkedin" ]; then
    args=""
    if [ "$include_single_source" = "1" ] || [ "$include_single_source" = "true" ]; then args="--include-single-source"; fi
    "$python_bin" scripts/run_manifested_linkedin.py \
      --manifest "$manifest" \
      --output-dir "$output_dir" \
      --state-dir "$state_dir" \
      --require-existing-state \
      --pagination-report "$pagination_report" \
      --filters-report "$filters_report" \
      --mode "${RUNR_LINKEDIN_MODE:-daily}" \
      --workers "${RUNR_LINKEDIN_WORKERS:-10}" \
      --detail-workers "${RUNR_LINKEDIN_DETAIL_WORKERS:-5}" \
      --per-proxy-concurrency "${RUNR_LINKEDIN_PER_PROXY_CONCURRENCY:-1}" \
      --max-requests "$source_cap" \
      $args > "$metrics_path" 2>&1
  else
    args=""
    if [ "$include_single_source" = "1" ] || [ "$include_single_source" = "true" ]; then args="--include-single-source"; fi
    "$python_bin" scripts/run_manifested_employer.py \
      --manifest "$manifest" \
      --output-dir "$output_dir" \
      --state-dir "$state_dir" \
      --require-existing-state \
      --full \
      --max-requests "$source_cap" \
      $args > "$metrics_path" 2>&1
  fi
  exit_code=$?
else
  cp "$receipt_root/${source_name}-validation.json" "$metrics_path"
  exit_code=$validation_code
fi
set -e

if [ "$exit_code" -eq 0 ]; then status="succeeded"; fi
cat "$metrics_path"
"$python_bin" scripts/write_acquisition_receipt.py \
  --source "$source_name" \
  --status "$status" \
  --exit-code "$exit_code" \
  --started-at "$started_at" \
  --finished-at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --metrics "$metrics_path" \
  --output "$receipt_path" \
  --release-commit "${RUNR_SOURCE_VERSION:-${RUNR_RELEASE_COMMIT:-}}" \
  > "$receipt_root/${source_name}-receipt-write.json"

exit "$exit_code"
