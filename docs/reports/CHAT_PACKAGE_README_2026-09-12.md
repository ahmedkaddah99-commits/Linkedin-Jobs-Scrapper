# Runr production completion package README

This package is the final source/report handoff for the production work in
this chat. The authoritative narrative is
`docs/reports/RUNR_PRODUCTION_COMPLETION_REPORT_2026-09-12.md`.

## Included

- All tracked source/deployment/test paths changed in `runr-production-final` after the prior VPS release through final release `4a1b1df55b9dbac9745d29d1916a85fe9575a114`.
- Current reference copies of `render.yaml`, `deploy/start.sh`, and
  `frontend/src/styles.css` are included because they explain the Render role
  and display layout even when not modified in this delta.
- Operations and report documents created or updated in the active workspace for this workstream:
  - `docs/operations/CONTABO_VPS6_RESOURCE_RECORD_2026-09-11.md`
  - `docs/operations/RUNR_SCRAPER_PRODUCER_BUNDLE_README.md`
  - `docs/operations/SOURCE_INVENTORY.md`
  - `docs/reports/SCRAPER_CAPACITY_AND_EFFICIENCY_REPORT_2026-09-11.md`
  - `SCRAPER_STATUS_REPORT_2026-09-11.md`
  - `scripts/audit_runr_data_readiness.py`
  - `docs/reports/RUNR_PRODUCTION_COMPLETION_REPORT_2026-09-12.md`
  - this README

## Excluded

Secrets, `.env` files, state databases, node/Python caches, existing zip archives, and the large preserved job catalog outputs are excluded. The zip is a source/report review artifact, not a deployable release bundle.

## Important interpretation

The package contains the implemented bounded acquisition, incremental
publication, display-first policy, logo-provider, Docker interpreter, and
cursor-pagination changes. It does not contain credentials, databases, or
historical catalog exports. The final report explicitly records the remaining
publisher-bootstrap gap, partial logo asset coverage, and the live Render
Turso-read/deployment lag instead of presenting them as complete.
