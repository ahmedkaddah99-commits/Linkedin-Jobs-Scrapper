#!/usr/bin/env sh
set -eu

# Build verified, canonicalized producer-state copies and atomically switch the
# active state symlink. The raw restored databases are never modified.

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

# Validate the immutable seed inputs and raw-state schemas before creating any
# derived release. Mutable state size/hash drift is expected after a prior run;
# integrity and table contracts remain mandatory.
RUNR_ACQUISITION_INPUT_ROOT="$input_root" \
RUNR_ACQUISITION_STATE_ROOT="$raw_state_root" \
  "$python_bin" deploy/validate_acquisition_runtime.py \
    --manifest "$manifest" \
    --role all \
    --allow-state-drift

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

active_link_tmp="$state_root/.active-link.$$"
rm -f "$active_link_tmp"
ln -s "$release_dir" "$active_link_tmp"
mv -Tf "$active_link_tmp" "$active_link"

echo "active_state_root=$active_link"
echo "linkedin_state=$active_link/linkedin/master_linkedin_jobs_state.db"
echo "employer_state=$active_link/employer/master_employer_jobs_state.db"
echo "identity_crosswalk=$active_link/company_identity_crosswalk.json"
