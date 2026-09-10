#!/usr/bin/env sh
set -eu

PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$PROJECT_DIR"

python_bin="${RUNR_PYTHON_BIN:-$PROJECT_DIR/.venv/bin/python}"
manifest="${RUNR_ACQUISITION_MANIFEST:-/srv/runr/shared/inputs/SOURCE_ELIGIBILITY_MANIFEST_RC005_RECONCILED.json}"
state_root="${RUNR_ACQUISITION_STATE_ROOT:-/srv/runr/state}"
export_root="${RUNR_ACQUISITION_EXPORT_ROOT:-/srv/runr/exports}"
data_dir="${RUNR_DATA_DIR:-/var/lib/runr/acquisition-data}"
include_single_source="${RUNR_ACQUISITION_INCLUDE_SINGLE_SOURCE:-1}"

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
  --state-dir "$state_root/linkedin" \
  --require-existing-state \
  --mode daily \
  --max-requests "${RUNR_LINKEDIN_MAX_REQUESTS:-${RUNR_ACQUISITION_MAX_REQUESTS:-0}}" \
  $linkedin_args \
  || linkedin_status=$?

employer_status=0
"$python_bin" scripts/run_manifested_employer.py \
  --manifest "$manifest" \
  --output-dir "$export_root/employer" \
  --state-dir "$state_root/employer" \
  --require-existing-state \
  --full \
  --max-requests "${RUNR_EMPLOYER_MAX_REQUESTS:-${RUNR_ACQUISITION_MAX_REQUESTS:-0}}" \
  $employer_args \
  || employer_status=$?

# Delivery is attempted even when one source collector exits non-zero. The
# bridge uses durable state and coverage receipts, so a failed company/source
# cannot erase or block the other source's observations.
"$python_bin" scripts/publish_producer_states.py \
  --manifest "$manifest" \
  --linkedin-state "$state_root/linkedin/master_linkedin_jobs_state.db" \
  --employer-state "$state_root/employer/master_employer_jobs_state.db" \
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
