# RC-027 bounded real-source pilot receipt

## Corrective diagnostics and spending stop - 2026-09-10

These are manually scoped diagnostics; two unattended staging cycles, Turso
publication and authenticated Jobs/UI visibility remain unaccepted. The
original four companies were investigated without replacements.

| Candidate | Company | Attempts | Jobs | Outcome |
| --- | --- | ---: | ---: | --- |
| 15f58623 | MALZERS | 3 | 1 | partial; embedded JSON observation, CAPTCHA on selected target |
| 15f58623 | St. Vincenz | 15 | 0 | partial; request cap |
| 15f58623 | NOVENTI | 15 | 0 | partial; request cap |
| 15f58623 | helmag | 15 | 0 | partial; request cap |
| 42f150f5 | St. Vincenz | 4 | 0 | source_failed; browser timeout |
| 42f150f5 | NOVENTI | 5 | 0 | partial; browser timeout |
| 42f150f5 | helmag | 5 | 0 | partial; browser timeout |
| 547ff5a7 | St. Vincenz | 7 | 0 | source_failed; browser timeouts on two targets |
| 547ff5a7 | NOVENTI | 10 | 0 | partial; browser timeouts on two targets |
| 547ff5a7 | helmag | 9 | 0 | partial; browser timeouts on two targets |

Each invocation selected exactly one approved canonical ID and enforced its
own cap. Receipts are preserved under `/srv/runr/exports/rc027-browser-15f58623/`,
`/srv/runr/exports/rc027-discovery-42f150f5/`, and
`/srv/runr/exports/rc027-proxy-547ff5a7/`. Their receipt.json files were copied
to the persistent local `runr-acquisition-snapshots/rc027-20260909/` directory
as `rc027-<browser|discovery|proxy>-<SHA>-receipt.json`. State is separate under
the matching `/srv/runr/state/rc027-*` directories. No existing state was cleared.

Accounting: the earlier repair diagnostics used 100, then these runs used
48 + 14 + 26 = 88, for **188 confirmed attempts** of the new 200 allowance.
A final NOVENTI run at `2ab1da7f` reserved 12 and was explicitly terminated
after the user stopped credit-consuming diagnostics. It returned exit -15;
actual consumption is unknown. Its receipt at
`/srv/runr/exports/rc027-direct-2ab1da7f/receipt.json` reserves those 12.
Treat the allowance as fully allocated, without claiming 200 measured
requests. Historical 190/200 remains separate. No new plan, purchase or credit
top-up occurred; incremental monetary cost was not reported by the transport.

The final code fixes browser timeout evidence loss and adds direct-first
browser access with proxy fallback. Those fixes have focused offline evidence;
the interrupted final run does not establish live success. A real Linux
Chromium loopback fixture passed as runr-acquisition under systemd protections.
The production acquisition service remains inactive/disabled and no acquisition
user processes remain running. No production publication or cutover occurred.

Staging still requires a scoped Turso database/token and scoped R2 bucket
access with browser CORS. The authoritative env contains database/S3 access
credentials, but no Turso Platform or Cloudflare management token. The latest
instruction stops further provider-credit diagnostics; continue offline only
until the user directs the next live operation and allowance.

## Repair-candidate live verification amendment - 2026-09-09

The final A/B repair candidate was staged as release
`466541b3ee4a57a89f83c583f5e497b36fccdbe3` under
`/opt/runr/releases/rc027-466541b3` on `runr-vps`. A no-network manifest
preflight passed for LinkedIn after the external pagination/filter evidence
paths were supplied explicitly. The first live attempt failed before any
request because the acquisition environment lacked Webshare configuration; a
separate protected `/opt/runr/.env.acquisition.provider` was then installed
with only the existing Webshare API/username/password entries. No customer
`.env` was made readable by the acquisition role.

The repaired LinkedIn cycle 1 used **60/60** newly authorized attempts for
the frozen four-company selection. It wrote 61 valid cards, 45 detail
successes and 16 pending detail retries; all four scans remained
`PARTIAL_SUSPICIOUS_EMPTY`, with 45 jobs written and no valid/closure-safe
snapshot. Provider cost was not reported. Its metrics are preserved at:

`/srv/runr/exports/rc027-repair-466541b3/cycle-1-live-3/linkedin/metrics.json`

The employer cycle invocation used the candidate repair but was **not valid
frozen-cohort evidence**: `--limit 0` selects all eligible companies in this
wrapper, so it processed all 1,574 manifest rows under a 40-attempt cap rather
than only MALZERS, St. Vincenz, NOVENTI and helmag. It recorded 1,573 partial
and one source-failed company status, zero jobs, 40 direct attempts and no
provider cost; no publication was promoted. Its output is preserved at:

`/srv/runr/exports/rc027-repair-466541b3/cycle-1-live-3/employer/`

This run is retained as a bounded diagnostic, not acceptance. New verification
usage is **100/200** attempts (60 LinkedIn + 40 employer), separate from the
earlier historical pilot's 190/200. No Turso write, migration, R2 object write
or customer service change was made by this amendment. The acquisition service
remains disabled.

Date: 2026-09-09
Integration branch: `deployment/render-turso-r2`
Persistent target checkout: `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview`
Host: `runr-vps` / `vmd205749`
Host release base: `6e9a1e9301ffca644aca916aad6fc8827e4a792d`
Target correction commit: `16c1215d` (`fix(acquisition): enforce bounded staging source requests`)

## Gate result

The real-source pilot executed both producer collectors for the four frozen
companies over two cycles on the authorized VPS. RC-027 is **not accepted**:
all LinkedIn scans were `PARTIAL_SUSPICIOUS_EMPTY`, employer scans were
`partial`, `source_failed`, or budget-bounded `collector_error`, and therefore
no source snapshot was valid or closure-safe. The integrated acquisition
transport correctly withheld staging and public publication.

This is a real partial/failure result, not a confirmed-zero result. No
production Turso write, migration, Render deployment, customer worker change,
subscription upgrade, or ScrapeOps request was made.

## Frozen scope and limits

Only these four manifest-approved identities were passed explicitly:

| Company | Canonical ID | LinkedIn organization ID |
| --- | --- | --- |
| MALZERS Backstube GmbH & Co. KG | `2f01e82d-c987-5b74-954a-c5f5e33dd3f6` | `52137146` |
| St. Vincenz Kliniken | `457b22b2-eef7-59de-bb51-6d68bca41183` | `71136748` |
| NOVENTI Health SE | `516fff5d-e011-5bc5-8104-f13cfe755ef8` | `20278563` |
| helmag | `7e9e0f51-3084-5688-957c-e4527c4b213e` | `11393520` |

The manifest hash was
`6bfcba5c01985402d2d1278e8b726baa8e4ac3332e6527be40bc433ab663e447`.
The source input was materialized from the verified shared manifest/sidecar;
no bulk runtime database was copied.

Hard limits were four companies, two cycles, one worker, one browser,
retry-limit 1, no more than 30 attempts per company/cycle, 200 cumulative
source/provider/browser attempts, 120 minutes, and US$5 incremental cost.
The measured total was **190/200** attempts: cycle 1 was 135 and cycle 2 was
55. Webshare was already active; no purchase, top-up, upgrade, or paid
enrichment was performed.

## Producer outcomes

LinkedIn used `scripts/run_manifested_linkedin.py`, which calls the actual
14-table producer `scripts/master_linkedin_jobs_catalog.py`. Employer used
`scripts/run_manifested_employer.py`. The `master_linkedin_jobs_url_catalog.py`
producer was not substituted.

| Cycle | Source/company | Requests | Jobs written | Result |
| --- | --- | ---: | ---: | --- |
| 1 | LinkedIn / MALZERS | 2 | 0 | `PARTIAL_SUSPICIOUS_EMPTY` |
| 1 | LinkedIn / Vincenz | 5 | 2 | `PARTIAL_SUSPICIOUS_EMPTY` |
| 1 | LinkedIn / NOVENTI | 13 | 10 | `PARTIAL_SUSPICIOUS_EMPTY` |
| 1 | LinkedIn / helmag | 15 | 8 | `PARTIAL_SUSPICIOUS_EMPTY` |
| 1 | Employer / MALZERS | 24 | 1 | `partial` |
| 1 | Employer / Vincenz | 25 | 0 | `source_failed` |
| 1 | Employer / NOVENTI | 26 | 0 | `partial` |
| 1 | Employer / helmag | 25 | 0 | `partial` |
| 2 | LinkedIn / MALZERS | 2 | 0 | `PARTIAL_SUSPICIOUS_EMPTY` |
| 2 | LinkedIn / Vincenz | 5 | 2 | `PARTIAL_SUSPICIOUS_EMPTY` |
| 2 | LinkedIn / NOVENTI | 8 | 5 | `PARTIAL_SUSPICIOUS_EMPTY` |
| 2 | LinkedIn / helmag | 8 | 1 | `PARTIAL_SUSPICIOUS_EMPTY` |
| 2 | Employer / MALZERS | 8 | 0 | `collector_error` at request budget |
| 2 | Employer / Vincenz | 8 | 0 | `collector_error` at request budget |
| 2 | Employer / NOVENTI | 8 | 0 | `collector_error` at request budget |
| 2 | Employer / helmag | 8 | 0 | `collector_error` at request budget |

The LinkedIn state path was
`/srv/runr/state/rc027-linkedin-6e9a1e9301ffca644aca916aad6fc8827e4a792d/`.
The employer state path was
`/srv/runr/state/rc027-employer-6e9a1e9301ffca644aca916aad6fc8827e4a792d/`.
Exports were under
`/srv/runr/exports/rc027/6e9a1e9301ffca644aca916aad6fc8827e4a792d/cycle-{1,2}/`.

## Integrated transport and publication result

The producer states were delivered through
`backend/acquisition/producer_adapters.py` and
`SqliteAcquisitionTransport` into:

`/srv/runr/app-data/rc027-6e9a1e9301ffca644aca916aad6fc8827e4a792d/acquisition-staging-v2.sqlite3`

The integrated database contains two partial cycles, 16 tasks, 22 source
observations, 21 canonical jobs, and 21 source states. Every task has
`valid_snapshot=0` and `closure_safe=0`; failed or incomplete scans were
represented as unknown/partial and did not close existing postings. There is
no `acquisition_publications` row, and both staging and public catalog reads
return `freshness=unpublished`, `total=0`.

The first harness database remains preserved at
`/srv/runr/app-data/rc027-6e9a1e9301ffca644aca916aad6fc8827e4a792d/acquisition-staging.sqlite3`.
It is not used as the acceptance database.

## Production R2 artifact verification

Per the user’s explicit instruction, the existing production artifact bucket
`runr-prod-artifacts` was used only for this new immutable key; no existing
object was overwritten or deleted:

`rc027/6e9a1e9301ffca644aca916aad6fc8827e4a792d/pilot/rc027-evidence-receipt.json`

The receipt is 332 bytes, `application/json`, `Cache-Control: max-age=600`,
and was read back with `HEAD` HTTP 200. A presigned 600-second range request
returned HTTP 206 and 32 matching bytes. The URL contains the normal
`X-Amz-Credential` access-key identifier required by S3 presigning, but not
the S3 secret, provider API tokens, or an `Authorization` query parameter.
This proves object write/read/sign/range behavior for the existing bucket;
bucket isolation and browser CORS remain unverified because bucket CORS
management returned `AccessDenied` and no Cloudflare management token is
configured. A direct browser-origin probe against the signed URL with
`Origin: https://app.userunr.com` returned `GET 206` with no
`Access-Control-Allow-*` headers; the preflight `OPTIONS` returned `403` with
no CORS headers. Therefore direct browser download is not accepted, even
though server-side object/sign/range behavior passed.

## Off-host checkpoint and restore verification

The host LinkedIn state was checkpointed with SQLite Online Backup through
`scripts/acquisition_state_backup.py` and restored into new directories before
and after an upload to the explicitly authorized existing production R2 bucket.
The source was
`/srv/runr/state/rc027-linkedin-6e9a1e9301ffca644aca916aad6fc8827e4a792d/master_linkedin_jobs_state.db`
(`770048` bytes, SHA-256
`ed94c1cd30095c3544adccabb028072b327885ccaf2e48630d3d4945213a59d5`, SQLite
integrity `ok`). Checkpoint
`linkedin-20260909T201035631862Z-e6d35734a371` produced a `770048` byte,
14-table backup with SHA-256
`d445e6c1a2dfb45d189c3ced3351406f867f49f3264f5375b07f078f26659356`.

The local checkpoint is preserved at
`C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc027-20260909\offhost-linkedin\offhost-linkedin-20260909\`;
local restore and R2 restore were both validated at
`C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc027-20260909\restored-linkedin`
and
`C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc027-20260909\restored-from-r2-linkedin`.
The R2 keys are under
`rc027/checkpoints/linkedin/linkedin-20260909T201035631862Z-e6d35734a371/`.
This closes the bounded checkpoint/restore evidence only; it does not restore
or accept the preserved approximately 3.48 GB historical state.

## Remaining acceptance blockers

- The source results are partial/failure, so RC-027 cannot authorize a
  staging or public publication.
- The real-source producer runs were on the host `6e9a1e93` release plus a
  staged uncommitted runtime overlay for the two corrections; the target
  branch now contains those corrections at `16c1215d`, but was not deployed.
- No authenticated staging UI origin was available, so browser dashboard,
  publication, direct-download and CORS proof remains pending.
- The configured Turso URL/token targets the production database and was not
  used. Isolated Turso staging, if still required, remains pending.
- R2 prefix isolation is not equivalent to a dedicated bucket/credential;
  the production bucket was used only because the user expressly authorized
  production artifacts. Dedicated staging scope remains the safer release
  gate.

## Rollback and cleanup

Code rollback: from the target checkout, review and revert only commit
`16c1215d` if the request-budget or POSIX manifest correction is rejected;
do not reset or restore over existing integration ancestry.

Pilot rollback: leave `runr-acquisition-worker.service` inactive/disabled,
retain the producer state, exports, evidence receipt and staging SQLite for
audit, and do not promote anything. Remove only the temporary provider env
file after verification; never remove the preserved historical source state,
shared input files, or existing production R2 objects.
