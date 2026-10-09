#!/bin/sh
set -eu

cd /opt/runr

python_bin=/opt/runr/.venv/bin/python
manifest=${RUNR_ACQUISITION_MANIFEST:-/srv/runr/shared/inputs/manifest-generations/active/SOURCE_ELIGIBILITY_MANIFEST.json}
export_root=${RUNR_ACQUISITION_EXPORT_ROOT:-/srv/runr/exports}
state_root=${RUNR_ACQUISITION_STATE_ROOT:-/srv/runr/state/active}
lock_root=${RUNR_ACQUISITION_LOCK_ROOT:-/srv/runr/state/locks}
output_dir="$export_root/employer"
state_dir="$state_root/employer"

mkdir -p "$output_dir" "$state_dir" "$lock_root"
exec 9>"$lock_root/employer.lock"
flock -n 9 || exit 75

exec timeout --foreground "${RUNR_EMPLOYER_DRAIN_TIMEOUT_SECONDS:-172800}" \
  "$python_bin" scripts/run_manifested_employer.py \
  --manifest "$manifest" \
  --output-dir "$output_dir" \
  --state-dir "$state_dir" \
  --require-existing-state \
  --full \
  --max-requests "${RUNR_EMPLOYER_DRAIN_MAX_REQUESTS:-200000}" \
  --easy-first \
  --timeout "${RUNR_EMPLOYER_REQUEST_TIMEOUT_SECONDS:-10}" \
  --max-targets "${RUNR_EMPLOYER_MAX_TARGETS:-5}" \
  --max-pages "${RUNR_EMPLOYER_MAX_PAGES:-5}" \
  --company-concurrency "${RUNR_EMPLOYER_DRAIN_COMPANY_CONCURRENCY:-2}" \
  --max-pending "${RUNR_EMPLOYER_DRAIN_MAX_PENDING:-4}" \
  --http-concurrency "${RUNR_EMPLOYER_DRAIN_HTTP_CONCURRENCY:-4}" \
  --account-concurrency "${RUNR_EMPLOYER_DRAIN_ACCOUNT_CONCURRENCY:-4}" \
  --per-origin-concurrency "${RUNR_EMPLOYER_DRAIN_PER_ORIGIN_CONCURRENCY:-1}" \
  --include-single-source
