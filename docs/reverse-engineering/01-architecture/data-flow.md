> Source: deployment/render-turso-r2 | SHA: 58a96674 | Verified: 2026-09-14

# Cross-subsystem data flow (WS-12 synthesis)

Secondary to [../00-overview.md](../00-overview.md). This traces one record from acquisition to the customer, citing the owning workstream doc at each hop rather than re-describing its internals.

## 1. Acquisition → per-source state

VPS systemd timers (owned by WS-7, [../02-deployment/vps-runtime-and-acquisition-timers.md](../02-deployment/vps-runtime-and-acquisition-timers.md)) invoke `scripts/run_manifested_linkedin.py` / `scripts/run_manifested_employer.py`, which drive the LinkedIn and employer producers (`backend/acquisition/**`, `backend/connectors/**`, owned by WS-3, [../05-subsystems/acquisition-and-collectors.md](../05-subsystems/acquisition-and-collectors.md)). Each producer writes to its own SQLite state store (`backend/repositories/sqlite_acquisition.py`) and CSV/export artifacts under `data/acquisition/` — never directly into the customer-facing catalog.

- **Gate:** `RUNR_ACQUISITION_LIVE_NETWORK_ENABLED` is intended to gate live network access, but WS3-G1 records that the producers themselves do not check it (only the systemd unit sets it); this is a confirmed static-analysis gap, not a live-run observation.
- **Company inputs:** `data/acquisition/inputs/*.csv` (company master, registry canonical, LinkedIn IDs) are read as seed inputs, per the Phase-1 delta audit correction (N-3) — they are not generated output.

## 2. Identity canonicalization and enrichment

`backend/application/company_identity_canonicalization.py` and the `company_enrichment`/`company_logo` services (WS-3, [../05-subsystems/company-identity-enrichment-and-logos.md](../05-subsystems/company-identity-enrichment-and-logos.md)) reconcile producer-reported company names/URLs against the company registry before publication. `backend/enrichment/**` exists as a foundation package but WS3-G11 records it has no runtime consumer at the baseline — enrichment here is a dormant capability, not an active production step, until an owner decision integrates or retires it.

## 3. Publication → catalog

`scripts/publish_producer_states.py`, `backend/acquisition/publication.py` and `backend/acquisition/job_publication_completeness.py` (WS-3, [../05-subsystems/publication-and-catalog.md](../05-subsystems/publication-and-catalog.md)) read the per-source state, apply the completeness gate and the company-identity crosswalk, and write into the shared catalog store. Two dormant paths noted there: `publication_policy_v2` is registered but has no live call site (WS3-G7), and `job_source_merging.merge_source_records` has no runtime call site in the publication path (WS3-G8) — cross-source merge today is observation-level only.

## 4. Catalog storage

The catalog lives in Turso/libSQL in production and SQLite locally, via one connection abstraction (`backend/database/**`, `backend/repositories/sqlite_migrations.py`), owned by WS-5 ([../03-data/schema-and-migrations.md](../03-data/schema-and-migrations.md), [../03-data/turso-and-libsql.md](../03-data/turso-and-libsql.md)). Migrations are append-only (001–060 at the baseline); **C3** records that the release-time migration head pin (`058_customer_task_queue`, in `render.yaml` and `release_contract.py`) is stale relative to the registry head (`060_publication_latest_observation_index`), with no code that gates on the mismatch — a metadata discrepancy, not a demonstrated runtime failure.

## 5. Catalog → customer API → frontend

`backend/api/server.py` and its route registry (WS-1, [backend-api.md](backend-api.md)) expose the catalog and customer-scoped resources (personalized jobs, runs, artifacts, evidence) over HTTP, authenticated by Clerk bearer tokens (WS-6, [security-and-auth.md](security-and-auth.md)). The React frontend (WS-8, [frontend-app.md](frontend-app.md)) renders `/jobs` as the customer-facing view. The pre-retirement customer `/dashboard` route now redirects to `/jobs` (`frontend/src/App.jsx:229`); its backend payload builders are unreachable dead code, not a live surface — see §5 of [../00-overview.md](../00-overview.md) and [../06-history-and-provenance/retired-features.md](../06-history-and-provenance/retired-features.md).

## 6. Application services and Assisted Apply

Customer-triggered work (tailored CV/cover-letter generation, tracker sync, Assisted Apply preparation) runs through `backend/application/**` services (WS-4, [../05-subsystems/personalized-jobs-and-customer-app-services.md](../05-subsystems/personalized-jobs-and-customer-app-services.md)) and the lease-based worker (WS-2, [backend-workers-and-orchestration.md](backend-workers-and-orchestration.md)). Prepared application packages can be consumed by the Assisted Apply browser extension (WS-9, [../05-subsystems/assisted-apply.md](../05-subsystems/assisted-apply.md)), which fills employer forms up to but never through a terminal submit action — the never-submit boundary is enforced independently of this data flow, at the extension's runtime guard and build-time boundary scan.

## 7. Cross-cutting concerns

- **Billing:** Creem webhooks/checkout (WS-6, [security-and-auth.md](security-and-auth.md) §Billing, [../05-subsystems/billing-and-creem.md](../05-subsystems/billing-and-creem.md)) gate paid features independently of the acquisition→catalog pipeline.
- **Object storage:** generated documents (tailored CVs, evidence bundles) go to R2 via an S3-compatible API (WS-5, [../03-data/object-storage-r2.md](../03-data/object-storage-r2.md)), not through the catalog database.
- **Telemetry:** the only live writer of `analytics_events` at the baseline is worker-side (`backend/adapters/stage_adapters.py`, run events and ScrapeOps usage). The HTTP ingestion path and the customer `/dashboard` analytics payload are unreachable (§5 of [../00-overview.md](../00-overview.md)).

## 8. What is not shown here

Deployment mechanics (Render build/deploy, VPS systemd topology, Docker images, CI) are cross-cutting infrastructure, not data flow — see [../02-deployment/](../02-deployment/). Every contradiction and unknown referenced above by ID is defined once, canonically, in [../06-history-and-provenance/known-gaps.md](../06-history-and-provenance/known-gaps.md); this doc does not duplicate those tables.
