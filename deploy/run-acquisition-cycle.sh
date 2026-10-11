#!/usr/bin/env sh
set -eu

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$project_dir"
total_cap="${RUNR_ACQUISITION_MAX_REQUESTS:-110}"
linkedin_cap="${RUNR_LINKEDIN_MAX_REQUESTS:-100}"
employer_cap="${RUNR_EMPLOYER_MAX_REQUESTS:-10}"

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

if [ "$linkedin_status" -ne 0 ] || [ "$employer_status" -ne 0 ] || [ "$publisher_status" -ne 0 ]; then
  exit 1
fi
