# Jobs feed read cost correction

Authorized outcome: require at least one Job Function before customer feed retrieval, query an indexed function candidate set, avoid exact-total scans in customer pagination, and deploy/sync all runtimes.

1. Add migration 070_job_function_lookup: compact version/function membership, indexed by normalized function; backfill existing classification metadata only. Insert/update/delete triggers maintain roles and hashes without rewriting memberships on unrelated metadata updates.
2. Add repository role-scoped reads and optional totals. Start SQL from indexed functions, deduplicate selected functions, verify current version/hash/publication, apply existing filters only to those candidates, and hydrate the requested page. Customer feed omits totals. Internal catalog tools retain their explicit contracts.
3. Enforce Job Function selection at the HTTP feed boundary through the service. Return a selection-required empty state before catalog lookup. Keep detail and hidden-job routes usable. Avoid global capability scans in this query mode.
4. Gate the frontend feed and pagination on a selected function; show a selection prompt and loaded count. Preserve named saved filters and all existing filters.
5. Verify regressions, query plans and live Hrana row counters; review; commit and fast-forward the shared deployment branch without touching the user's REPORT.md edit. Apply the exact migration/checksum, deploy Render and VPS, keep all protected timers enabled, verify release and health.

Verification: missing function issues no catalog query; role lookup updates/delete/staleness; multi-role deduplication; additional filters; page continuity; no COUNT in customer-page SQL; indexed query plan; focused Python, full API and frontend checks; live first/subsequent page reads and zero query writes.
