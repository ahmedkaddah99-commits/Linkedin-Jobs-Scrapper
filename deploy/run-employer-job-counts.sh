#!/usr/bin/env sh
set -eu
project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$project_dir"
python_bin="${RUNR_PYTHON_BIN:-/opt/runr/.venv/bin/python}"
state_root="${RUNR_ACQUISITION_STATE_ROOT:-/srv/runr/state/active}"
lock_root="${RUNR_ACQUISITION_LOCK_ROOT:-$state_root/locks}"
mkdir -p "$lock_root"
exec 6>"$lock_root/employer-job-counts.lock"
exec 7>"$lock_root/publisher.lock"
exec 8>"$lock_root/linkedin.lock"
exec 9>"$lock_root/employer.lock"
flock -n 6 || exit 75
flock -n 7 || exit 75
flock -n 8 || exit 75
flock -n 9 || exit 75
exec "$python_bin" scripts/process_employer_job_counts.py \
  --ledger /srv/runr/state/employer-job-counts/employer-counts.sqlite3 \
  --policy /etc/runr/title-collar-policy.json \
  --linkedin-state "${RUNR_LINKEDIN_STATE_DIR:-$state_root/linkedin}/master_linkedin_jobs_state.db" \
  --employer-state "${RUNR_EMPLOYER_STATE_DIR:-$state_root/employer}/master_employer_jobs_state.db" \
  --max-rows 500 --apply
