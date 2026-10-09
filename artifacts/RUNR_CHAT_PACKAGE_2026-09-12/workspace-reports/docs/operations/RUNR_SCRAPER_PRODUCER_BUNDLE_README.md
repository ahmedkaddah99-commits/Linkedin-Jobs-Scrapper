# Runr scraper producer source bundle

This bundle contains the source used by the canonical LinkedIn and employer-career-site producers, their production wrappers, the combined catalog builder, supporting acquisition/connectors code, deployment contracts, and focused tests.

The preserved output evidence is separate and intentionally excluded because it contains multi-gigabyte mutable state and large exports. Its locations and counts are recorded in `SOURCE_INVENTORY.md` inside this bundle.

## Entry points

- `scripts/master_linkedin_jobs_catalog.py` — canonical LinkedIn producer.
- `scripts/master_employer_jobs_catalog.py` — canonical employer-career-site producer.
- `scripts/run_manifested_linkedin.py` — production LinkedIn wrapper.
- `scripts/run_manifested_employer.py` — production employer wrapper.
- `scripts/build_master_jobs_catalog.py` — combined source-preserving projection.
- `scripts/master_linkedin_jobs_url_catalog.py` — retained legacy URL-catalog implementation for historical comparison; it is not the canonical producer.
- `scripts/publish_producer_states.py` — bridge from producer state to Runr acquisition storage.

## Secrets and mutable state

No `.env` file, provider credential, proxy credential, SQLite state database, browser profile, or large job export is included. Restore those separately using the paths and safeguards in the deployment manifest.

