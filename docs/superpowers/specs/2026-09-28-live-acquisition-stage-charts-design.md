# Live acquisition stage charts — design

## Purpose and approved scope

The owner needs to see real job volume over time, split by LinkedIn versus employer-site collection, location and the **collection pipeline stage**: collected → detailed → imported → published. This is an operational diagnostic view: it should reveal where jobs stop moving without loading individual jobs into Grafana or consuming enrichment credits. “Location” means city; show the top ten cities plus Other and Unknown. The owner manually refreshes the browser when needed. Underlying aggregates must continue to be produced from current data, not screenshot numbers or hardcoded values.

This change improves the existing [Runr Data Pipeline Overview](https://pluckyhovercraft81.grafana.net/d/runr-data-pipeline). It does not change source eligibility, scraping, paid enrichment, publication rules, daily timers, request limits, or backup behavior.

## Approach

Use the existing VPS observer and Grafana Cloud Metrics path. A read-only, bounded aggregator computes counts server-side from the active LinkedIn and employer SQLite producer states and the shared Turso catalog. Grafana receives only numeric aggregates with bounded labels. This keeps the existing authenticated infrastructure and avoids adding a public analytics endpoint. Querying raw jobs from every Grafana panel is rejected: it would duplicate heavy reads, increase cost, and expose row-level data. Using only current Prometheus inventory gauges is also insufficient: it cannot reconstruct stage transitions or location history.

The aggregator produces **two complementary views** per source, deliberately not mixing their meanings:

1. **Current funnel snapshot:** distinct job identities known at each stage now. This answers “where is the backlog?” Stage counts are cumulative membership, not mutually exclusive buckets; a published job was also collected. Show counts and conversion percentages without stacking stage totals.
2. **Dated progress:** daily counts of first entry into each stage, using persisted event timestamps where they exist. This answers “what actually moved on each day?” Historical bins are backfilled from durable records; missing dates remain Unknown, not assigned to today. New daily bins refresh as new records arrive. A separate live history of funnel snapshots begins only at installation and is labelled as such.

Avoid claiming that a change in total inventory is the number collected that day. Show the latest successful aggregate timestamp and section status beside every source. If a source query fails, retain the last good count with its old timestamp and mark the section failed; never silently replace it with zero.

## Counting contract

| Stage | LinkedIn evidence | Employer evidence | Time basis |
|---|---|---|---|
| Collected | Distinct LinkedIn job IDs in persisted search-card evidence, plus restored job records that have no retained card | Distinct employer source keys in producer jobs | Earliest durable card/first-seen event, if known |
| Detailed | Distinct LinkedIn job IDs with a successful persisted detail/job payload | Distinct employer source keys with a usable normalized payload; employer collection may combine discovery and detail, so this is explicitly labelled “usable details” | First successful detail/first-seen timestamp if present; otherwise Unknown |
| Imported | Distinct source identities linked to canonical jobs by source observations | Same | First relevant canonical source observation timestamp; mark historical imported date unavailable if only a later observation survives |
| Published | Distinct canonical jobs in the current publication head, attributed to a source through its observation evidence | Same | Current-head membership for snapshot; publication history for dated first publication only where membership evidence survives |

All stage counts identify jobs **within a source**. A job collected from both LinkedIn and an employer site can appear once in each source view; it is not two distinct global jobs. For imported/published source attribution, a canonical job with observations from both sources is counted once per source, never inferred from a job title or company name. No source attribution means an explicit Unknown-source aggregate, not a guessed LinkedIn or employer count. First-seen and latest-seen are separate; collection on a later scan is not a new first-collected job.

The exact producer schema and timestamp coverage must be validated against the live recovered stores before coding the event queries. If historical card, detail, import or publication evidence is absent, the chart must show **Unknown date / unavailable history**, not a reconstructed event that did not happen. Historical publication snapshots are not the current published set.

## Location contract

Use the job posting location captured at the stage, not company headquarters. Normalize obvious city aliases consistently across both sources; retain raw location only in the source store. Multi-city, remote-only and ambiguous location strings go to Unknown unless a defensible city can be extracted. A missing location never becomes a German city by default. Choose the ten leading cities by current detailed-job volume across the selected source; put all other valid cities into Other. This is a bounded dashboard grouping, not a permanent change to canonical job location. A city label is an allowlisted aggregate value; no free-form location, job ID or company ID becomes a Prometheus label.

Historical city groups can change if the top-ten ranking changes; document that the dated chart is grouped by the **current** top-ten set. The all-cities total is computed before grouping and must equal the sum of top ten, Other and Unknown for each source/stage/date. Distinct jobs are deduplicated **before** aggregation.

## Dashboard design and refresh

Put two immediately readable sections near the top: “LinkedIn jobs” and “Employer-site jobs”. Each has a four-stage funnel, a dated stage-flow chart, a city-by-stage breakdown and a conspicuous source-data freshness indicator. Use exact count tooltips/axis values; compact `k` may be displayed only if the exact number is available on hover or adjacent text. The current dashboard’s dense inventory tables move lower, as diagnostic detail. Source-specific charts do not accidentally inherit provider or readiness filters that change their denominator.

Set dashboard automatic browser refresh to Off. Its time range and filters remain user-controlled. The observer may refresh its aggregate cache on its existing five-minute schedule; Alloy continues shipping the latest metrics. Browser refresh does not initiate a scrape, paid API call, or raw-row fetch. Label the distinction “Data updated at” versus “Dashboard viewed at”. The current 1-minute browser auto-refresh must be removed. A manual refresh should show the latest successfully produced aggregates after normal ingestion delay; it cannot make the underlying five-minute cache instantaneous.

Daily history should be kept bounded in Prometheus (initially 90 days of UTC buckets and a fixed stage/source/city vocabulary). Older recoverable history may be summarized by month or shown as a separate bounded backfill; it must not create unbounded metric labels. Grafana should query only aggregate series. Any chart whose data has not yet been produced must say “unavailable” with reason rather than display a plausible zero.

## Efficiency and safety

- Read source SQLite files with read-only/query-only connections and the correct active state paths; read the shared Turso catalog without migrations or writes.
- Aggregate by indexed identifiers/dates where possible. Add no large in-memory row export and no per-job time-series labels. Confirm query plans, runtime, and peak memory on the actual VPS before leaving the recurring collector enabled.
- Use a checkpoint or short-lived cached daily summary so the five-minute observer does not rescan 188,000 source jobs and the remote catalog in full on every run. Refresh changed partitions and periodically reconcile totals. A failed reconciliation must surface a health/error signal.
- Preserve the collector’s bounded memory/timeout controls and keep the backup, LinkedIn, employer and publisher timers untouched.
- Do not use company-enrichment API credits or Webshare proxies for telemetry.

## Verification and acceptance

Tests cover deduplication, cross-source attribution, stage membership, time-bucket semantics, top-ten/Other/Unknown reconciliation, incomplete historical evidence, stale section behavior, and dashboard refresh Off. Run them under Python 3.12.7 in the project venv. Compare source-aggregate totals against read-only live queries and the existing inventory metrics; investigate any disagreement rather than silently adjusting counts. Verify every new Grafana query returns a live series where data exists, the chart names/axes match the counting contract, the dashboard is readable at desktop size, and the VPS observer remains within its memory/time bounds. Confirm all four existing operational timers remain enabled and active after deployment.

Success means the owner can open the Grafana dashboard, see separate LinkedIn and employer charts with genuine current counts, dated movement, city/stage breakdown and freshness, and tell whether a slowdown is in collection, detail completion, import or publication. Gaps in recoverable historical evidence must be explicit rather than hidden by “real-time” styling.
