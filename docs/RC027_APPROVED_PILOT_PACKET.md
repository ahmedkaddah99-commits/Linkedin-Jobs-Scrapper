# RC-027 approved staging pilot packet

Status: frozen selection; staging execution is blocked on host elevation and
isolated provider/resource credentials. No live request has been made under
this packet.

## Candidate and verified input

| Item | Value |
| --- | --- |
| Runtime candidate | `d326726acab7fffbbf59e294629b8ef002437566` |
| Integrated repository tip | `daf00c187116c77b43744efa3d07539db06880ad` |
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

These names are reserved for this packet. They were not created because no
Turso/R2 CLI credentials are configured locally and the VPS has no installed
Runr runtime or usable non-interactive sudo yet.

```text
Turso database:       runr-staging-turso-rc027
R2 bucket/prefix:     runr-staging-rc027 / rc027/d326726acab7fffbbf59e294629b8ef002437566/
Acquisition queue:    runr-staging-acquisition-queue
Customer queue:       runr-staging-customer-queue
Evidence root:        /srv/runr/rc027-evidence/d326726acab7fffbbf59e294629b8ef002437566/
Shared inputs:        /srv/runr/shared/inputs/
LinkedIn state:       /srv/runr/state/linkedin/
Employer state:        /srv/runr/state/employer/
Exports:              /srv/runr/exports/rc027/d326726acab7fffbbf59e294629b8ef002437566/
Disposable app data:  /srv/runr/app-data/rc027-d326726a/
```

No production database, bucket, prefix, queue, credentials, or schedule may
be substituted for these identifiers.

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
RUNR_RELEASE_COMMIT=d326726acab7fffbbf59e294629b8ef002437566 \
RUNR_RELEASE_CONTRACT_VERSION=runr-contract-v1 \
RUNR_MIGRATION_HEAD=058_customer_task_queue \
RUNR_PRIVATE_TEST_DEPLOYMENT=true \
RUNR_DATA_DIR=/srv/runr/app-data/rc027-d326726a \
RUNR_STORAGE_BACKEND=sqlite
```

Run migration once against the isolated staging database, then start API,
customer and acquisition roles with unique IDs. Mount the packet manifest and
raw sidecar read-only at `/srv/runr/shared/inputs`; mount acquisition state and
exports only to the acquisition owner. The wrappers must be invoked with one
frozen company ID at a time, `--mode pilot`, `--max-companies 1`, one worker,
one detail worker, retry limit 1, and `--max-requests 30` for LinkedIn. The
employer connector must use one target at a time and a page/browser cap below
the 30-request company budget. Cumulative accounting, not command-line caps
alone, is authoritative.

## Evidence required before completion

Record sanitized cycle IDs, source-task result/reason rows, request and credit
counters, costs, publication IDs, authenticated Jobs API reads, UI evidence,
second-cycle stable IDs/detail reuse, failure/partial/outage classifications,
worker restart/checkpoint/lease results, object metadata, signed-download
headers/body, and browser CORS behavior under the evidence root above. Disable
the staging schedules and workers after the evidence capture. RC-006b remains
outside this packet.

## Current execution blocker

Read-only SSH succeeds, but the host currently has no `/opt/runr`, `/srv/runr`,
`/var/lib/runr`, Docker/Podman, or Runr systemd units. `runradmin` is in the
`sudo` group, but `sudo -n -v` is unavailable and no password/root SSH path is
configured. Local Turso, Wrangler, AWS and R2 credential configuration is also
absent. No staging resource was created and no live source request was made.

The smallest required user action is to provide a working approved elevation
method for `runradmin` on `144.91.99.90` and inject isolated staging Turso/R2
and source-provider credentials/pricing access through the authorized secret
store. Provider credentials must remain disabled if their cost cannot be
bounded under this packet.
