# Historical readiness audits

These September 2026 reports describe historical data and must not be used as current production status. Summary reports and reconciliation evidence remain here. Generated CSV datasets were removed from the working tree to keep routine repository exploration small; all originals remain in Git at revision `3631aab56749bac0d19bfa8846221f8b3bf23abe`.

Retrieve an original without rerunning a historical audit:

```powershell
git show 3631aab56749bac0d19bfa8846221f8b3bf23abe:data/audit/runr_readiness/2026-09-22/jobs_readiness.csv
```

The generator is `scripts/audit_runr_data_readiness.py`; its outputs describe the database supplied to that run. Use a separate ignored output directory for new audits.

Removed generated files:

- `data/audit/runr_readiness/2026-09-11/companies_readiness.csv` (446,433 bytes)
- `data/audit/runr_readiness/2026-09-11/jobs_readiness.csv` (140,325 bytes)
- `data/audit/runr_readiness/2026-09-22/catalog_join.csv` (390,799 bytes)
- `data/audit/runr_readiness/2026-09-22/companies_readiness.csv` (5,611,368 bytes)
- `data/audit/runr_readiness/2026-09-22/jobs_readiness.csv` (3,704,147 bytes)
