# Critical acquisition recovery ticket research — 2026-09-19

Research State: **Current**

## Decision

Create two non-duplicate P0 children under RUN-24:

1. Preserve every recovered producer, employer, company-identity, enrichment, and code artifact in verified off-host storage.
2. Restore the preserved producer states into the authoritative VPS state layout only after live topology and timer ownership are proven.

Existing RUN-25/RUN-26/RUN-27/RUN-28/RUN-30/RUN-32/RUN-33/RUN-34/RUN-39/RUN-40/RUN-41 continue to own live topology, timer ownership, collector repair, publisher checkpointing, row reconciliation, Turso backfill, publishability remediation, employer targeting, enrichment, and end-to-end acceptance. Creating replacements would duplicate that work.

## Recovered evidence

- LinkedIn producer DB: 3,479,191,552 bytes; SHA-256 `ADC5C1AB7AC5B7BDCA67CDABD7687FDD29913AFAE188FAB2ABA4377A41327525`; SQLite quick check `ok`; 188,206 jobs and 188,206 company observations.
- Employer producer DB: 83,841,024 bytes; SHA-256 `4F779500C9CD5FB66342CB36BD2FD236CEFB9B9EEBB3CAF13876FCA8B1265AAF`; SQLite quick check `ok`; 428 companies and 2,612 jobs.
- LinkedIn identity/enrichment DB: 413,691,904 bytes; SHA-256 `4DA05480F291DBDF47C4BBD7988D1DA8B79206CB2310332F3F5A32DFBA627F2E`; integrity `ok`; 15,454 URL resolutions.
- Company source CSV: 17,601 rows, including 12,059 resolved LinkedIn company IDs.
- Verified complete-history Git bundle preserves the current deployment ref and final LinkedIn/employer refs. The LinkedIn final patch is integrated; the employer final patch is not patch-equivalent to the current deployment branch.
- R2 contains only a 770,048-byte RC-027 LinkedIn pilot checkpoint. No full LinkedIn, employer, or enrichment database was found under acquisition/checkpoint/backup prefixes. The employer checkpoint explicitly says `not_uploaded`.
- Full evidence and checksums: `data/audit/runr_source_state/2026-09-19/recovery_manifest.md`.

## VPS entrypoint finding

The repository contract routes systemd through `deploy/run-acquisition-source.sh`, which invokes `scripts/run_manifested_linkedin.py` and `scripts/run_manifested_employer.py`; the publisher invokes `scripts/publish_producer_states.py`. Static repository evidence therefore identifies the intended scripts, but current live VPS unit contents, release SHA, environment overrides, and active state paths remain unverified and stay owned by RUN-25 and RUN-26.

## Publication objective

The remediation program must classify 100% of recovered rows with explicit publishable or blocker reasons and target at least 95% publishability among active, non-duplicate, technically valid records. Identity, direct apply URL, description, freshness/lifecycle, provenance, logo, seniority, employment type, workplace arrangement, and company enrichment remain blocking. Salary and benefits remain non-blocking. Invalid, inactive, expired, duplicate, and Easy-Apply-only records are excluded from the eligible denominator, not silently counted as publishable.

## Ordering

`off-host preservation -> live topology proof -> controlled VPS restore -> row reconciliation/checkpoint ownership -> bounded Turso backfill -> publishability remediation -> end-to-end acceptance`

No live restore, upload, database mutation, or provider request was performed by this research pass.
