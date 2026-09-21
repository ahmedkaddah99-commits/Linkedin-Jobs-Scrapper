#!/usr/bin/env sh
set -eu

# Build verified, canonicalized producer-state copies and atomically switch the
# active state symlink. The raw restored databases are never modified.
# `rollback` atomically re-points the active symlink at the most recent other
# state release without deleting any generation.

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$project_dir"
python_bin="${RUNR_PYTHON_BIN:-$project_dir/.venv/bin/python}"
manifest="${RUNR_ACQUISITION_DATA_MANIFEST:-$project_dir/deploy/acquisition-data-manifest.json}"
input_root="${RUNR_ACQUISITION_INPUT_ROOT:-/srv/runr/shared/inputs}"
state_root="${RUNR_ACQUISITION_STATE_ROOT_PHYSICAL:-/srv/runr/state}"
raw_state_root="${RUNR_ACQUISITION_RAW_STATE_ROOT:-$state_root}"
release_id="${RUNR_SOURCE_VERSION:-$(date -u +%Y%m%dT%H%M%SZ)}"
release_id=$(printf '%s' "$release_id" | tr -c 'A-Za-z0-9._-' '_')
release_dir="$state_root/versions/$release_id"
raw_linkedin="$raw_state_root/linkedin/master_linkedin_jobs_state.db"
raw_employer="$raw_state_root/employer/master_employer_jobs_state.db"
registry="$input_root/company_registry_canonical.csv"
active_link="$state_root/active"
lock_root="${RUNR_ACQUISITION_LOCK_ROOT:-$state_root/locks}"

switch_active_link() {
  target="$1"
  active_link_tmp="$state_root/.active-link.$$"
  rm -f "$active_link_tmp"
  ln -s "$target" "$active_link_tmp"
  mv -Tf "$active_link_tmp" "$active_link"
}

if [ "${1:-}" = "rollback" ]; then
  if [ -e "$active_link" ] && [ ! -L "$active_link" ]; then
    echo "Refusing to roll back non-symlink active state path: $active_link" >&2
    exit 1
  fi
  mkdir -p "$lock_root"
  exec 9>"$lock_root/canonicalize.lock"
  if ! flock -n 9; then
    echo "state activation or rollback is already running" >&2
    exit 75
  fi
  current_target=""
  if [ -L "$active_link" ]; then
    current_target=$(readlink "$active_link")
  fi
  rollback_to=""
  for candidate_dir in "$state_root"/versions/*/; do
    [ -d "$candidate_dir" ] || continue
    candidate="${candidate_dir%/}"
    if [ -n "$current_target" ] && [ "$candidate" = "$current_target" ]; then
      continue
    fi
    if [ -z "$rollback_to" ] || [ "$candidate" -nt "$rollback_to" ]; then
      rollback_to="$candidate"
    fi
  done
  if [ -z "$rollback_to" ]; then
    echo "No previous state release is available for rollback under: $state_root/versions" >&2
    exit 1
  fi
  switch_active_link "$rollback_to"
  echo "rollback_from=${current_target:-<none>}"
  echo "rollback_to=$rollback_to"
  echo "active_state_root=$active_link"
  exit 0
fi

if [ "$#" -gt 0 ]; then
  echo "usage: restore-acquisition-states.sh [rollback]" >&2
  exit 64
fi

if [ ! -x "$python_bin" ]; then
  echo "Missing required project interpreter: $python_bin" >&2
  exit 1
fi
if [ -e "$active_link" ] && [ ! -L "$active_link" ]; then
  echo "Refusing to replace non-symlink active state path: $active_link" >&2
  exit 1
fi
if [ -e "$release_dir" ]; then
  echo "Refusing to replace existing state release: $release_dir" >&2
  exit 1
fi

mkdir -p "$lock_root" "$state_root/versions"
exec 9>"$lock_root/canonicalize.lock"
if ! flock -n 9; then
  echo "state canonicalization is already running" >&2
  exit 75
fi

# Validate the immutable seed inputs, raw-state schemas, and the producer
# row-count contract before creating any derived release. Mutable state
# size/hash drift is expected after a prior run; integrity, table, and
# row-count contracts remain mandatory.
RUNR_ACQUISITION_INPUT_ROOT="$input_root" \
RUNR_ACQUISITION_STATE_ROOT="$raw_state_root" \
  "$python_bin" deploy/validate_acquisition_runtime.py \
    --manifest "$manifest" \
    --role all \
    --allow-state-drift \
    --require-table-counts

mkdir -p "$release_dir"
"$python_bin" scripts/canonicalize_producer_states.py \
  --registry "$registry" \
  --linkedin-state "$raw_linkedin" \
  --employer-state "$raw_employer" \
  --output-dir "$release_dir"

mkdir -p "$release_dir/linkedin" "$release_dir/employer"
ln -s "../master_linkedin_jobs_state.canonicalized.db" \
  "$release_dir/linkedin/master_linkedin_jobs_state.db"
ln -s "../master_employer_jobs_state.canonicalized.db" \
  "$release_dir/employer/master_employer_jobs_state.db"

switch_active_link "$release_dir"

echo "active_state_root=$active_link"
echo "linkedin_state=$active_link/linkedin/master_linkedin_jobs_state.db"
echo "employer_state=$active_link/employer/master_employer_jobs_state.db"
echo "identity_crosswalk=$active_link/company_identity_crosswalk.json"
