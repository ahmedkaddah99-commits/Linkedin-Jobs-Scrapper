# Profile-based job matching implementation ? 2026-10-07

Runr now shows full-width job cards with a percentage, opens a dedicated overview on click, and links directly to the employer posting. The original employer description is no longer rendered in the Jobs workspace. Filter selections survive the card/detail round trip. Desktop and mobile screenshots in this directory are synthetic visual fixtures, not measured matching accuracy.

## Source of truth

Matching reads the authenticated account's saved `metadata.profile` through a dedicated account repository query that does not hydrate CV assets or documents. A whitelist contains professional skills, competencies, role, work history, industries, projects, education and languages. Identity/contact data, uploaded CVs, tailored documents and search preferences do not enter the scoring snapshot. Settings normalization now preserves work descriptions, industries and dates. Each request reads the current profile; a saved profile edit affects the next response without a background user/job recomputation.

## Exact calculation

`profile_match_v1` replaces the customer V1/V2 comparison. This is Runr's documented provisional rubric; Jobright's proprietary formula and exact weights were not available. The reference screenshot's 100/54/49 breakdown would produce 68% under this rubric, not Jobright's displayed 72%.

- **Skill:** source-supported required skills carry weight 2 and preferred skills weight 1. Percentage = supported weight / established job-skill weight ? 100, rounded. Reviewed English/German aliases match equivalent names; explicit negations do not establish support. Profile skills and actual work/project descriptions supply evidence. Unknown job skills produce an unknown dimension.
- **Experience Level:** work qualifies by substantive title overlap or overlapping job skills. Dated relevant intervals are merged so concurrent roles count once. Years coverage is capped at 100%; explicit title seniority or conservative dated-work bands establish level coverage. When both are known, the lower coverage is used. Undated/unsupported experience stays unknown rather than becoming invented years.
- **Industry Exp.:** explicitly saved profile/work industries are compared with source/company industries. Direct alignment receives full credit, documented related-domain alignment half credit, and an established mismatch zero. Employer names do not establish candidate industry. Missing industry information stays unknown.
- **Overall:** arithmetic mean of established dimensions, rounded. Partial assessments show how many of three dimensions are established. Strong match ?80%; good match ?60%. A percentage estimates rubric fit; it is not an interview probability.

Every detail dimension is expandable and explains its evidence. All users use the same evaluator; profile data remains scoped to the authenticated user. Historical document-generation matching remains separate from the customer job percentage.

## Acquisition/VPS lifecycle and speed

Migration `073_profile_job_facts` creates shared version/hash-bound facts and a durable revisioned queue. Publication changes, new posting versions, description/filter enrichment and company updates enqueue affected versions. The one-time migration backfills existing current versions. No profile information reaches this worker. Migration `074_profile_matching_industry_invalidation` adds an index for company-to-current-version lookups and invalidates company-derived facts only when industry changes. Unrelated profile/logo updates do not cause catalog-wide queue churn.

A dedicated `runr-profile-job-facts.timer` runs the bounded provider-free worker every 30 seconds after its previous run finishes. Each invocation handles up to 4,096 jobs or 180 seconds in bulk batches of 100; each batch uses a single guarded bulk insert and acknowledgement rather than per-row database commits. Only the industry fields needed for scoring are transferred from large company/posting payloads. A flock prevents overlap, with 512 MB and one-core limits. The isolated release directory leaves collector/publisher and existing description-worker deployments intact. Race guards check posting hash, enrichment signature and queue revision before persisting; changed input cannot acknowledge newer work. API reads reject stale facts until refreshed.

Cards perform one bulk fact read per page and local scoring, without loading job descriptions or calling an AI provider. Company and hidden-job feeds also use bulk facts. The obsolete CV-based Most suitable sort is removed; chronological and competition sorts remain. This release does not claim a globally profile-ranked catalog.

Synthetic 25-job scoring benchmark, 100 samples: median 36.24 ms, 95th percentile 69.01 ms, zero provider calls. This measures evaluator CPU time, not end-to-end HTTP latency or Turso transport.

## Validation and operating limits

Focused tests cover profile/CV independence, separate users, alias boundaries and negation, required/preferred skills, overlapping dates, unknown fields, settings round trips, stale versions and concurrent queue revisions. Desktop/mobile Playwright covers card-only loading, lazy detail requests, breakdown/evidence, employer links, absence of embedded originals, back navigation and viewport overflow. Validation passed: 31 focused backend tests, 173 frontend unit tests, two Playwright projects and a production build. A further 14 feed performance/security checks passed after legacy-sort fallback was retired.

Reliability here means deterministic, reproducible, source-linked and conservative handling of unknowns. Human-labelled calibration has not been completed. The reviewed skill/industry ontology has finite coverage; unsupported extraction can yield partial assessments. Seniority bands and related-industry credit are explicit product rules, not a learned model. Education, licence and legal eligibility are not included in this three-dimension percentage. Original sources remain available through the employer link.

Deployment verification is recorded in `deployment-verification.json` beside this report after the release and VPS backfill are checked.
