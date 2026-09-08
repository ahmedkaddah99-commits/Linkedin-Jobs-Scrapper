# Acquisition runtime data inventory

Status: offline reconciliation recorded 2026-09-08.  No live acquisition,
provider request, production migration, database upload, or deployment was
performed.

The deployment branch is `deployment/render-turso-r2`.  RC-022 is preserved at
`39d15b8f3da9870b03102525ed03431194edaad6`; the runtime-data manifest is
[`deploy/acquisition-data-manifest.json`](../deploy/acquisition-data-manifest.json).
The manifest is the server-facing contract.  Windows source paths below are
provenance only and must not be used as VPS runtime paths.

## Git decision

The three immutable company inputs are committed under
`data/acquisition/inputs/`.  They are company-source records, not credentials,
cookies, tokens, or authenticated proxy material.  The reconciled eligibility
manifest and raw sidecar remain external restore artifacts because they are
generated 43 MB/63 MB files and retain the full raw 118-column evidence packet.
Their exact hashes and destination paths are in the machine-readable manifest.

Mutable databases, WAL/SHM files, large catalogs, request logs, browser caches,
and duplicate backups are not normal Git inputs.  They are preserved at their
current source paths and must be copied only as immutable, checksummed restore
artifacts.

## Authoritative seed inputs

| Logical name | Current/source path | Bytes | SHA-256 | Rows/shape | Git/VPS decision |
| --- | --- | ---: | --- | --- | --- |
| Company master | `Company-Urls/Master-Company-Url/Master-Company-Url.csv` | 17,491,851 | `680b4c5cd1fb9309e81f04d8e8ee3b28aba0af154dc70811ca716654231967fc` | 9,129 × 82 | committed as `data/acquisition/inputs/company_master.csv` |
| Canonical registry | `Company-Urls/Master-Company-Url/cleaned/Master-Company-Url-canonical_cleaned.csv` | 11,986,132 | `31ed996ab2b2d0723b00a6634cdcba02901862f95ffb1b2f3c9d8432bb457446` | 17,601 × 42 | committed as `data/acquisition/inputs/company_registry_canonical.csv` |
| Active LinkedIn source input | `Company-Urls/Master-Company-Url/cleaned/Master-Company-Url-canonical_cleaned_linkedin_ids.csv` | 18,807,047 | `7f416ec6ebbcb936a42061ef0adaa07e4a6c04d2959d0eb579779126682440d9` | 17,601 × 118 | committed as `data/acquisition/inputs/company_sources_linkedin_ids.csv` |

The active input is the producer input.  Its 9,682 proposed RC-004 mappings and
37 unresolved shared-organization groups remain review-gated; no mapping was
silently applied by this reconciliation.

## Eligibility packet requiring separate restore

| Artifact | Current path | Bytes | SHA-256 | Role | VPS destination |
| --- | --- | ---: | --- | --- | --- |
| RC-005 reconciled manifest | `SOURCE_ELIGIBILITY_MANIFEST_RC005_RECONCILED.json` | 43,035,445 | `72b61f100a0d9edbba315b5f19db589f40cfecd42c19ce3ef95b78b331621873` | immutable source/task eligibility contract; internal manifest hash `6bfcba5c01985402d2d1278e8b726baa8e4ac3332e6527be40bc433ab663e447` | `/srv/runr/shared/inputs/SOURCE_ELIGIBILITY_MANIFEST_RC005_RECONCILED.json` |
| RC-005 reconciled raw sidecar | `SOURCE_ELIGIBILITY_RAW_RC005_RECONCILED.jsonl` | 63,665,149 | `cda46fee441e2e6e02d52ffe2fc86ae33121c82edc9f0636562367b63cbb5ef7` | 17,601 raw 118-column provenance records required by the manifest wrapper | `/srv/runr/shared/inputs/SOURCE_ELIGIBILITY_RAW_RC005_RECONCILED.jsonl` |

The original RC-005 manifest/sidecar pair is also preserved locally as a
historical generation.  It is not substituted for the reconciled pair.

## Runtime state and catalogs

All state checks below were read-only.  No WAL or SHM file was present beside
the authoritative LinkedIn database, no Python/browser writer process was
running during inspection, and `PRAGMA integrity_check` returned `ok` for the
LinkedIn state, employer state, archived state, and legacy v2 state.

| Logical artifact | Current/source path | Bytes | SHA-256 | Schema/rows | Git/VPS decision |
| --- | --- | ---: | --- | --- | --- |
| LinkedIn authoritative state | `Jobs-Urls/master linkedin jobs url/master_linkedin_jobs_state.db` | 3,479,191,552 | `26b81012177f40949b6b3ede3187860129db9fdaf3392d2195d78ac050244317` | exact 14-table model; `runs` 2, `jobs` 188,206, `search_pages` 52,386, `search_cards` 198,491, `detail_attempts` 198,493, `lifecycle_events` 187,415, `ownership_exclusions` 8,689; integrity `ok` | external immutable restore to `/srv/runr/state/linkedin/master_linkedin_jobs_state.db`; required before acquisition resume |
| Employer state | `Jobs-Urls/master linkedin jobs url/master_employer_jobs_state.db` | 83,841,024 | `b1eee3b449afd075d9b860f12a5880da6769fcc666473bbfe8f08e7e4cb36737` | tables `companies` 428, `jobs` 2,612; integrity `ok` | external immutable restore to `/srv/runr/state/employer/master_employer_jobs_state.db` |
| Archived legacy LinkedIn state | `Jobs-Urls/archive/2026-08-21/linkedin_germany_discovery_state_pre_v2.db` | 2,038,747,136 | `01559b47d6ca0e0e1c8186e8d3de0ebd6fa2214149043c1bfb42f58ceaf9304d` | legacy tables including `query_nodes` 4,675,135; integrity `ok` | external backup only: `/srv/runr/backups/linkedin/` |
| LinkedIn ID-resolution state | `Company-Urls/.../linkedin_id_resolution.sqlite3` | 413,691,904 | `4da05480f291dbdf47c4bbd7988d1da8b79206cb2310332f3f5a32dfba627f2e` | mutable enrichment state; not used for first acquisition start | external restore to `/srv/runr/state/enrichment/`; RC-006b remains pending |
| Legacy v2 state | `Jobs-Urls/linkedin_germany_discovery_state_v2.db` | 116,367,360 | `6e39e6f0733337533a1e78be90dc856d59f43ab242e0c5f0fa79a6722aba2ce5` | legacy 12-table state; integrity `ok` | external historical backup only |

Large generated outputs were also found and checksummed: LinkedIn CSV
774,860,470 bytes (`4adc35fa34cad684deb0d6dcac7f29cbf5a5548c7d7ab2fefe7855a20a898532`),
LinkedIn JSONL 1,005,775,822 bytes
(`847835987d07c263188e160658e8c9a6d12a157d9b952c1e6344b61689ca510f`),
combined `master_jobs.csv` 1,421,822,599 bytes
(`0f5296df28a46a5eab4623334bcf0eca3c40f4f37958359a64a65238077fc2db`),
employer CSV 38,097,370 bytes
(`49bef439521161f0d251dd3e331a4ccb615dd354214b0559baf0e59d8ec16790`),
and employer JSONL 40,036,727 bytes
(`c22d44216006b5b6f4e9fd1115057694e81cb4df9f096a8f3db6ab7027da7811`).  They are reconstructable/visibility exports, not
authoritative resume state, and belong under `/srv/runr/exports/` or backup
storage, not Git.

The 413 MB resolver database was identified as a separate enrichment state,
not the 14-table LinkedIn producer state.  The 2 GB archive is not a migration
source without a separately reviewed conversion.

## Script dependency map

| Script | Classification | Inputs | State | Outputs | VPS requirement |
| --- | --- | --- | --- | --- | --- |
| `scripts/master_linkedin_jobs_catalog.py` | canonical 14-table producer | active 118-column input; manifest-gated source rows | LinkedIn state | generation CSV/JSONL, metrics, lifecycle state | acquisition worker |
| `scripts/master_employer_jobs_catalog.py` | canonical employer producer | active input; manifest-gated source rows | employer state | employer CSV/JSONL/metrics | acquisition worker |
| `scripts/run_manifested_linkedin.py` | production wrapper | reconciled manifest + raw sidecar | LinkedIn state | manifest input + LinkedIn outputs | scheduled LinkedIn entrypoint |
| `scripts/run_manifested_employer.py` | production wrapper | reconciled manifest + raw sidecar | employer state | manifest input + employer outputs | scheduled employer entrypoint |
| `scripts/build_master_jobs_catalog.py` | publication builder | validated LinkedIn and employer exports | none | combined catalog + generation manifest | daily publication step |
| `scripts/audit_employer_coverage.py` | read-only audit | employer state | employer state | coverage report | operations/recovery only |
| `scripts/run_linkedin_company_id_resolution.py` | supporting enrichment | canonical registry input | resolver state | approved output copy/reports | not first-start; RC-006b gated |
| `scripts/linkedin_company_enrichment_pipeline.py` | supporting parser/resolver | explicit input and state paths | resolver state | enrichment reports/output copy | not first-start; no live run here |
| `scripts/build_source_eligibility_manifest.py` | offline manifest builder | immutable source CSV and review reports | none | manifest + raw sidecar | release/data preparation only |
| `backend/acquisition/producer_adapters.py` | supporting adapter | producer results | application acquisition repository | normalized observations | API/worker integration |

The separate `scripts/master_linkedin_jobs_url_catalog.py` remains a legacy
nonproducer compatibility implementation.  It is not the scheduled producer
and must not replace the 14-table script.

## Restore contract

Transfer artifacts out of band only after review.  Example commands are
provided, not executed:

```bash
install -d -m 0750 /srv/runr/shared/inputs /srv/runr/state/linkedin /srv/runr/state/employer /srv/runr/state/enrichment /srv/runr/exports /srv/runr/backups/linkedin
rsync --protect-args --checksum /reviewed-bundle/SOURCE_ELIGIBILITY_MANIFEST_RC005_RECONCILED.json /srv/runr/shared/inputs/
rsync --protect-args --checksum /reviewed-bundle/SOURCE_ELIGIBILITY_RAW_RC005_RECONCILED.jsonl /srv/runr/shared/inputs/
rsync --protect-args --checksum /reviewed-bundle/master_linkedin_jobs_state.db /srv/runr/state/linkedin/
rsync --protect-args --checksum /reviewed-bundle/master_employer_jobs_state.db /srv/runr/state/employer/
sha256sum /srv/runr/shared/inputs/SOURCE_ELIGIBILITY_MANIFEST_RC005_RECONCILED.json /srv/runr/shared/inputs/SOURCE_ELIGIBILITY_RAW_RC005_RECONCILED.jsonl /srv/runr/state/linkedin/master_linkedin_jobs_state.db /srv/runr/state/employer/master_employer_jobs_state.db
RUNR_ACQUISITION_INPUT_ROOT=/srv/runr/shared/inputs RUNR_ACQUISITION_STATE_ROOT=/srv/runr/state python deploy/validate_acquisition_runtime.py --role all --deep
```

The restore operator must stop the acquisition owner before replacing a state
file, preserve the prior snapshot, verify hashes and schema, then start one
owner.  Do not copy WAL/SHM files independently.  Provider secrets belong only
in the service environment or a root-readable secret file; no secret values
are part of this inventory.

## Excluded local data classes

The remaining source checkout contains temporary smoke outputs, duplicate
backups, raw provider evidence, resolver transport caches, unbounded logs,
browser artifacts, and local product storage.  They remain untouched and are
classified as external evidence, reconstructable output, disposable cache, or
sensitive material.  In particular, the feature-branch commit `0d7f2b5c`
captured 654 mixed files, including mutable SQLite WAL/SHM files and large
company-enrichment data; it is not merged wholesale.
