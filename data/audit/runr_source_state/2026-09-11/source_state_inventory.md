# Source-state inventory used for the full audit

Audit date: `2026-09-11`

## Authoritative full-corpus files

| File | Absolute path | Size |
|---|---|---:|
| LinkedIn producer state | `C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc023-20260908\state\linkedin\master_linkedin_jobs_state.db` | 3,479,191,552 bytes |
| Employer producer state | `C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc023-20260908\state\employer\master_employer_jobs_state.db` | 83,841,024 bytes |
| Canonical company registry | `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\data\acquisition\inputs\company_registry_canonical.csv` | 17,601 canonical company rows |

The source-state audit opened the SQLite files read-only and evaluated every row in `job_company_observations` for LinkedIn and every row in `jobs` for employer sites.

## Pilot/restored files excluded from the full-corpus count

These files are only `770,048` bytes each and were not used as the historical full-corpus source:

- `C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc027-20260909\restored-linkedin\master_linkedin_jobs_state.db`
- `C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc027-20260909\restored-from-r2-linkedin\master_linkedin_jobs_state.db`
- `C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc027-20260909\offhost-linkedin\offhost-linkedin-20260909\master_linkedin_jobs_state.db`

## Known source hashes

These hashes are recorded in the Runr RC-C handoff:

- LinkedIn: `26b81012177f40949b6b3ede3187860129db9fdaf3392d2195d78ac050244317`
- Employer: `b1eee3b449afd075d9b860f12a5880da6769fcc666473bbfe8f08e7e4cb36737`

## Authority references

- Runtime inventory: `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\docs\ACQUISITION_RUNTIME_DATA_INVENTORY.md`
- Completeness contract: `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\docs\JOB_PUBLICATION_COMPLETENESS_CONTRACT.md`
- Migration/source transcript: `C:\Users\ahmed\.codex\attachments\0383ee05-fb65-451e-9a36-ed608b63fda5\pasted-text.txt`
