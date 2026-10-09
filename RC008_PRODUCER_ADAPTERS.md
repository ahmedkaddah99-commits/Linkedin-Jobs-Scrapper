# RC-008 — Adapt both producers to a shared observation contract

Status: **complete offline** on 2026-09-07.

Target worktree: `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview`
Target branch: `deployment/render-turso-r2`
HEAD at validation: `e7662c63082d605d8ae6de090d3a04a55bba6556`
Required interpreter: `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe`
Verified version: **Python 3.12.7**

The adapter implementation was already present in preserved dirty worktree
changes. It was audited and validated in this turn. Neither the employer nor
LinkedIn producer implementation was edited.

## Files

- `backend/acquisition/producer_adapters.py` — source-specific state adapters, observation contract, bounded batches, idempotent fake transport, and SQLite acquisition transport.
- `tests/test_producer_adapters.py` — fake employer ATS and real LinkedIn parser/state paths, field preservation, unknowns, bounded batches, replay, and source separation.
- `tests/test_observation_store_integration.py` — SQLite acquisition transport receipts, final snapshot controls, raw contract retention, partial/zero-source handling, and idempotency.
- `RC008_PRODUCER_ADAPTERS.json` — machine-readable evidence.

## Acceptance evidence

`SourceObservation` includes canonical employer mapping, source, source job ID,
source URL, apply URL/type, scope, cycle and scan IDs, observed timestamp,
content hash, schema version, source record, and normalized mapping. Missing
values remain explicit `unknown` values.

LinkedIn metadata retains ownership status, Easy Apply status, applicant count,
source-company IDs/names/URLs, run/scan/endpoint/transport evidence, and raw
producer data. Employer observations retain ATS tenant/provider, career target,
discovery, extraction, endpoint, transport, collection status, and geography
evidence.

Adapters stream from durable producer state rather than depending on either
CSV export. Batches are bounded. Batch IDs, observation IDs, idempotency keys,
and fake-transport receipt IDs are deterministic. Replaying a batch returns the
same receipt and counts a duplicate without adding a second logical record.

The adapter export surface now names the actual `SOURCE_EMPLOYER` and
`SOURCE_LINKEDIN` constants, so wildcard imports do not expose undefined names.

`SqliteAcquisitionTransport.send()` is explicitly intermediate and never
closure-safe. `send_final()` requires an explicit complete source inventory and
rejects missing IDs, invalid snapshots marked closure-safe, and observations
outside the declared inventory.

## Verification commands and results

```powershell
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' --version
# Python 3.12.7

& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m pytest tests/test_producer_adapters.py tests/test_observation_store_integration.py -q
# 7 passed in 5.83s

& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m ruff check backend/acquisition/producer_adapters.py tests/test_producer_adapters.py tests/test_observation_store_integration.py
# All checks passed!

& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m py_compile backend/acquisition/producer_adapters.py tests/test_producer_adapters.py tests/test_observation_store_integration.py
# exit code 0
```

The tests use temporary SQLite databases and synthetic/mocked transport. Network
calls: **0**.

## Limitations and rollback

- No live HTTP, proxy, browser, provider, credential, deployment, or production-state check was performed.
- End-to-end normalization/publication belongs to RC-009 and is not claimed here.
- No producer implementation was changed.
- The target worktree has no commit isolating RC-008 from other user-owned dirty changes.

Rollback:

1. Stop adapter delivery and acquisition workers.
2. Back up the acquisition database and source-specific state databases.
3. Reverse only the adapter changes in `backend/acquisition/producer_adapters.py`; do not reset or restore producer files.
4. Preserve source observations/raw payloads, disabling only the adapter call site if needed.
5. Restore backed-up state only for an explicit state rollback.

No rollback was performed. Stop after RC-008; RC-009 is the next ticket boundary.
