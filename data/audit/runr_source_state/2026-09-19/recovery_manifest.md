# Runr acquisition recovery manifest — 2026-09-19

Research State: **Current**

This manifest records the read-only discovery and non-destructive preservation
of the historical Runr acquisition producer state after the former
`C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots` root was found to
be absent. The recovered files are copied under:

`C:\Users\ahmed\Projects_Local\runr-acquisition-recovery\2026-09-19`

No active production database, Turso row, Git branch, or source Temp file was
modified or removed.

## Recovered LinkedIn producer state

- Stable path: `linkedin\master_linkedin_jobs_state.db`
- Recovery source:
  `C:\Users\ahmed\AppData\Local\Temp\runr-rc024-historical-20260909\linkedin\linkedin-20260909T085116426477Z-4b604df8392a\master_linkedin_jobs_state.db`
- Bytes: `3,479,191,552`
- SHA-256 of both source and stable copy:
  `ADC5C1AB7AC5B7BDCA67CDABD7687FDD29913AFAE188FAB2ABA4377A41327525`
- SQLite `PRAGMA quick_check`: `ok`
- Schema: 14 expected producer tables
- `jobs`: `188,206`
- `job_company_observations`: `188,206`
- `company_scans`: `11,921`
- `search_cards`: `198,491`
- `search_pages`: `52,386`
- `detail_queue`: `198,491`
- `detail_attempts`: `198,493`
- `lifecycle_events`: `187,415`
- `source_company_groups`: `11,896`

The recovered file is a SQLite Online Backup representation, so its physical
file hash differs from the historical live-source hash while retaining the
verified logical database contents.

Also preserved:

- `linkedin\master_linkedin_jobs.csv`
- Bytes: `775,613,386`
- SHA-256:
  `5DB2EB21032CC9D6FF8BB837A71E58D6E7E4E1BEF827CE8C5429367377292033`

## Recovered employer producer state

- Stable path: `employer\master_employer_jobs_state.db`
- Recovery source:
  `C:\Users\ahmed\AppData\Local\Temp\runr-rc026-benchmark-20260909-v3\historical\employer\master_employer_jobs_state.db`
- Bytes: `83,841,024`
- SHA-256:
  `4F779500C9CD5FB66342CB36BD2FD236CEFB9B9EEBB3CAF13876FCA8B1265AAF`
- SQLite `PRAGMA quick_check`: `ok`
- Tables: `companies`, `jobs`
- `companies`: `428`
- `jobs`: `2,612`

The RC-024 checkpoint manifest is preserved as `employer\checkpoint.json`.
It records that the employer checkpoint was **not uploaded** to R2.

Also preserved:

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `employer\master_employer_jobs.csv` | 38,097,370 | `49BEF439521161F0D251DD3E331A4CCB615DD354214B0559BAF0E59D8EC16790` |
| `employer\master_employer_jobs.jsonl` | 40,036,727 | `C22D44216006B5B6F4E9FD1115057694E81CB4DF9F096A8F3DB6AB7027DA7811` |
| `employer\master_employer_jobs_metrics.json` | 456 | `FAF48365397FF8D65F95E242D1F6EC11F578204711608855B37C79F46D8F5715` |

## Preserved company enrichment and LinkedIn identities

| File | Bytes | SHA-256 | Verification |
| --- | ---: | --- | --- |
| `company\linkedin_id_resolution.sqlite3` | 413,691,904 | `4DA05480F291DBDF47C4BBD7988D1DA8B79206CB2310332F3F5A32DFBA627F2E` | integrity `ok`; `url_resolution` 15,454; `request_log` 1,475,495; `run_meta` 10 |
| `company\company_sources_linkedin_ids.csv` | 18,807,044 | `B8B8512C0669CF57754A2783ED3E9E9B341FA4A0B7ABCD3DB9A7CFC91CD3DCE0` | 17,601 rows × 118 columns; 12,059 resolved LinkedIn company IDs |
| `company\company_registry_canonical.csv` | 11,968,530 | `DEDE5FD5052EC8CC85886344C66C1761D818FC686E437670E8B5AC1636914F87` | stable copy |
| `company\company_master.csv` | 17,482,721 | `F54BB4BF8DE3AAEB7C37AC9B3238E403CF998B32A6E8EFC9BC0F8C6B7DD6C6F5` | stable copy |

LinkedIn ID resolution statuses in the 17,601-row source:

- `RESOLVED`: 12,059
- `INVALID_LINKEDIN_URL`: 2,147
- `UNRESOLVED`: 2,341
- blank: 1,054

## Preserved collector code

The verified Git bundle is:

`code\runr-producer-code-and-history.bundle`

- Bytes: `36,440,939`
- SHA-256:
  `05138FD61556FA995A0C550E0F27A3F8EB0C6E583F4AA0CA92C2611514726E36`
- `git bundle verify`: complete history, valid SHA-1 bundle
- Preserved refs:
  - `deployment/render-turso-r2` at `30c8d5f1641951148de3e30f44165e8e69fb764e`
  - `temp/runr-linkedin-final` at `e84697110c199085fb625df253aae0354b236571`
  - `temp/runr-employer-final` at `6ea7f460e5175d8b4b74a00e3c804a3bc34b9d5f`
  - `temp/runr-production-final` at `58a96674b5cc77bd9da0877d2adaad64abe41b85`

Important integration fact:

- The final LinkedIn collector patch is patch-equivalent to code already in
  the current deployment history.
- The final employer collector patch is still local-only and not integrated
  into the current deployment branch. Its branch and complete history are now
  preserved in the bundle.
- The preserved employer implementation includes direct company-site career
  discovery and native ATS routing for Greenhouse, Lever, Workday, Personio,
  Recruitee, SmartRecruiters, Ashby, Teamtailor, and expansion connectors.
- The preserved LinkedIn implementation uses LinkedIn guest search/detail
  endpoints and the numeric LinkedIn company IDs from the company source CSV.
- All preserved collector entrypoints and final employer connector modules
  passed Python AST syntax parsing.

## VPS and R2 correction

`/srv/runr/state/linkedin/master_linkedin_jobs_state.db` and the corresponding
employer path are deployment contract/default paths. They were not evidence
that the full historical databases were currently present on the VPS.

The live R2 inventory contains only the bounded RC-027 LinkedIn pilot:

- `rc027/checkpoints/linkedin/linkedin-20260909T201035631862Z-e6d35734a371/master_linkedin_jobs_state.db`
- Bytes: `770,048`

No full LinkedIn database, employer database, or enrichment SQLite database
was found under the R2 acquisition/checkpoint/backup prefixes. The RC-024
employer manifest explicitly records `status: not_uploaded`.

## Disappearance evidence

The former `runr-acquisition-snapshots` root is absent and no matching item is
present in the Windows Recycle Bin. The RUN-43/T43 cleanup audit lists nine
specific removed worktrees; the snapshots root is not among them. Therefore
the available evidence does not attribute deletion of the snapshots root to
T43. The exact deletion event remains unknown.

## Readiness

The historical producer databases, exports, company identity/enrichment data,
and collector code are now found and preserved locally. Implementation or a
controlled restore can start from these recovered copies. Promotion to active
VPS state or upload to off-host storage requires a separate authorized restore
operation with immutable backup verification; it was not performed during
this research/recovery pass.
