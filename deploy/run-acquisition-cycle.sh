#!/usr/bin/env sh
set -eu

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$project_dir"
total_cap="${RUNR_ACQUISITION_MAX_REQUESTS:-110}"
linkedin_cap="${RUNR_LINKEDIN_MAX_REQUESTS:-100}"
employer_cap="${RUNR_EMPLOYER_MAX_REQUESTS:-10}"
export_root="${RUNR_ACQUISITION_EXPORT_ROOT:-/srv/runr/exports}"

is_positive_integer() {
  case "$1" in
    ''|*[!0-9]*|0) return 1 ;;
    *) return 0 ;;
  esac
}

if ! is_positive_integer "$total_cap" || ! is_positive_integer "$linkedin_cap" || ! is_positive_integer "$employer_cap"; then
  echo "Set positive total and per-source acquisition request caps before enabling the timer." >&2
  exit 64
fi
if [ "$((linkedin_cap + employer_cap))" -gt "$total_cap" ]; then
  echo "Per-source acquisition request caps exceed RUNR_ACQUISITION_MAX_REQUESTS." >&2
  exit 64
fi

linkedin_status=0
deploy/run-acquisition-source.sh linkedin || linkedin_status=$?

employer_status=0
deploy/run-acquisition-source.sh employer || employer_status=$?

publisher_status=0
deploy/run-acquisition-publisher.sh || publisher_status=$?

# The combined CSV is only a projection of both source exports. Never create a
# one-source combined catalog when the other collector failed or has not yet
# produced a validated export.
combined_status=0
if [ -s "$export_root/linkedin/master_linkedin_jobs.csv" ] && [ -s "$export_root/employer/master_employer_jobs.csv" ]; then
  mkdir -p "$export_root/combined"
  python_bin="${RUNR_PYTHON_BIN:-$project_dir/.venv/bin/python}"
  "$python_bin" scripts/build_master_jobs_catalog.py \
    --linkedin-csv "$export_root/linkedin/master_linkedin_jobs.csv" \
    --employer-csv "$export_root/employer/master_employer_jobs.csv" \
    --output "$export_root/combined/master_jobs.csv" || combined_status=$?
else
  echo "combined catalog skipped: both source exports are required" >&2
fi

if [ "$linkedin_status" -ne 0 ] || [ "$employer_status" -ne 0 ] || [ "$publisher_status" -ne 0 ] || [ "$combined_status" -ne 0 ]; then
  exit 1
fi
