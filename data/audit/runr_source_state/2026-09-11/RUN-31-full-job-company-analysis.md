# RUN-31 Full Job and Company Data Analysis

**Evidence date:** 2026-09-11

**Scope:** every row in the authoritative historical producer-state tables,
plus every row represented in the audited canonical/Turso readiness report.

**Important freshness note:** the source SQLite files used for this audit are
not present at their documented local path in the current workspace, so this
file reports the latest verified historical evidence. It does not claim a
fresh live/VPS re-read on 2026-09-19.

## 1. Direct answer

The historical LinkedIn producer database did contain **188,206 job rows** and
**188,206 job-company observations**. The audit recorded SQLite integrity as
`ok`, zero duplicate LinkedIn source job IDs, and a 3,479,191,552-byte database
with SHA-256
`26b81012177f40949b6b3ede3187860129db9fdaf3392d2195d78ac050244317`.

However, the full 188,206-row producer database was **not** fully copied into
the canonical publication database. The canonical/Turso audit contained only
**299 canonical jobs**, of which **93** passed the then-current validator; the
current publication head contained **47** jobs. Therefore:

- Source storage: verified historically for 188,206 LinkedIn jobs.
- Canonical catalog ingestion: incomplete; only 299 jobs were represented in
  the audited canonical tables.
- Current publication head: valid but only 47 jobs, not the full producer
  corpus.

## 2. All producer-state jobs

These totals come from a read-only audit of every row in LinkedIn
`job_company_observations` and employer `jobs`.

| Source | Total rows | Publishable/unblocked | Not publishable/blocked | Publishable rate | Distinct source IDs | Duplicate IDs |
|---|---:|---:|---:|---:|---:|---:|
| LinkedIn | 188,206 | 42,564 | 145,642 | 22.6% | 188,206 | 0 |
| Employer sites | 2,612 | 63 | 2,549 | 2.4% | 2,440 | 172 |
| **Combined** | **190,818** | **42,627** | **148,191** | **22.3%** | **190,646** | source-specific |

“Publishable/unblocked” means `publishable_complete` under the historical
`job_publication_completeness_v1` audit. It does not mean that those jobs were
already in the canonical publication head.

### LinkedIn reasons

| Outcome/reason | Jobs or reason occurrences |
|---|---:|
| Publishable complete | 42,564 |
| Unresolved identity | 145,637 |
| Invalid outcome | 5 |
| Missing canonical company ID | 145,637 |
| Insufficient description | 466 occurrences |
| Blocked/error description body | 51 occurrences |
| Easy Apply marker `true` | 631 |

The reason rows are not additive: one job can have multiple reason codes. The
dominant blocker is the unresolved/sentinel company ID (`//`), affecting
145,637 jobs, or 77.4% of LinkedIn rows. All 188,206 rows used a LinkedIn job
view URL as the mapped application URL, so the historical 42,564 pass count
was provisional with respect to direct-application URL policy.

### Employer-site reasons

| Outcome/reason | Jobs or reason occurrences |
|---|---:|
| Publishable complete | 63 |
| Unresolved identity | 2,018 |
| Missing required outcome | 487 |
| Invalid outcome | 41 |
| Placeholder outcome | 3 |
| Missing canonical company ID | 2,018 |
| Missing location | 1,911 |
| Missing description | 1,404 |
| Insufficient description | 72 occurrences |
| Blocked/error description body | 3 occurrences |
| Placeholder title | 1 occurrence |
| No explicit application URL; job-detail fallback only | 1,663 |

These reason rows also overlap. The 172 duplicate source-job-ID occurrences
must be reconciled before treating the employer corpus as a clean unique set.

## 3. All canonical/Turso jobs

The separate canonical readiness audit reported:

| Canonical layer | Total | Publishable/unblocked | Blocked/not publishable |
|---|---:|---:|---:|
| All canonical jobs | 299 | 93 | 206 |
| Current publication head | 47 | 47 | 0 |

Canonical-job blockers were:

| Reason | Jobs |
|---|---:|
| Listing-fallback application URL | 186 |
| Missing description | 46 |
| Closed lifecycle | 35 |
| Missing location | 22 |
| Insufficient description | 6 |

Those reason counts overlap. The latest acquisition cycle was `degraded` with
`partial_source_coverage`, observed/new/published counts of `0/0/47`, so the
47-job head represented existing state rather than a complete replay of the
188,206 LinkedIn rows.

## 4. All company records and company readiness

There are three different company populations; they must not be conflated:

| Company population | Total | Ready/unblocked | Not ready/blockers |
|---|---:|---:|---|
| Canonical companies in the audited database | 1,428 | 1,428 identity-ready | 0 identity blockers |
| Canonical companies with selected primary URL | 1,428 | 1,379 | 49 missing selected primary URL |
| Canonical companies with profile + verified logo | 1,428 | 893 | 525 missing verified logo; 2 missing company profile |
| Registry input rows | 17,601 | Not equivalent to stored canonical companies | Registry is an input, not proof of catalog ingestion |

Companies referenced by publishable producer-state jobs were much smaller
subsets: **1,235 LinkedIn companies** and **4 employer-site companies**.
Companies referenced by the current 47-job publication head: **2**.

Company blocker counts are field-level counts and may overlap. In particular,
missing logo/profile/presentation data is distinct from missing canonical
identity. The full producer-state blocker is mostly a **job-to-company identity
bridge** problem: 147,655 combined producer jobs lacked a usable canonical
company ID.

## 5. Storage and database conclusion

### Verified historical source storage

- LinkedIn state: 3,479,191,552 bytes; 188,206 `jobs` rows and 188,206
  `job_company_observations` rows; integrity `ok`.
- Employer state: 83,841,024 bytes; 428 company rows and 2,612 job rows;
  integrity `ok`.
- Both databases were documented as external immutable restore artifacts, not
  Git-tracked files.

### Not proven in the current workspace

The documented source path
`C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots` is absent from
the current machine state, and the SQLite files are not in this repository.
Consequently, this session could not independently rerun `PRAGMA integrity_check`
or verify the current VPS/Turso contents. The report proves what the 2026-09-11
audit observed, not that those files are still mounted or active today.

## 6. T32 contract freshness caveat

The counts above were generated under the historical `v1` audit and before the
owner clarification was applied to the full source corpus. The clarified T32
contract makes company logo, company enrichment, seniority, employment type,
and workplace arrangement blocking; salary and benefits remain non-blocking.
The updated validator was tested against fixtures, but a fresh 188,206-row
source audit could not be run because the authoritative SQLite snapshot is not
available in this checkout. Therefore **42,564 LinkedIn and 63 employer
publishable counts are baseline counts, not final post-T32 counts**.

## Evidence files

- Full producer audit JSON: `data/audit/runr_source_state/2026-09-11/rc023-authoritative/completeness_audit_real.json`
- Full producer audit Markdown: `data/audit/runr_source_state/2026-09-11/full_source_state_audit_report.md`
- Canonical/Turso audit JSON: `data/audit/runr_readiness/2026-09-11/audit_summary.json`
- Canonical/Turso audit Markdown: `data/audit/runr_readiness/2026-09-11/audit_report.md`
- Job remediation queue: `data/audit/runr_readiness/2026-09-11/jobs_readiness.csv`
- Company remediation queue: `data/audit/runr_readiness/2026-09-11/companies_readiness.csv`
- Runtime inventory and source hashes: `docs/ACQUISITION_RUNTIME_DATA_INVENTORY.md`
