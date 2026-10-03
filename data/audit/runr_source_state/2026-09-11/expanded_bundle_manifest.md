# Expanded Runr source-state readiness bundle

Generated: `2026-09-11`

This bundle adds the full RC023 producer-state audit to the earlier canonical/Turso audit. It contains reports, machine-readable results, remediation queues, contract/producer scripts, runtime inventory, the migration transcript, and redacted production visibility evidence.

## Included audit outputs

- `full_source_state_audit_report.md`
- `source_state_inventory.md`
- `rc023-authoritative/completeness_audit_real.md`
- `rc023-authoritative/completeness_audit_real.json`
- `canonical_runr_readiness/audit_report.md`
- `canonical_runr_readiness/audit_summary.json`
- `canonical_runr_readiness/jobs_readiness.csv`
- `canonical_runr_readiness/companies_readiness.csv`
- `canonical_runr_readiness/production_visibility_evidence.md`
- `canonical_runr_readiness/bundle_manifest.md`

## Included source and audit scripts

- `source_code/runr_admin/scripts/audit_real_job_data.py`
- `source_code/runr_admin/scripts/audit_job_publication_completeness.py`
- `source_code/scraper/scripts/audit_runr_data_readiness.py`
- `source_code/scraper/scripts/master_employer_jobs_catalog.py` (active scraper-worktree reference)
- `source_code/runr_admin/backend/acquisition/job_publication_completeness.py`
- `source_code/runr_admin/scripts/master_linkedin_jobs_catalog.py`
- `source_code/runr_admin/scripts/master_employer_jobs_catalog.py`
- `source_code/runr_admin/scripts/run_manifested_linkedin.py`
- `source_code/runr_admin/scripts/run_manifested_employer.py`
- `source_code/runr_admin/scripts/publish_producer_states.py`
- `source_code/runr_admin/scripts/build_master_jobs_catalog.py`
- `source_code/runr_admin/scripts/acquisition_state_backup.py`
- `source_code/runr_admin/scripts/clean_master_company_url.py`
- `source_code/runr_admin/scripts/apply_known_company_websites.py`
- `source_code/runr_admin/scripts/linkedin_company_enrichment_pipeline.py`
- `source_code/runr_admin/scripts/run_linkedin_company_id_resolution.py`
- `source_code/runr_admin/backend/acquisition/producer_adapters.py`
- `source_code/runr_admin/backend/acquisition/employer_coverage.py`
- `source_code/runr_admin/scripts/audit_employer_coverage.py`
- `source_code/runr_admin/scripts/backfill_company_ids.py`
- `source_code/runr_admin/scripts/reconcile_company_registry.py`

## Included references

- `references/ACQUISITION_RUNTIME_DATA_INVENTORY.md`
- `references/JOB_PUBLICATION_COMPLETENESS_CONTRACT.md`
- `references/migration_transcript_pasted-text.txt`

## Deliberate exclusions

The bundle excludes all `.env` files, credentials, tokens, production databases, SQLite producer-state databases, logs, browser sessions, caches, `node_modules`, `.venv`, and other mutable runtime data. The source database absolute paths, sizes, known hashes, and audit results are recorded in the reports so the implementation decision can target the original files without copying them into the ZIP.
