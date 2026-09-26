# RC-015 LinkedIn transport and storage safety

The LinkedIn producer now bounds transport work and publishes catalog artifacts as immutable generations.

## Implemented contract

- Webshare sessions are reused per worker/proxy identity and closed at run end; proxy credentials are excluded from diagnostics and health rows.
- The adaptive limiter gates actual request entry, tracks account/provider in-flight work and backs off on rate limits, blocks and server failures.
- Retry attempts, proxy cooldowns and proxy health counters are recorded at transport level.
- SQLite writes use small transactions; acknowledged catalog batches roll back together on failure. CSV export streams from a cursor rather than materializing the catalog.
- Event JSONL is written inside the generation directory. A manifest hashes CSV, JSONL and metrics, and one atomic pointer selects the coherent generation; compatibility aliases are copied only after the pointer target is complete.
- Detail provider credits/cost are recorded when the transport reports them; otherwise the metrics explicitly retain an unknown/not-reported state.

## Focused verification

The focused producer suite covers shared limiter in-flight bounds, session reuse and closure, proxy cooldown/health persistence without credentials, transaction rollback, typed JSONL output, retry transport attempts and generation pointer/hash validation. Runtime execution remains pending because the repository-required `.venv\Scripts\python.exe` is absent. No network or live provider request was made.

## Rollback

Reverse only the RC-015 transport, generation-publication and focused test hunks in `scripts/master_linkedin_jobs_catalog.py` and `tests/test_master_linkedin_jobs_catalog.py`, plus this document. Preserve unrelated dirty files and producer changes. No external schema or live data migration was performed.
