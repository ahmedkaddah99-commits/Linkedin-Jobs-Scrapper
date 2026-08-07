# Phase I offline production-rollout acceptance report

Status: **not complete — production approval and live evidence are pending**

## Scope and implementation lineage

This is an offline/code acceptance record. It is not a live acquisition,
publication, or production-evidence report.

- Phase I reconstruction baseline: `5a91380`.
- Deployment baseline reviewed during recovery: `182d51f`.
- Later admin job-import dashboard work is outside this report's evidence
  scope and does not make Phase I complete.

## Offline acceptance

- Python interpreter: `.venv\Scripts\python.exe`, Python 3.12.7.
- State machine proof: preflight → one-source controlled production → staging
  publication → internal cohort → selected cohort → source expansion → daily
  scheduler → pro checkout → complete.
- Circular gate fixed: the controlled-source transition enables one source and
  controlled validation before measured/productive evidence is required for
  staging publication.
- Flags are enabled incrementally. Global scheduler and publication remain
  disabled during controlled-source validation.
- Direct bounded probes do not escalate empty employer results to ScrapeOps.
  Repeated credible empty probes quarantine after the manifest request cap.
- Daily-window claim is durable and idempotent; a second worker cannot claim
  the same window, and a later window can be claimed after a miss.
- Evidence endpoint: `GET /admin/acquisition/cycles/{cycle_id}/evidence`.
- Evidence includes cycle/window, deployment commit, target URL/host, request
  rows, redirects, status, latency, reserved/actual credits, monetary cost
  basis, job counts, rejection reasons, yield/cost, no-submit official Apply
  validation, and publication head before/after.

## Verification recorded at acceptance time

- Passing focused rollout/acquisition suite: 21 tests.
- Ruff and backend bytecode compilation: passed.
- Full Python collection: 1,176 tests collected.
- Full Python run exceeded the 120-second command timeout without a reported
  failure; that timeout is not evidence of a passing full run.
- An unrelated provider-boundary test remained failing because it expected
  Gemini while the current worktree routed that path through DeepSeek; no live
  request was allowed.

## Required production approval packet

The following is a proposed first-cycle packet. It has not been executed.

| Cycle | Target | URLs/hosts | Max requests | Credits/cost | Mode | Database/publication |
|---|---|---|---:|---:|---|---|
| 1 | Qonto Lever | `https://jobs.lever.co/qonto`; `api.lever.co` | 1 direct | 0; $0 configured | direct only; no ScrapeOps | production Turso/libSQL acquisition DB; staging only; public head unchanged |
| 2 | N26 Greenhouse | `https://job-boards.greenhouse.io/n26`; `boards-api.greenhouse.io` | 1 direct | 0; $0 configured | direct only; no ScrapeOps | same; staging only; public head unchanged |
| 3 | Siemens, BASF, Bosch, DHL, adidas | manifest request URLs; their individual HTTPS hosts | 1 direct each | 0; $0 configured | bounded direct probe only; no ScrapeOps fallback | same; no publication |

Applicant-data portals are excluded from this packet and require separate
Phase G approval.

Rollback/kill switch: set `acquisition.phase_a.kill_switch=true`; keep
`acquisition.phase_a.scheduler_enabled=false`,
`acquisition.phase_a.global_enabled=false`, and
`acquisition.phase_i.production_publication_enabled=false` until evidence
review. Do not promote staging; the existing public publication head remains
the rollback snapshot. If a request has uncertain outcome, stop and use the
protected recovery decision endpoint before retrying.

## Pending evidence

No live cycle has been run. Therefore there is currently no production
deployment commit evidence, request/redirect/status/latency evidence, credit
ledger evidence, Apply validation evidence, publication-head comparison, or
controlled source-failure preservation report. Phase I must not be marked
complete until those reports are attached to the corresponding cycle IDs.
