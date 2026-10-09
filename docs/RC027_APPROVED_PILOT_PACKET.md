# RC-027 approved staging pilot packet

> **Execution amendment — 2026-09-09.** The host/runtime gate was completed
> on the authorized VPS for an isolated local SQLite staging rehearsal. The
> verified code candidate is now `6e9a1e9301ffca644aca916aad6fc8827e4a792d`,
> which includes the demonstrated systemd worker-log-path correction. The
> persistent deployment checkout remains at its pre-amendment tip until the C
> worktree evidence is committed and fast-forwarded into it. A synthetic
> customer run completed, a controlled unknown-stage failure was classified as
> failed without retry expansion, and the customer worker recovered after a
> restart. No real-source/provider request, charge, Turso resource, R2 object,
> signed download, or browser/CORS pilot evidence exists. RC-027 therefore
> remains incomplete and blocked only at the external staging-credential,
> resource, and real-source acceptance gates described below.

Status: frozen selection; local host/runtime rehearsal complete; real-source
staging execution remains blocked on isolated provider/resource credentials.
No live request has been made under this packet.

## Candidate and verified input

| Item | Value |
| --- | --- |
| Runtime candidate | `6e9a1e9301ffca644aca916aad6fc8827e4a792d` |
| C worktree evidence base | `6e9a1e9301ffca644aca916aad6fc8827e4a792d` |
| Target branch | `deployment/render-turso-r2` |
| Contract / migration | `runr-contract-v1` / `058_customer_task_queue` |
| Host | `vmd205749` / `runradmin@144.91.99.90` |
| Master snapshot SHA-256 | `7f416ec6ebbcb936a42061ef0adaa07e4a6c04d2959d0eb579779126682440d9` |
| Master shape | 17,601 rows × 118 columns |
| Manifest cycle | `rc005-reconciled-20260907` |
| Manifest internal hash | `6bfcba5c01985402d2d1278e8b726baa8e4ac3332e6527be40bc433ab663e447` |
| Manifest file SHA-256 | `72b61f100a0d9edbba315b5f19db589f40cfecd42c19ce3ef95b78b331621873` |
| Raw sidecar SHA-256 | `cda46fee441e2e6e02d52ffe2fc86ae33121c82edc9f0636562367b63cbb5ef7` |
| Manifest totals | 1,574 dual-ready entities; 3,148 dual-source tasks |
| Preserved packet evidence | `C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc027-20260909\pilot-packet\` |

The manifest and sidecar were restored read-only from the recorded RC-023
source and their external file hashes match the preservation inventory. The
previously missing artifact is therefore resolved without changing the
original source or any application table.

## Frozen company selection

Selection rule: sort manifest rows with `decision=dual_ready`,
`source_eligibility.dual_source=true`, `review_required=false`, no exclusion
reasons, clear non-shared ownership, and an input canonical ID by canonical ID
ascending. Select the first four. All four support both sources; no pending
mapping, enrichment, or ownership review is used.

| # | Company | Canonical ID | Employer URL | LinkedIn URL | LinkedIn org ID | Row fingerprint |
| ---: | --- | --- | --- | --- | ---: | --- |
| 1 | MALZERS Backstube GmbH & Co. KG | `2f01e82d-c987-5b74-954a-c5f5e33dd3f6` | `https://malzers.de/` | `https://www.linkedin.com/company/malzersbackstube` | `52137146` | `986e61e0d0c3f0a3c0c00c64f83efddba79dd6d0f9e57ec580577a1bfcefead3` |
| 2 | St. Vincenz Kliniken | `457b22b2-eef7-59de-bb51-6d68bca41183` | `https://vincenz.de/` | `https://www.linkedin.com/company/vincenz-krankenhaus` | `71136748` | `28b1eef2d31ef0eb81b71dde9885b56b706dec8bcf3b1bd6a954b2a4620e0832` |
| 3 | NOVENTI Health SE | `516fff5d-e011-5bc5-8104-f13cfe755ef8` | `https://noventi.de/` | `https://www.linkedin.com/company/noventi` | `20278563` | `723fe56e1eb47adcc3064d47f0798dc7819bc9522090e356d5cd72e26c5b98ce` |
| 4 | helmag | `7e9e0f51-3084-5688-957c-e4527c4b213e` | `https://www.helmag.com/` | `https://www.linkedin.com/company/helmag` | `11393520` | `6d5ee7d52b041460e169b9e0c36c5a8a27f680a05abb3a4d273fc374d96bc9a5` |

## Isolated staging identifiers

These names remain reserved for this packet. The host runtime is installed and
verified, but the external Turso/R2 resources were not created because no
authorized external credentials or dashboard access is configured. The local
rehearsal therefore uses isolated SQLite/local-object-storage state only.

```text
Turso database:       runr-staging-turso-rc027
R2 bucket/prefix:     runr-staging-rc027 / rc027/6e9a1e9301ffca644aca916aad6fc8827e4a792d/
Acquisition queue:    runr-staging-acquisition-queue
Customer queue:       runr-staging-customer-queue
Evidence root:        /srv/runr/rc027-evidence/6e9a1e9301ffca644aca916aad6fc8827e4a792d/
Shared inputs:        /srv/runr/shared/inputs/
LinkedIn state:       /srv/runr/state/linkedin/
Employer state:        /srv/runr/state/employer/
Exports:              /srv/runr/exports/rc027/6e9a1e9301ffca644aca916aad6fc8827e4a792d/
Disposable app data:  /srv/runr/app-data/rc027-6e9a1e93/
```

No production database, bucket, prefix, queue, credentials, or schedule may
be substituted for these identifiers.

The host currently retains the original d326 packet/setup directory for
preservation. The corrected 6e9 evidence, export and app-data directories are
reserved names only and were not created because the real pilot did not start;
the local rehearsal used the separately isolated `/var/lib/runr/api-data` and
`/var/lib/runr/customer-data` stores.

## Hard limits and stop conditions

The limits apply cumulatively across both cycles, retries, restart and failure
checks. Counters must persist in the isolated staging state and be checked
before dispatch:

- at most 4 companies and 2 normal acquisition cycles;
- at most 200 acquisition HTTP/provider/browser requests total;
- at most 30 acquisition requests per company per cycle;
- at most 2 concurrent company tasks and 1 browser session;
- at most 120 minutes active live acquisition;
- at most US$5 equivalent incremental provider/infrastructure charges;
- no subscription upgrade, top-up, paid plan or enrichment purchase.

Stop immediately for production targeting, a cap hit, uncontrolled retry or
scope expansion, state/writer/identity corruption, repeated authentication
failure, rate limiting or anti-bot challenge. A cap or failure is recorded as
partial/incomplete/failed—not confirmed zero. Paid endpoints remain disabled
until their pricing and projected charge are verified under the US$5 cap.

## Staging command contract

Every role must advertise the same release and migration values:

```sh
RUNR_ENV=staging \
RUNR_RELEASE_BRANCH=deployment/render-turso-r2 \
RUNR_RELEASE_COMMIT=6e9a1e9301ffca644aca916aad6fc8827e4a792d \
RUNR_RELEASE_CONTRACT_VERSION=runr-contract-v1 \
RUNR_MIGRATION_HEAD=058_customer_task_queue \
RUNR_PRIVATE_TEST_DEPLOYMENT=true \
RUNR_DATA_DIR=/srv/runr/app-data/rc027-6e9a1e93 \
RUNR_STORAGE_BACKEND=sqlite
```

Run migration once against the isolated staging database, then start API,
customer and acquisition roles with unique IDs. Mount the packet manifest and
raw sidecar read-only at `/srv/runr/shared/inputs`; mount acquisition state and
exports only to the acquisition owner. The wrappers must be invoked with one
frozen company ID at a time. The LinkedIn wrapper must use `--mode pilot`,
`--max-companies 1`, one worker, one detail worker, retry limit 1, and
`--max-requests 30`; the employer wrapper must use one target at a time and a
page/browser cap below the 30-request company budget. Cumulative accounting,
not command-line caps alone, is authoritative.

## Evidence required before completion

Record sanitized cycle IDs, source-task result/reason rows, request and credit
counters, costs, publication IDs, authenticated Jobs API reads, UI evidence,
second-cycle stable IDs/detail reuse, failure/partial/outage classifications,
worker restart/checkpoint/lease results, object metadata, signed-download
headers/body, and browser CORS behavior under the evidence root above. Disable
the staging schedules and workers after the evidence capture. RC-006b remains
outside this packet.

## Current execution result and blocker

The authorized `runr-vps` alias and non-interactive sudo were verified. Host
setup completed on `vmd205749`: Python 3.12.7 is installed at
`/opt/python/3.12.7/bin/python3.12`; `/opt/runr` contains the candidate;
migrations 001 through `058_customer_task_queue` are applied to the isolated
SQLite rehearsal database; API, frontend, and customer worker are active;
acquisition worker is inactive and disabled; API is loopback-only; frontend is
on port 3000; UFW remains deny-by-default with SSH allowed; fail2ban and SSH
hardening remain active. The release metadata, contract, and migration head
advertise the same candidate.

The synthetic customer run `run_996c212f698049d6` completed with one attempt.
The controlled failure run `run_bc9f72cd89fb43a1` ended `failed` at `1/1`, with
redacted error logging and no retry expansion. After `runr-worker.service` was
restarted, it returned active with a new process and current idle heartbeat.

The live pilot is still blocked. The host has no configured `turso`, `wrangler`,
`aws`, `rclone`, Docker or Podman tooling, and the required Turso/R2/provider
secret names are not configured in either protected environment file. No
isolated Turso database, R2 bucket/prefix object, provider price authorization,
real-source request, signed URL, browser download, or CORS result may be
claimed. Complete the consolidated external checklist in the RC-C handoff;
keep acquisition disabled until every item and the budget ledger are verified.
