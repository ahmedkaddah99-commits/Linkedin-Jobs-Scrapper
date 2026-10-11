# Admin operations console parity checklist

Implementation source: `RUNR_ADMIN_OPERATIONS_CONSOLE_IMPLEMENTATION_PACKAGE.zip` reviewed against production base `8d10ff7f792452e1789768e26bdbb1a95a641d92`.

- [x] One responsive `AdminOperationsShell`; admin routes bypass the consumer `AppShell`.
- [x] Canonical grouped navigation and command palette match the supplied route map.
- [x] Existing overview, analytics, acquisition, quality, release, provider, events, promotions, and access API contracts remain wired.
- [x] Legacy Acquisition, analytics, job-import, and ScrapeOps URLs redirect safely.
- [x] Job, company, and import detail URLs are directly addressable.
- [x] Loading, stale/partial, empty, forbidden/error, and session-unavailable states retain the shell.
- [x] Keyboard focus, Escape-close, focus return, mobile drawer, and reduced-motion behavior are implemented.
- [x] No prototype fixture data, Next/Vinext runtime, Cloudflare runtime, or prototype dependency was imported.
- [x] No provider, AI, budget, publication, import, reconciliation, enrichment, reprocessing, or duplicate action runs automatically.
- [x] Local viewport evidence is recorded at 1440×900, 768×1024, and 375×812.
- [ ] Production viewport evidence and authenticated route smoke results are recorded during release verification.
