# VPS job descriptions

## Objective

Every published posting version has one shared, readable Runr description in English. The VPS acquisition role generates it from the preserved employer posting. The customer API only reads it. The job page offers Runr description and Original job post tabs. Candidate matching is outside this change.

## Processing

1. A VPS timer invokes a bounded processor after publication. It scans the current publication in stable job-ID order for versions lacking the current description prompt version.
2. The processor sends up to five full postings per request through OpenRouter's free Nemotron model in JSON mode, with reasoning disabled so visible output fits the token budget. It requires exact posting-version IDs and a fixed JSON shape covering overview, responsibilities, required qualifications, preferred qualifications, benefits, application details, source language, and source excerpts. It stores the model and writes each result to the existing `job_description_intelligence` table keyed by posting version. A failed provider call never writes a deterministic substitute.
3. The timer can be run repeatedly to backfill and then process new versions. The existing posting remains published while descriptions are prepared. Metrics report scanned, completed, and failed counts without posting text.
4. The customer API looks up the stored version and hash from Turso. It exposes the Runr description and preserved original; it never calls the model in a GET handler. The VPS service uses the shared Turso production catalog, not its local acquisition SQLite catalog. It is limited to 45 requests per day (up to 225 postings) to stay within the OpenRouter free-tier allowance. On 2026-10-01, the customer catalog had 35,359 published jobs, of which 9,880 had no description source. Processing the remaining 25,479 takes at least about 114 days if every request succeeds and the catalog does not grow. Jobs lacking source text require upstream acquisition repair.

## Presentation

The default Runr tab uses one reading column. It shows the overview and all extracted nonempty sections. The Original tab renders preserved text/HTML. Both share the existing job header and application actions. If processing is pending, the Runr tab says so and links to the original tab.

## Deployment

Test against local fixtures, then stage an exact Git revision on the VPS. Install this additive worker in `/opt/runr-description-worker/current`, separate from the active `/opt/runr` acquisition release, so existing collectors and publisher keep their selected code. Configure the free-model key and shared Turso credentials in `/etc/runr/description.env` with restricted permissions; this file overrides the local SQLite setting in `.env.acquisition`. Run a bounded canary against Turso, inspect receipts, then run the backfill until all current contentful published versions have the current prompt version. Deploy the API/frontend revision and verify live job pages. Do not roll live services from an uncommitted worktree.
