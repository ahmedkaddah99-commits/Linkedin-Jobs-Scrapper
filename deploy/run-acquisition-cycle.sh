#!/usr/bin/env sh
set -eu

PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$PROJECT_DIR"

python_bin="${RUNR_PYTHON_BIN:-$PROJECT_DIR/.venv/bin/python}"
manifest="${RUNR_ACQUISITION_MANIFEST:-/srv/runr/shared/inputs/SOURCE_ELIGIBILITY_MANIFEST_RC005_RECONCILED.json}"
state_root="${RUNR_ACQUISITION_STATE_ROOT:-/srv/runr/state}"
linkedin_state_dir="${RUNR_LINKEDIN_STATE_DIR:-$state_root/linkedin}"
employer_state_dir="${RUNR_EMPLOYER_STATE_DIR:-$state_root/employer}"
linkedin_state_db="${RUNR_LINKEDIN_STATE_DB:-$linkedin_state_dir/master_linkedin_jobs_state.db}"
employer_state_db="${RUNR_EMPLOYER_STATE_DB:-$employer_state_dir/master_employer_jobs_state.db}"
export_root="${RUNR_ACQUISITION_EXPORT_ROOT:-/srv/runr/exports}"
data_dir="${RUNR_DATA_DIR:-/var/lib/runr/acquisition-data}"
include_single_source="${RUNR_ACQUISITION_INCLUDE_SINGLE_SOURCE:-1}"
max_requests="${RUNR_ACQUISITION_MAX_REQUESTS:-0}"
linkedin_max_requests="${RUNR_LINKEDIN_MAX_REQUESTS:-0}"
employer_max_requests="${RUNR_EMPLOYER_MAX_REQUESTS:-0}"

is_positive_integer() {
  case "$1" in
    ''|*[!0-9]*|0) return 1 ;;
    *) return 0 ;;
  esac
}

if ! is_positive_integer "$max_requests" \
  || ! is_positive_integer "$linkedin_max_requests" \
  || ! is_positive_integer "$employer_max_requests"; then
  echo "Set positive total and per-source acquisition request caps before enabling the timer." >&2
  exit 64
fi
if [ "$((linkedin_max_requests + employer_max_requests))" -gt "$max_requests" ]; then
  echo "Per-source acquisition request caps exceed RUNR_ACQUISITION_MAX_REQUESTS." >&2
  exit 64
fi

mkdir -p "$export_root/linkedin" "$export_root/employer"

linkedin_args=""
employer_args=""
if [ "$include_single_source" = "1" ] || [ "$include_single_source" = "true" ]; then
  linkedin_args="--include-single-source"
  employer_args="--include-single-source"
fi

linkedin_status=0
"$python_bin" scripts/run_manifested_linkedin.py \
  --manifest "$manifest" \
  --output-dir "$export_root/linkedin" \
  --state-dir "$linkedin_state_dir" \
  --require-existing-state \
  --mode daily \
  --max-requests "$linkedin_max_requests" \
  $linkedin_args \
  || linkedin_status=$?

employer_status=0
"$python_bin" scripts/run_manifested_employer.py \
  --manifest "$manifest" \
  --output-dir "$export_root/employer" \
  --state-dir "$employer_state_dir" \
  --require-existing-state \
  --full \
  --max-requests "$employer_max_requests" \
  $employer_args \
  || employer_status=$?

# Delivery is attempted even when one source collector exits non-zero. The
# bridge uses durable state and coverage receipts, so a failed company/source
# cannot erase or block the other source's observations.
"$python_bin" scripts/publish_producer_states.py \
  --manifest "$manifest" \
  --linkedin-state "$linkedin_state_db" \
  --employer-state "$employer_state_db" \
  --data-dir "$data_dir" \
  --source-version "${RUNR_SOURCE_VERSION:-unknown}" \
  > "$export_root/producer-state-delivery.json"

"$python_bin" scripts/build_master_jobs_catalog.py \
  --linkedin-csv "$export_root/linkedin/master_linkedin_jobs.csv" \
  --employer-csv "$export_root/employer/master_employer_jobs.csv" \
  --output "$export_root/combined/master_jobs.csv"

if [ "$linkedin_status" -ne 0 ] || [ "$employer_status" -ne 0 ]; then
  exit 1
fi
