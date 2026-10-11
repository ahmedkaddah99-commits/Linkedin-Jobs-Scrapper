# Runr data-readiness audit bundle

Generated: 2026-09-11

This bundle supports the next implementation decision. It contains the live audit outputs, the exact completeness validator and publication/acquisition code used for interpretation, the migration transcript, production handoff evidence, and the source inputs needed to reason about canonical-company identity coverage.

## Local audit outputs

- `audit_report.md` — human-readable decision report.
- `audit_summary.json` — machine-readable counts, current publication/cycle metadata, raw field gaps, and absolute source paths.
- `jobs_readiness.csv` — all 299 canonical jobs, with current-head membership, validator status, and reason codes.
- `companies_readiness.csv` — all 1,428 canonical companies, with identity/presentation/enrichment gates, URLs, profiles, logo state, and job references.
- `production_visibility_evidence.md` — redacted provider visibility results and the separate frontend/API operational blocker.
- `audit_runr_data_readiness.py` — reproducible read-only audit script.

## Decision snapshot

- Current publication head: `acq_publication_5ff941b21ea84b78af39a4a5cb508b3c`.
- Current head jobs: 47; validator-publishable: 47.
- All canonical jobs: 299; validator-publishable: 93.
- Canonical companies: 1,428; canonical identity-ready: 1,428.
- Company presentation-ready: 1,379; enrichment-complete under the non-blocking audit gate: 893.
- Latest cycle: `acq_cycle_818f17433ea047c6b2c86f949cdbdd58`, `degraded`, `partial_source_coverage`, zero fresh observations.

## Explicit exclusions

The ZIP intentionally excludes `user_config/.env`, all credentials and tokens, VPS env files, Turso/R2/SQLite state databases, production logs, browser sessions, `node_modules`, `.venv`, caches, and the 23 MB VPS delivery JSON. Those are secret-bearing, runtime-only, mutable, or unnecessarily large for implementation review.
