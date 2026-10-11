#!/usr/bin/env sh
set -eu

project_dir="${RUNR_PROJECT_DIR:-/opt/runr}"
python_bin="${RUNR_PYTHON_BIN:-$project_dir/.venv/bin/python}"
input="${RUNR_COMPANY_EVIDENCE_INPUT:-/srv/runr/shared/inputs/company_sources_linkedin_ids.csv}"
root="${RUNR_MANIFEST_GENERATIONS_ROOT:-/srv/runr/shared/inputs/manifest-generations}"
active="${RUNR_ACTIVE_MANIFEST_DIR:-/srv/runr/shared/inputs/manifest-generations/active}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
generation="$root/$stamp"
mkdir -p "$generation"

"$python_bin" /opt/runr-ops/refresh_live_company_manifest.py \
  --input "$input" \
  --snapshot-output "$generation/company_sources_catalog_complete.csv" \
  --output "$generation/SOURCE_ELIGIBILITY_MANIFEST.json" \
  --raw-sidecar "$generation/SOURCE_ELIGIBILITY_RAW.jsonl" \
  --cycle-id "catalog-refresh-$stamp" \
  --as-of "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --max-evidence-age-days "${RUNR_MANIFEST_MAX_EVIDENCE_AGE_DAYS:-365}" \
  > "$generation/refresh-report.json"

"$python_bin" -c \
  "from backend.application.source_eligibility_manifest import load_manifest; load_manifest('$generation/SOURCE_ELIGIBILITY_MANIFEST.json')"
ln -s "$generation" "$active.new"
mv -Tf "$active.new" "$active"
