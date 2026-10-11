# Phase G Applicant-Intelligence Audit And Implementation Boundary

Status: **BLOCKED — no applicant-intelligence source is approved for production**
Date: 2026-08-07
Branch: `feat/phase-g-applicant-intelligence`
Policy: `phase_g_applicant_intelligence_v1`

## Decision

No inspected source can currently be documented as both legitimately authorized and reliably capable of supplying every required applicant-intelligence field. No applicant source is activated in production.

The existing sources remain ordinary job-acquisition sources only. Applicant data is not inferred from job volume, ranking position, search filters, or a portal label. Candidate identities and application data are out of scope and are not collected.

## Source decision matrix

| Source | Exact count/range | Posting time/freshness | Application method | Job-specific official employer/ATS Apply destination | Observation timestamp | Unattended behavior and cost | Decision |
|---|---|---|---|---|---|---|---|
| LinkedIn guest/portal connector | Applicant text may be visible in some portal views, but no repository evidence establishes a stable, authorized field contract | Listing output has partial posted text; not audited as a freshness contract | Connector returns a portal listing/apply link; destination is not consistently established as official employer/ATS | Not proven for every record | Connector request time is available operationally, but source-field contract is not approved | Repository report records LinkedIn terms risk, documented ScrapeOps cost of 70 credits/request, and a 403 banned-account probe | **BLOCKED: authorization, reliability, and cost risk** |
| Indeed portal / ScrapeOps Indeed Data API | Not proven in the current connector contract | Search filters and posted text are not an applicant-intelligence freshness contract | Not consistently proven as an official employer/ATS destination | Not proven for every record | Request time is available operationally | Repository report records terms/automation uncertainty, account-level 403 rejection, zero observed rejected-request credits, and unverified Data API billing | **BLOCKED: authorization and billing/quality gaps** |
| Other job portals (Glassdoor, StepStone, ZipRecruiter, Careerjet, etc.) | No audited exact/range applicant field contract | No audited freshness contract | Portal links are not canonical employer identity or proof of official Apply destination | Not proven | Request time is available operationally | ScrapeOps-backed paths have per-mode cost but no source-specific authorization or unattended-use decision | **BLOCKED** |
| Bundesagentur für Arbeit | No applicant count/range field in the direct structured connector | Structured posting fields and request time are available | Detail records can provide a job URL; applicant-count contract is absent | Not an applicant source | Direct observation time is available | Direct JSON control is low-cost/uncosted in the repository report; endpoint/API-key usage still needs production legal/operational review | **Not an applicant source** |
| Greenhouse public Job Board API | Structured jobs only; no applicant count/range field | `updated_at` is available and can be observed | Job-specific `absolute_url` is an official ATS destination when Phase B host checks pass | Yes for ordinary job acquisition; no applicant count | Direct request/observation time is available | Public structured endpoint; direct request cost is recorded as zero ScrapeOps credits in the existing validation path | **Not an applicant source** |
| Lever published postings API | Structured postings only; no applicant count/range field | `createdAt` is available and normalized | `hostedUrl`/`applyUrl` is an ATS destination when Phase B host checks pass | Yes for ordinary job acquisition; no applicant count | Direct request/observation time is available | Public structured endpoint; direct request cost is recorded as zero ScrapeOps credits in the existing validation path | **Not an applicant source** |
| Generic employer career sites / detected Workday, Personio, Recruitee, SmartRecruiters | No applicant-count contract in the implemented connectors | Varies by site and is not audited as a source contract | ATS routing can establish ordinary Apply destinations for supported hosts | Sometimes, but not uniformly | Request time is available | Direct/ATS-first and ScrapeOps fallback costs are policy-dependent; no applicant source authorization or field audit exists | **Not an applicant source** |

The source evidence is in [the scraping strategy report](../scraping_strategy_report_2026-05-26.md), [the ATS router](../../backend/connectors/ats_router.py), [Phase B normalization](../../backend/acquisition/phase_b.py), and [the Phase A manifest](../../backend/acquisition/manifest.py). The repository also records that public legal pages/terms work was incomplete in [the website discovery report](../runr-website-discovery.md).

## Credentials and network posture

`user_config/.env` declares ScrapeOps and other provider keys locally; their values were not read into this report. The current process environment does not enable `RUNR_ACQUISITION_LIVE_NETWORK_ENABLED`. Phase A manifest targets are disabled and publication is disabled by default. Credential presence is not authorization, and a provider key is not permission to collect applicant data.

No live portal request was made for this audit. The existing repository evidence records ScrapeOps Proxy/Indeed probes as account-rejected (`403 Banned Account`) with zero rejected-request credits observed. That is an operational finding, not source authorization.

## Implementation boundary

The repository already had a latent `job_applicant_snapshots` table and an incomplete Phase G prototype. This change makes the boundary explicit without activating a source:

- `PHASE_G_PRODUCTION_ACTIVATED = False`; target configuration cannot override it.
- `applicant_source_gate()` requires a documented source decision, authorization, data-quality, request-cost, unattended-behavior, timestamp, official-Apply, and no-candidate-data evidence. Current decisions remain blocked.
- Ordinary job ingestion may continue, but applicant evidence from a blocked source is not written to applicant snapshots.
- Quick Apply, Easy Apply, portal-only, and email-only jobs remain rejected by Phase B before enrichment. A portal target without an explicit canonical employer is rejected; its display name cannot become an employer or user-facing source label.
- Applicant snapshots are append-only. Exact values use `exact`; bounded or lower-bounded values use `min`/`max` plus the original explicit label; absent values remain unknown. A valid observation timestamp is required.
- First/latest observation is derived from the append-only rows. Observation age and stale state are derived from the latest observation. Stale competition is neutral in ranking.
- Internal provenance includes source ATS, source provenance, provenance URL, and official Apply URL. The snapshot payload is an allow-list and cannot retain candidate identities or application data.
- Replay is idempotent through the existing unique `(target_id, cycle_id, external_job_id)` source observation and unique snapshot `source_observation_id`, with a deterministic snapshot ID derived from that observation.
- Free users retain normal catalog access and both match scores. Exact/range applicant intelligence, change history, competition ranking, and advanced freshness remain Pro-gated. Missing applicant data is neutral, not zero applicants.

## Snapshot schema

Migration `037_phase_g_applicant_competition` creates the table. Migration `041_phase_g_applicant_boundary` adds explicit `apply_url` and `source_provenance` fields and preserves the unique observation index.

| Field | Semantics |
|---|---|
| `snapshot_id` | Deterministic append-only row ID derived from source observation |
| `canonical_job_id` | Canonical posting only; never a candidate identity |
| `source_observation_id` | Internal source observation and replay key |
| `source_ats`, `source_provenance`, `provenance_url` | Internal provenance; portal names are not user-facing canonical employer labels |
| `applicant_count_exact` | Exact count only when explicitly supplied |
| `applicant_count_min`, `applicant_count_max`, `applicant_count_label` | Explicit range/lower-bound representation without precision fabrication |
| `posting_time` | Source-supplied posting/published time; blank remains unknown |
| `first_seen_at`, `last_verified_at`, `observed_at` | Observation lifecycle timestamps |
| `apply_method`, `apply_url` | Source-declared method and job-specific official Apply destination |
| `freshness_status` | `fresh`, `aging`, `stale`, or `unknown` |
| `payload_json` | Sanitized evidence allow-list only; no raw connector payload |

## Ranking and stale-data model

Formula version: `phase_g_priority_v1`

`priority = 0.60 * user_fit + 0.20 * freshness + 0.20 * competition`

Each component is normalized to 0–100. Missing fit, missing freshness, missing applicant count/range, or stale competition uses neutral `50`; no missing count is converted to zero applicants. Competition uses the explicit exact count or the lower bound of an explicit range only. The SQL ordering expression and response payload use the same version and weights.

## Cost model

The current ScrapeOps policy constants are: Basic 1 credit/request, cheap JS 5, JS 10, residential 10, and JS residential 25. The repository report separately records a documented LinkedIn rate of 70 credits/request and says Indeed Structured Data billing was not established. Direct Greenhouse/Lever/Arbeitsagentur requests are not charged ScrapeOps runner credits in the existing controls, but legal/operational approval is still required before unattended production use. No applicant-source budget is reserved because no applicant source is approved.

Before any future activation, the source owner must document native and runner cost, failed-request billing, rate/concurrency limits, cache/retry policy, expected daily volume, and an explicit unattended-request approval. A provider API key alone does not satisfy this gate.

## Verification

Added/updated tests cover:

- exact, bounded, and lower-bounded applicant parsing;
- hard-disabled applicant-source activation;
- safe unknown snapshots with no candidate payload retention;
- neutral missing competition and formula-version output;
- free/Pro projection behavior and Pro priority formula;
- portal employer identity rejection;
- existing Phase B rejection and acquisition persistence contracts.

The required interpreter is Python 3.12.7. Targeted verification passed:

```text
17 passed
```

Full verification and the final commit SHA are reported with the handoff.

## Activation blockers

Status remains **BLOCKED** until all of the following exist as reviewed artifacts for one named source:

1. Written authorization or a sanctioned API/data-access agreement covering unattended requests.
2. A field-level quality contract proving exact/range applicants, posting freshness, application method, official Apply URL, and observation timestamp.
3. Provider billing and request-limit evidence, including failed-request cost.
4. A source-specific no-candidate-data guarantee and payload allow-list review.
5. A replay/staleness test fixture and production owner sign-off.

Until then, applicant snapshots are schema and test boundary only; no applicant source is activated in production.
