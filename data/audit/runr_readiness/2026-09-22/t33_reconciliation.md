# T33 producer state reconciliation

Generated: 2026-09-22
Contract: `job_publication_completeness_v1`
Scope: read-only source-state and catalog-ID reconciliation. No producer state,
catalog row, timestamp, checkpoint, or publication was modified.

## Inputs

| Input | Snapshot evidence | Rows / bytes | SHA-256 |
| --- | --- | ---: | --- |
| LinkedIn producer state | `data/audit/runr_source_state/2026-09-19/recovery_manifest.md` | 188,206 jobs / 3,479,191,552 B | `ADC5C1AB7AC5B7BDCA67CDABD7687FDD29913AFAE188FAB2ABA4377A41327525` |
| Employer producer state | same recovery manifest | 2,612 jobs / 83,841,024 B | `4F779500C9CD5FB66342CB36BD2FD236CEFB9B9EEBB3CAF13876FCA8B1265AAF` |
| LinkedIn identity resolution | same recovery manifest | 15,454 URL resolutions | `4DA05480F291DBDF47C4BBD7988D1DA8B79206CB2310332F3F5A32DFBA627F2E` |
| Company source registry | same recovery manifest | 17,601 rows; 12,059 resolved LinkedIn IDs | `DEDE5FD5052EC8CC85886344C66C1761D818FC686E437670E8B5AC1636914F87` |

The recovered files are local preserved copies. The live VPS state is not
assumed to equal these snapshots.

## Producer counts and classification

| Source | Input rows | Unique source IDs | Duplicate rows | Publishable | Primary outcome counts |
| --- | ---: | ---: | ---: | ---: | --- |
| LinkedIn | 188,206 | 188,206 | 0 | 0 | unresolved identity 145,637; missing required 42,561; invalid 8 |
| Employer | 2,612 | 2,440 | 172 | 0 | unresolved identity 2,018; missing required 550; invalid 41; placeholder 3 |
| Combined | 190,818 | 190,646 | 172 | 0 | all rows have an explicit audit outcome |

The detailed reason counters are in
`producer/completeness_audit_real.json`. The dominant reasons are missing
canonical company identity (145,637 LinkedIn and 2,018 employer rows), weak or
blocked descriptions, missing location, unsupported Easy Apply, and duplicate
employer source IDs. Salary and benefits are not used as rejection reasons.

## Catalog join

`catalog_join.csv` is a redacted stable-ID join keyed by `external_job_id`.
It contains 6,373 catalog rows: 6,338 in the current publication head and 35
outside that head. The readiness snapshot separately records 6,370 canonical
jobs and 6,335 published jobs; those counts are retained as separate evidence
because the join export includes three rows outside the canonical-job count.

For the recovered LinkedIn source IDs:

| Bucket | Count |
| --- | ---: |
| Local LinkedIn IDs matched to current-head catalog rows | 6,090 |
| Local LinkedIn IDs absent from the catalog join | 182,116 |
| Catalog current-head IDs absent from the recovered LinkedIn snapshot | 248 |
| Catalog rows outside current head and absent from recovered LinkedIn | 35 |
| Local LinkedIn IDs matched only to a non-head row | 0 |

The employer snapshot uses composite `source_key` values and has no employer
family key in this catalog export, so its 2,612 rows are reported as
`catalog_match_unproven` rather than being falsely joined to LinkedIn IDs.

## Reconciliation buckets

| Bucket | Result | Evidence / limit |
| --- | --- | --- |
| Local-only | LinkedIn 182,116; employer 2,612 | Stable source IDs were not found in the catalog export. |
| Catalog/VPS-only candidate | 248 current-head rows | Present in the catalog join but absent from the recovered LinkedIn snapshot; live VPS ownership is not proven. |
| Published but not visible | 0 proven | No separate UI visibility snapshot was supplied; the 35 non-head rows are kept in the stale/superseded bucket. |
| Stale/closed or superseded | 35 catalog rows | `in_head=0`; the readiness snapshot also reports 35 stale/closed canonical jobs. |
| VPS-only | Unknown | Requires the corrected read-only VPS inventory; no live host claim is made here. |

Every producer row is assigned an audit outcome and every catalog join row is
assigned to current-head, non-head, matched-local, or absent-local. Unknown VPS
ownership remains explicit instead of being inferred from a local snapshot.

## Reproducibility

- Producer audit: `.venv\\Scripts\\python.exe scripts/audit_real_job_data.py` with the preserved LinkedIn and employer state paths and the canonical company registry.
- Required ticket checks:
  - `.venv\\Scripts\\python.exe scripts/audit_job_publication_completeness.py --help`
  - `.venv\\Scripts\\python.exe scripts/audit_employer_coverage_real.py --help`
- Catalog evidence: `data/audit/runr_readiness/2026-09-22/catalog_join.csv`, `audit_summary.json`.
- No source DB, VPS state, Turso row, or publisher checkpoint was changed.
