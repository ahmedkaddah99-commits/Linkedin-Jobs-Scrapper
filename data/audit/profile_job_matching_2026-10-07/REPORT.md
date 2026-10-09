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

Focused tests cover profile/CV independence, separate users, alias boundaries and negation, required/preferred skills, overlapping dates, unknown fields, settings round trips, stale versions and concurrent queue revisions. Desktop/mobile Playwright covers card-only loading, lazy detail requests, breakdown/evidence, employer links, absence of embedded originals, back navigation and viewport overflow. Validation passed: 32 focused backend tests, 173 frontend unit tests, two Playwright projects and a production build. A further 14 feed performance/security checks passed after legacy-sort fallback was retired. The final detail-read change passed 26 profile, feed and asynchronous-intelligence backend tests; legacy endpoint assertions were updated to the saved-profile contract. Independent detail reads overlap through four bounded threads.

Reliability here means deterministic, reproducible, source-linked and conservative handling of unknowns. Human-labelled calibration has not been completed. The reviewed skill/industry ontology has finite coverage; unsupported extraction can yield partial assessments. Seniority bands and related-industry credit are explicit product rules, not a learned model. Education, licence and legal eligibility are not included in this three-dimension percentage. Original sources remain available through the employer link.

Deployment verification is recorded in `deployment-verification.json` beside this report after the release and VPS backfill are checked.


## Filled-profile checks

The owner requested population from the selected uploaded CV. The saved profile now contains 22 competencies, four work experiences with converted source periods as month dates, and two education entries. Existing parsed CV data was reused; no extra AI call was needed. The CV did not establish an explicit industry, which remains unknown. Only the account profile JSON was changed; uploaded files and other account metadata were preserved. The previous profile was backed up locally outside Git.

A browser regression fills a fictional QA profile with Power BI and three dated years of analyst work in Insurance. The actual Python evaluator produces Experience 100%, Skill 67%, Industry 50%, Overall 72%. Saving Python as another skill changes Skill to 100% and Overall to 83%. Both desktop and mobile pass. This test exposed and fixed loss of unsaved profile fields when switching tabs. Source-backed production job checks are recorded in `live-profile-job-test.json`; incomplete assessments are labelled Partial assessment rather than Strong match.

During rollout, competing enrichment/publication writes produced 30-second Turso write timeouts. A controlled matching batch completed 100 jobs in 3.86 seconds after quiescing competing writes. Initial backfill uses a controlled pause of description/publisher writes; normal timers and description concurrency are restored after coverage is verified. A temporary description cap was removed. This is separate from the evaluator CPU benchmark. Live end-to-end detail reads in the first production sample took approximately 5?8 seconds, so that sample does not establish a sub-second HTTP latency claim.

The final owner-profile production-data sample took 4.3?4.9 seconds per detail service call from the local operator machine. This includes remote repository reads and is not a browser-to-Render latency measurement. One posting supplied no established matching dimensions; three supplied partial skill assessments (100%, 14%, 50%). None supplied supported industry evidence.

## Final rollout evidence

API, frontend and Render worker are live at `0f0a81b29c580633c05df0f2c4843aee90821da8`; the VPS matching release has the same commit. API readiness confirms Turso and R2 configuration. The initial published backfill drained, with 33,840 facts stored. A version/hash/source-signature audit during resumed enrichment established 33,830 current facts out of 33,840 published jobs (99.97%). Ten jobs changed during that audit. Normal matching, publication and description timers are restored; description concurrency is 32.

**Remaining production limit:** concurrent acquisition/enrichment writes still produce Turso write timeouts. Matching work remains durably queued and retries, and stale facts are withheld. This rollout does not establish sustained full coverage or the requested fast end-to-end behavior under concurrent writer load. That database contention needs further production remediation; it is not hidden by the CPU benchmark or successful profile tests.
