# OpenCode F — Job Completeness Handoff

- **Workstream:** F (job publication completeness)
- **Contract:** `job_publication_completeness_v1` (see `docs/JOB_PUBLICATION_COMPLETENESS_CONTRACT.md`)
- **Base SHA:** `848408f3024c3c675abb3f8d6696563eb4184c50`
- **Final SHA:** branch tip at handoff (see `git rev-parse HEAD` on `temp/opencode-f-job-completeness`)
- **Branch:** `temp/opencode-f-job-completeness`

## 1. What was delivered

| Artifact | Path |
|---|---|
| Validator + contract constants | `backend/acquisition/job_publication_completeness.py` |
| Source-merging rules | `backend/acquisition/job_source_merging.py` |
| Offline audit command (canonical-job JSONL/CSV) | `scripts/audit_job_publication_completeness.py` |
| Real producer-state audit command (SQLite) | `scripts/audit_real_job_data.py` |
| Sample generator (documented synthetic) | `scripts/generate_completeness_sample.py` |
| Company input profiler | `scripts/profile_company_inputs.py` |
| Tests | `tests/test_job_publication_completeness.py`, `tests/test_job_source_merging.py`, `tests/test_job_completeness_audit.py`, `tests/test_real_job_data_audit.py` |
| Audit evidence | `data/audit/report/completeness_audit.{json,md}` (synthetic) and `data/audit/real/completeness_audit_real.{json,md}` (RC-023 real) |
| Contract doc | `docs/JOB_PUBLICATION_COMPLETENESS_CONTRACT.md` |

All new code lives in **isolated files**; no C-owned publication path was modified.

## 2. The validator API

```python
from backend.acquisition.job_publication_completeness import (
    validate_job_for_publication,
    STATUS_PUBLISHABLE_COMPLETE,
)

result = validate_job_for_publication(
    record,                       # normalized canonical-job mapping
    now=None,                     # optional datetime for staleness/date checks
    company_registry=None,        # optional set[str] of known canonical company IDs
    source_records=None,          # optional sequence of source observations
)
result.publishable               # bool
result.status                    # one of the six statuses
result.reason_codes              # tuple[str]
result.to_dict()                 # {status, publishable, reasons[{code, fields, detail}], ...}
```

The record is a plain mapping shaped like `normalize_job_for_ingestion` output
plus the canonical columns. The validator is alias-tolerant and reads
`canonical_job_id`, `canonical_company_id`/`company_id`,
`company_name`/`employer_name`, `title`, `description_text`/`description`,
`location_raw`/`location`, `application_destination.resolved_url`/`apply_url`,
`source`/`source_ats`, `source_job_id`/`external_job_id`, `observed_at`,
`lifecycle_state`, `posted_at`/`posted_at_estimated`, `closed_at`.

Sentinel values are treated as missing:

- `canonical_company_id` sentinels: empty string, `//`, `UNKNOWN`, `__UNKNOWN__`,
  `__MISSING__`, `__PENDING__`, `__UNRESOLVED__`, `__NOT_FOUND__`, `__NONE__`,
  `__NULL__`.
- Placeholder check is bounded to short values; long descriptions with a stray
  leaked `}}` JSON/HTML artifact are **not** placeholders.
- Identity mode for producer records is `source_derived` because producer state
  does not contain `canonical_job_id`; the validator builds a stable identity
  from `source` + `source_job_id`.

## 3. Exact wiring required from C

The validator is **not wired** anywhere. C owns publication and must add the
gate. Two enforcement points are recommended; the read-time gate alone is
sufficient to protect the customer UI.

### 3.1 Read-time gate (recommended, least invasive)

In `backend/repositories/sqlite_personalized_jobs.py`:

- `list_published_job_rows` (line 1046) and `query_published_jobs` (line 1172)
  already fetch full catalog rows via `_published_jobs_sql()` (line 1369).
- `_published_jobs_sql()` currently does **not** select a per-observation
  `external_job_id`. Add:

  ```sql
  (
      SELECT o.external_job_id FROM job_source_observations o
      WHERE o.canonical_job_id = j.canonical_job_id
      ORDER BY o.observed_at DESC LIMIT 1
  ) AS source_job_id
  ```

- After fetching rows, map each row to the validator shape and filter:

  ```python
  from backend.acquisition.job_publication_completeness import validate_job_for_publication

  def _completeness_record(row: dict) -> dict:
      return {
          "canonical_job_id": row.get("canonical_job_id"),
          "canonical_company_id": row.get("company_id"),
          "company_name": row.get("company"),
          "title": row.get("title"),
          "description_text": row.get("description") or row.get("version_description"),
          "location_raw": row.get("location") or row.get("version_location"),
          "apply_url": row.get("apply_url"),
          "source": row.get("source_ats"),
          "source_job_id": row.get("source_job_id"),
          "observed_at": row.get("observation_observed_at") or row.get("last_verified_at"),
          "lifecycle_state": row.get("lifecycle_state"),
          "posted_at_estimated": row.get("posted_at") or row.get("posted_at_estimated"),
          "application_destination": row.get("version_payload", {}).get("application_destination"),
      }

  rows = [r for r in rows
          if validate_job_for_publication(
              _completeness_record(r),
              now=datetime.now(timezone.utc),
              company_registry=company_registry,
          ).publishable]
  ```

  Pass `company_registry` as `SELECT company_id FROM canonical_companies`
  (or the loaded registry CSV set) so present-but-unknown company IDs are
  rejected.

### 3.2 Write-time gate (optional, publication hygiene)

In `backend/repositories/sqlite_acquisition.py`:

- `publish_valid_snapshot` (line 2137) and `publish_staging_snapshot` (line
  2310) build a **thin** snapshot (`canonical_job_id`, `company`, `title`,
  `location`, `canonical_url`, `apply_url`, `lifecycle_state`,
  `current_version_id`). It does not select description or `observed_at`.
- To gate at write time, enrich the snapshot `SELECT` to include
  `v.description`, the latest `o.external_job_id`/`o.observed_at`, and
  `j.company_id`, then evaluate each row and only `INSERT` publishable rows into
  `acquisition_publication_jobs`. Rejections can be recorded via the existing
  `acquisition_job_rejections` table (reason codes are already the vocabulary).

### 3.3 Policy flag (must be explicit)

`backend/acquisition/publication.py` has a `PublicationPolicy` whose
`completeness_mode` is `"report_only"` and `missing_apply_is_blocker=False`,
with the explicit note that "no new blocker may be activated implicitly."
Register a **new** version (e.g. `publication_policy_v2`) with
`completeness_mode="blocking"` and `missing_apply_is_blocker=True`, and gate on
that policy. Do **not** change the default in place.

## 4. Migration / backward-compatibility

- **No schema migration is required** to enforce the contract: the validator is
  read-only and side-effect free, and the read-time gate operates on existing
  catalog columns (plus the optional `source_job_id` column addition above).
- If C wants a durable completeness decision, add a nullable
  `completeness_status` / `completeness_json` column to `canonical_jobs` (or a
  separate `job_completeness_decisions` table keyed by `canonical_job_id`).
  Persist the decision at write time and reuse it in the read-time gate. This
  is optional and not required for enforcement, but strongly recommended to
  avoid re-evaluating every row on every list/query call.
- Total counts returned by `list_published_job_rows` / `query_published_jobs`
  must be computed **after** the completeness filter is applied, otherwise a
  paginated response will advertise a total that includes non-publishable rows.
- Backward compatibility: records that were previously served but now fail will
  simply stop appearing. If a soft rollout is desired, attach
  `result.to_dict()` to the row (e.g. `row["completeness"] = result.to_dict()`)
  and let the frontend render a degraded card, then switch to hard exclusion
  later. The frontend already renders "Unknown" fallbacks for missing optional
  fields, so only required-field failures need hard exclusion.
- The deleted admin dashboard is not a dependency; enforcement is in the
  repository read path and can be audited via `scripts/audit_job_publication_completeness.py`.

## 5. Source merging note

`backend/acquisition/job_source_merging.py` defines when complementary
LinkedIn + employer observations may form one canonical job. C does not need to
call it for enforcement; the validator's `source_records` conflict detection
and the `uncertain_dedupe_identity` / `unresolved_ownership_conflict` reason
codes cover publication. Merge the module into C's dedupe path only if C wants
to collapse cross-source records at write time.

## 6. Reproduce the audits

### 6.1 Synthetic sample audit (fast)

```powershell
.venv\Scripts\python.exe scripts/generate_completeness_sample.py --count 300 --seed 20260812
.venv\Scripts\python.exe scripts/audit_job_publication_completeness.py `
  --input data/audit/master_jobs_sample.jsonl `
  --company-registry data/acquisition/inputs/company_registry_canonical.csv `
  --output data/audit/report --format both
```

### 6.2 Real producer-state audit (slow; ~10 min, reads a 3.4 GB SQLite file)

```powershell
.venv\Scripts\python.exe scripts/audit_real_job_data.py `
  --linkedin-state "C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc023-20260908\state\linkedin\master_linkedin_jobs_state.db" `
  --employer-state "C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc023-20260908\state\employer\master_employer_jobs_state.db" `
  --company-registry data/acquisition/inputs/company_registry_canonical.csv `
  --output data/audit/real --format both
```

The committed reports are at `data/audit/report/completeness_audit.{md,json}`
(synthetic) and `data/audit/real/completeness_audit_real.{md,json}` (RC-023
real). Real-data results from this workstream:

| Source | Records | Publishable | Dominant blocker |
|---|---|---|---|
| LinkedIn | 188,206 | 42,564 (22.6%) | `missing_canonical_company_id` (145,637; 77.4%) |
| Employer | 2,612 | 63 (2.4%) | `missing_canonical_company_id` (2,018; 77.2%) |
| Combined | 190,818 | 42,627 (22.3%) | `missing_canonical_company_id` (147,655; 77.4%) |

## 7. Test commands and results

```powershell
.venv\Scripts\python.exe -m pytest tests/test_job_publication_completeness.py tests/test_job_source_merging.py tests/test_job_completeness_audit.py tests/test_real_job_data_audit.py -q
```

Result: **53 passed**.

## 8. Ownership boundaries respected

- **D** (LinkedIn), **E** (employer collector), **C** (adapters/publication/
  repositories/scheduler/deployment), **A** (admin removal): none of their
  existing files were modified. Only new, isolated files were added under
  `backend/acquisition/`, `scripts/`, `tests/`, and `docs/`.
- No production/master data was mutated. Company inputs were profiled read-only.
- No large databases or full exports were committed; only code, tests, docs,
  small deterministic sample/report, and a compact real-data audit report.
