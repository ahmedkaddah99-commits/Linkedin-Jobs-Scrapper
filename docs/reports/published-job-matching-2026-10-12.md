# Published job matching, 12 October 2026

Runtime commit `4833d433b5ca10aec3aaee5585ec35a44fd71262` is deployed to
`/srv/runr/releases/matching-4833d433`. Its archive SHA-256 is
`cd2b05756343ea8a419b3f1631e5a350482a456a7d2e2ecc2e14f2daa0bb7a7f`.
Only the matching service's next-invocation working directory was changed.
No acquisition, publication, enrichment or customer service was stopped.

The existing `profile_match_v1` evaluator calculates personal percentages from
the saved account profile. Skills use source-supported required/preferred
weights, experience uses relevant dated work and seniority, and industry uses
explicit profile/company evidence. Overall is the mean of established
dimensions. Partial or unknown evidence remains labelled accordingly; a match
percentage is not a hiring probability. Profile edits take effect on the next
customer request without stale stored personal scores.

The matching companion runs every 30 seconds after its prior invocation ends.
It projects up to 4,096 jobs per invocation and now reconciles up to 1,000
missing/stale published queue entries. Concurrent queue revisions remain fenced.
The API rejects stale facts. No AI provider is involved in match calculation.

## Verification

- Eleven focused evaluator, queue reconciliation and acquisition-to-customer
  lifecycle tests passed.
- A live audit found **16,698 current facts out of 16,698 published jobs: 100%**.
  This is a snapshot while acquisition and enrichment remain active; subsequent
  source changes can temporarily queue recalculation.
- The new worker completed 4,096 projections in 41.861 seconds, with zero
  provider calls and a successful systemd exit. Its new reconciliation receipt
  reported zero missing queue entries in that run.
- The matching, acquisition and AI timers remain active. API readiness confirms
  SQLite and R2. Browser acceptance remains with the user.

The read-only `deploy/verify-published-job-matching.py` audit evaluates every
captured publication member against every nonempty saved account profile using
the actual serving application's evaluator. It exposes only aggregate outcomes,
never account identities, profile text or credentials.

The completed full audit captured 17,032 published jobs and evaluated all of
them against three nonempty saved profiles in 319.65 seconds, with zero provider
calls. During this moving audit, 16,974 facts were current (99.66%) and 58 were
temporarily pending. Profiles produced 3,658 / 3,662 / 3,658 numeric percentages,
all partial assessments (about 21.5%). The remaining 13,316 / 13,312 / 13,316
assessments lacked sufficient evidence. None established all three dimensions.
This proves full-catalog evaluator execution, not full evidence completeness.
Enrichment and explicit saved-profile evidence must improve before those
unknown dimensions can support complete percentages.
