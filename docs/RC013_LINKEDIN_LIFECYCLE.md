# RC-013 LinkedIn scan outcomes and job lifecycle

RC-013 hardens the actual LinkedIn catalog producer around scan completeness, ownership, retry disposition and source disappearance.

## Implemented contract

- Search outcomes use validated page evidence instead of a stale job/card counter. A scan that observed cards cannot be finalized as confirmed zero.
- Repeated bodies, malformed or partial pages, challenges, transport failures, request caps and interruptions remain non-complete outcomes.
- Recovery partitions are evidence-bound. A recovery partition with a non-empty page at the pagination cap is recorded as `PARTIAL`; only an explicit terminal no-results page or validated terminal HTTP 400 can complete it.
- Recovery metrics expose required, completed, partial and pending partitions. Scan status counts expose incomplete outcomes without collapsing them into zero.
- Suspicious-empty pages never prove zero inventory, including empty-first and empty-after-nonempty sequences.
- Lifecycle absence is keyed by `(linkedin_company_id, company_scan_id, linkedin_job_id)` and requires two distinct complete scans. Replaying one scan does not add another absence.
- Run and company-scan records persist terminal status and finish time. Detail failures retain bounded retry due times and quarantine after the attempt budget.
- Card/detail ownership requires an exact source mapping or bounded verified-alias evidence. Ambiguous shared organization mappings and unverified aliases remain excluded.
- Legacy consistency audit is read-only and emits explicit scan keys, page evidence and revalidation-required flags before absence expiry can be trusted.

## Focused verification

The focused producer suite in [test_master_linkedin_jobs_catalog.py](../tests/test_master_linkedin_jobs_catalog.py) covers lifecycle replay, legacy audit, explicit zero scans, persistent search failure, retry disposition, suspicious-empty paths, ownership conflict, validated recovery, and non-empty recovery at the cap. It also contains the existing detail-refresh and producer regression coverage used by RC-014.

The repository-required `.venv\Scripts\python.exe` is absent in this worktree. Therefore Python 3.12.7 tests, import checks and fixture execution were not run in this session. `git diff --check` completed without whitespace errors. No network or live provider request was made.

## Rollback

Review and reverse only the RC-013 hunks in `scripts/master_linkedin_jobs_catalog.py` and `tests/test_master_linkedin_jobs_catalog.py`, plus this document. Do not reset or clean the worktree: both files already contain unrelated dirty producer/test work that must remain intact. No external schema or live data migration was performed.
