# RC-012 employer concurrency and request accounting

RC-012 adds bounded concurrency to the independent employer collector while keeping SQLite writes in the coordinator thread.

## Runtime contract

- Default company workers: `2`.
- Default pending company futures: `4`, clamped to at least the worker count and at most `100`.
- Default HTTP attempts: `4` concurrent.
- Default browser processes: `1` concurrent.
- Default shared account attempts: `4` concurrent.
- Default per-origin attempts: `1` concurrent.

All limits are CLI/configurable: `--company-concurrency`, `--max-pending`, `--http-concurrency`, `--browser-concurrency`, `--account-concurrency`, and `--per-origin-concurrency`. These are safety bounds, not claims about provider/account capacity; RC-002 baseline evidence is still required for tuning.

Each worker creates and closes its own HTTP sessions. A shared `TransportGate` limits actual direct HTTP attempts, proxy fallback attempts, browser navigation/resource requests, account-wide work, and per-origin work. The main thread alone calls `EmployerState.save`, so SQLite connections are not shared across workers. Completed futures are checkpointed as soon as they finish; a stalled company does not hold completed results in an unbounded queue.

Metrics now include `request_accounting` with total attempts, fallback attempts, browser navigations, peak in-flight work, transport/kind/origin counts, and the effective concurrency configuration. The top-level `requests` value comes from actual transport attempts, not job counts or inferred target counts.

On interruption, already checkpointed results remain durable; pending futures are cancelled where possible and resume replays companies without a saved checkpoint. Employer export remains a final atomic step after all scheduled work completes.

## Verification

Focused tests cover a delayed company with an independently checkpointed fast company, direct-plus-proxy attempt accounting, and protection against job-count-derived request metrics in [test_rc012_employer_concurrency.py](../tests/test_rc012_employer_concurrency.py).

The repository `.venv\Scripts\python.exe` is currently absent, so Python 3.12.7 tests and deterministic benchmark execution were not run in this session. No network or live benchmark was performed. The implementation is ready for the required offline test/benchmark once the repository virtual environment is restored.

Rollback: revert the RC-012 changes in `scripts/master_employer_jobs_catalog.py`, `backend/connectors/employer_site_fallbacks.py`, `tests/test_rc012_employer_concurrency.py`, and this document. No schema or state migration was added; existing checkpoints and employer artifacts do not need data rollback.
