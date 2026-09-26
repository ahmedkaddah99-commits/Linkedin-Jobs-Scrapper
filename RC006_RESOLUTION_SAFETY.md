# RC-006a — Offline resolver safety evidence

Status: **complete offline** on 2026-09-06.

Target worktree: `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview`
Target branch: `deployment/render-turso-r2`
HEAD at validation: `e7662c63082d605d8ae6de090d3a04a55bba6556`
Required interpreter: `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe`
Verified version: **Python 3.12.7**

This evidence completes the offline RC-006a slice only. RC-006b (authorized
enrichment expansion) was not started. RC-007 was not started.

## Files

- `backend/application/company_enrichment_resolution.py` — independent queue classification, evidence precedence, stable fingerprints, durable retry/budget/circuit safety.
- `scripts/run_linkedin_company_id_resolution.py` — accumulated contextual-ID history, explicit reconciliation decisions, safety admission around resolver transports, retry-due selection, and report fields.
- `tests/test_rc006_resolution_safety.py` — offline acceptance tests.
- `tests/fixtures/rc006_mostly_blocked.json` — deterministic blocked/recovery sequence.
- `RC006_RESOLUTION_SAFETY.json` — machine-readable version of this record.

Existing dirty exporter, employer-producer, and LinkedIn-producer changes were
preserved. No producer file was edited for this ticket.

## Implemented safety contract

The queues remain independent: a row may need canonical-ID, website, and
numeric-LinkedIn-ID work at the same time. Ownership conflicts are explicit.
Evidence merging protects user-confirmed values and reports conflicting values
for review instead of silently downgrading or replacing them.

The resolver now records every contextual ID observed in a response history.
Same-response multi-ID evidence remains `AMBIGUOUS`. If one response contains
IDs 111 and 222 and a later response contains only 111, the accumulated result
remains `AMBIGUOUS`; it cannot become `RESOLVED` without a recorded reviewer
reconciliation decision.

Resolver safety is stored in a separate SQLite database under the resolver
state directory. It persists per-URL/provider attempts, next eligible retry
time, rolling request reservations, conservative ScrapeOps credit usage, and
provider circuit state. Admission is transactional, so worker count or proxy
count cannot bypass the global/provider ceilings. A circuit admits one bounded
recovery probe after its open interval.

Per-group source evidence receives a stable fingerprint based on normalized
URL and canonical-ID evidence, not source row number. Reordering rows therefore
does not restart unchanged completed identity work; changed identity evidence
remains detectable. Repeated retry runs select only due failures.

## Verification commands and results

```powershell
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' --version
# Python 3.12.7

& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m pytest tests/test_acquisition_baseline.py tests/test_company_registry_reconciliation.py tests/test_company_id_backfill.py tests/test_source_eligibility_manifest.py tests/test_linkedin_company_id_browser_resolution.py tests/test_linkedin_company_enrichment_pipeline.py tests/test_producer_adapters.py tests/test_rc006_resolution_safety.py -q
# 66 passed in 15.88s

& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m ruff check backend/application/company_enrichment_resolution.py scripts/run_linkedin_company_id_resolution.py tests/test_rc006_resolution_safety.py
# All checks passed!

& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m py_compile backend/application/company_enrichment_resolution.py scripts/run_linkedin_company_id_resolution.py tests/test_rc006_resolution_safety.py
# exit code 0

git diff --check
# no diff errors; existing line-ending warnings were emitted while reading status
```

The tests made **zero network calls**. They cover independent queues, evidence
protection, contradictory sequential IDs, same-response multiple IDs, explicit
reconciliation, producer ownership grouping, restart-persistent cooldown and
credit ceilings, circuit opening, recovery probing, and the mostly-blocked
fixture's request bound.

The full repository test command was started as a diagnostic but was not used
as the gate: it is much larger than this acquisition slice and showed failures
outside the bounded command before it was stopped; no trace was retained. The
bounded acquisition/resolver command above is the recorded RC-006a gate.

## Limitations and deferred work

- No live HTTP, proxy, browser, ScrapeOps, paid enrichment, provider-quota, or deployment test was performed.
- RC-006b remains deferred because it requires explicit authorization for bounded provider checks.
- Actual provider limits, live costs, and current source coverage remain unverified.
- No production database or input CSV was modified.

## Rollback

1. Stop any resolver process.
2. Back up the resolver state directory, including `linkedin_id_resolution.sqlite3` and `resolver_safety.sqlite3`.
3. Reverse only the RC-006 hunks in `scripts/run_linkedin_company_id_resolution.py`; preserve its earlier RC-001 transfer and all dirty exporter changes.
4. Remove the RC-006 module, fixture, test, and evidence files only if the ticket artifacts must be withdrawn.
5. Do not delete resolver results or request logs. Restore the backed-up state directory if state rollback is required.

No rollback was performed.
