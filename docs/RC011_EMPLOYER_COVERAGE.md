# RC-011 employer coverage and truthful zero outcomes

RC-011 keeps the employer collector’s existing checkpoint statuses for compatibility while adding canonical outcomes:

| Canonical outcome | Existing stored status | Meaning |
| --- | --- | --- |
| `complete_with_jobs` | `completed` | Complete source evidence and accepted jobs. |
| `confirmed_zero` | `no_jobs` | Complete source/pagination evidence and no accepted jobs. |
| `partial` | `partial` | Jobs or source evidence exist, but the source was capped, interrupted, or otherwise incomplete. |
| `failed` | `source_failed` | The source did not produce usable evidence. |
| `unsupported` | `source_failed` | Detected source has no supported adapter and no usable fallback evidence. |
| `blocked` | `source_failed` | Challenge, bot protection, or equivalent access block. |
| `skipped` | `skipped_resume` | A bounded resume/recheck budget intentionally deferred work. |

Each persisted company result now carries `coverage` with detected ATS, discovered targets, extraction methods, counts, stop reason, completeness evidence, and a recheck policy. Each target carries the same evidence at source level.

Fallback rules are conservative: a nonempty ATS/HTTP result suppresses browser fallback only when the snapshot is complete. Timeouts, challenges, parser errors, failed details, pagination caps, and generic responses without explicit completeness evidence cannot produce `confirmed_zero`.

Resume rechecks historical `no_jobs`, `discovery_failed`, `partial`, and `source_failed` rows. The `--recheck-budget` option bounds those rechecks per run. A legacy `completed` checkpoint remains resumable for compatibility, but it is not evidence that the full master list was covered.

## Historical migration disposition

The plan’s existing 428 company-state records are accounted for as follows:

- 194 `no_jobs`: bounded recheck; no historical negative is trusted without completeness evidence.
- 146 `discovery_failed`: re-run discovery and persist source coverage.
- 82 `partial`: resume/revalidate from checkpoint.
- 5 `source_failed`: recheck with explicit failure/blocked/unsupported outcome.
- 1 `completed`: retain accepted jobs and timestamps, but do not use it as proof of master-list coverage.
- 2,612 existing observations: preserve original rows, timestamps, and provenance while revalidating; uncertain parent scans do not delete them.

Run the read-only audit against a local state database with:

```powershell
.venv\Scripts\python.exe scripts\audit_employer_coverage.py `
  --state-db path\to\master_employer_jobs_state.db `
  --output RC011_EMPLOYER_COVERAGE_AUDIT.json
```

The repository worktree has no target `.venv\Scripts\python.exe` and no local employer state database was available for this session, so this audit command was not executed here. It performs no network access and does not write to the state database.

Rollback: restore `scripts/master_employer_jobs_catalog.py`, `scripts/audit_employer_coverage.py`, `tests/test_rc011_employer_outcomes.py`, and this document from the worktree. Existing employer state rows and job observations are append/upsert-preserved; no destructive migration is required.
