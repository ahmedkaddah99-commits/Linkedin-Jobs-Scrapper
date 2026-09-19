# Runr chat package README

This package was prepared for the requested design review.

## Included

- All 45 tracked source/deployment/test paths changed in `runr-production-final` after baseline commit `c25d394ab9355e4d08a058589d9e125df9ee7444` through release `107114620765b52a0c3f41abaf51d4cda67edfab`.
- The relevant current pagination and Render runtime files are included among those paths, with current reference copies of `Dockerfile.api`, `Dockerfile.worker`, `render.yaml`, and `frontend/src/styles.css` added because they are required to review the runtime and sentinel behavior even though they were not modified after the baseline.
- Operations and report documents created or updated in the active workspace for this workstream:
  - `docs/operations/CONTABO_VPS6_RESOURCE_RECORD_2026-09-11.md`
  - `docs/operations/RUNR_SCRAPER_PRODUCER_BUNDLE_README.md`
  - `docs/operations/SOURCE_INVENTORY.md`
  - `docs/reports/SCRAPER_CAPACITY_AND_EFFICIENCY_REPORT_2026-09-11.md`
  - `SCRAPER_STATUS_REPORT_2026-09-11.md`
  - `scripts/audit_runr_data_readiness.py`
  - `docs/reports/CHAT_CHANGES_AND_PRODUCTION_REGRESSION_REPORT_2026-09-12.md`
  - this README

## Excluded

Secrets, `.env` files, state databases, node/Python caches, existing zip archives, and the large preserved job catalog outputs are excluded. The zip is a source/report review artifact, not a deployable release bundle.

## Important interpretation

The package records evidence before a new design is approved. It does not contain a speculative pagination rewrite or a Render runtime fix. The accompanying regression report explains the existing cursor pagination, the automatic observer-prefetch risk, and the independent `/app/.venv/bin/python` deployment mismatch.
