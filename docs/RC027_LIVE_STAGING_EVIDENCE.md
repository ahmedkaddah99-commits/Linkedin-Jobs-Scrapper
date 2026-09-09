# RC-027 live-staging evidence and external gate

Date: 2026-09-09
Integration lane: C (`temp/rc-c-release-integration`)
Persistent target: `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview`
Target branch: `deployment/render-turso-r2`
Runtime candidate: `6e9a1e9301ffca644aca916aad6fc8827e4a792d`

## Result

RC-023's clean-host/systemd portion is evidenced on the authorized VPS. The
RC-027 real-source pilot is not complete. It is blocked before live traffic by
the absence of isolated Turso/R2/provider resources and protected credentials,
not by SSH, sudo, host installation, or the customer-worker runtime.

No LinkedIn or employer request, provider charge, Turso external write, R2
object, signed download, browser/CORS request, or production migration was
performed.

## Actual deployed/runtime visibility

Read-only visibility checks on 2026-09-09 found different revisions in the
available environments:

| Environment | Observed result |
| --- | --- |
| Persistent target checkout | `3570e6c09edc88af77c7423da92a64e0244fa668` on `deployment/render-turso-r2` |
| GitHub remote-tracking deployment ref | `30ef992b7945ff0998704a550fdc2f893b24476f`; local target is 48 commits ahead; no push was made |
| VPS systemd runtime | `6e9a1e9301ffca644aca916aad6fc8827e4a792d`; API/frontend/customer services active; acquisition inactive/disabled |
| Public Render frontend | `7251ae297c55f7f6a4524181cdafb4648f7fdcde`, generated `2026-09-08T10:49:58.289Z` |
| Public Render API | `GET https://runr-api.onrender.com/health/live` returned HTTP 200 with `{"status":"ok"}` |
| Render management API | Authorized read-only via the nested repository env file; live API and worker deploy SHA `30ef992b7945ff0998704a550fdc2f893b24476f`; live frontend deploy SHA `7251ae297c55f7f6a4524181cdafb4648f7fdcde`; `runr-process-next` is suspended |

The public frontend revision is not evidence that the current target or VPS
candidate is deployed. The target must not be pushed until the isolated pilot
passes, because `render.yaml` uses `autoDeployTrigger: commit` for the API,
worker and frontend. The live Render API is healthy now, but it is running the
remote `30ef992b` candidate, not the local target.

## Credential discovery and scope boundary

The configured environment was found at
`C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\user_config\.env`,
not at the target checkout root. Its values were used only in memory for
redacted authorization checks. The configured Turso URL identifies the
production `runr-dev-ahmedkaddah99-commits` database and the configured S3
bucket is `runr-prod-artifacts`; those credentials were not used for staging
writes. The configured Turso credential returns HTTP 401 for the organization
management endpoint, but that result identifies it as a database/SQL token; it
does not prove that the Hobby plan forbids a staging database. Turso's current
authorization model separates database SQL tokens from organization/group
Platform API tokens. A separate staging database can be created in an existing
group with the latter; creating more than one group is the plan-limited
operation. No organization-scoped or group-scoped Platform token, organization
slug, or plan/quota response is configured here, so Turso staging creation still
needs that control-plane check. No Cloudflare account-management token is
configured, so R2 bucket/key isolation remains unverified; the configured S3
credential points at the production bucket.

The Webshare account is not blocked. Fresh profile and subscription checks
returned HTTP 200; the subscription is active, unpaused, unthrottled, renewals
enabled, and has zero failed-payment events. The plan lookup reports 100 shared
proxies at `$2.99` monthly. No source/proxy request was made. The ScrapeOps key
is present locally but remains disabled because its permitted cost was not
established.

## Host and release verification

The first access check used the approved alias and returned `root`:

```text
ssh -o BatchMode=yes -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no runr-vps "sudo -n whoami"
```

Sanitized results from `runr-vps`:

- Host: `vmd205749` (the alias remains `runr-vps`; no password-based SSH was
  used).
- OS: Ubuntu 24.04; SSH hardening, UFW and fail2ban were preserved.
- Exact host interpreter: `/opt/python/3.12.7/bin/python3.12`, Python 3.12.7.
- Release source: `/opt/runr`, candidate `6e9a1e9301ffca644aca916aad6fc8827e4a792d`.
- Source archive SHA-256:
  `fedf8336b2cd3f681dc35053f37b4f2beca1da6f328c5d23c8f78434365eb631`.
- Legal-document archive SHA-256:
  `7aa7408b4b6b6734ae4e9a1258f7a6b33e2722d57086509b54c276b94d3babff`.
- `/opt/runr/.env` and `.env.acquisition` advertise branch
  `deployment/render-turso-r2`, the candidate SHA, `runr-contract-v1`, and
  migration head `058_customer_task_queue`.
- Migration status for isolated SQLite `/var/lib/runr/api-data/rc027-staging.sqlite3`
  is applied through `058_customer_task_queue`, in order from 001 onward.
- `runr-api.service`, `runr-frontend.service`, and `runr-worker.service` are
  active. `runr-acquisition-worker.service` is inactive and disabled.
- API health: `GET http://127.0.0.1:8000/health/live` returned `{"status":"ok"}`.
- API listens on `127.0.0.1:8000`; frontend listens on `0.0.0.0:3000`; SSH
  remains on port 22. No public acquisition API was opened.
- Frontend `/runr-release.json` advertises the same candidate and contract.
- UFW remains active with default incoming deny and SSH-only allow; fail2ban's
  `sshd` jail is active.
- The runtime service accounts are non-root. Environment files are
  `root:runr`/`0640` and `root:runr-acquisition`/`0640`; role log directories
  are owned by their respective service accounts with mode `0750`.
- The corrected worker logger writes to `/var/log/runr/customer/worker.log`
  under systemd's protected filesystem policy.

Unavailable host tools are recorded rather than substituted: `turso`,
`wrangler`, `aws`, `rclone`, Docker, Podman and `sqlite3` are not installed.
The systemd runtime does not require Docker for this RC-023 rehearsal, but
external-resource creation and R2 verification cannot proceed without
authorized tooling/credentials.

## Runtime paths and ownership

The installed role contract is:

| Purpose | Path | Owner / access |
| --- | --- | --- |
| Release source | `/opt/runr` | `root:root`, service-readable |
| Customer/API env | `/opt/runr/.env` | `root:runr`, `0640` |
| Acquisition env | `/opt/runr/.env.acquisition` | `root:runr-acquisition`, `0640` |
| API SQLite rehearsal | `/var/lib/runr/api-data` | `runr:runr`, `0750` |
| Customer state | `/var/lib/runr/customer-data` | `runr:runr`, `0750` |
| Shared inputs | `/srv/runr/shared/inputs` | `root:runr-acquisition`, `0750`; files `0640` |
| Acquisition state | `/srv/runr/state` | `runr-acquisition:runr-acquisition`, `0750` |
| Acquisition exports | `/srv/runr/exports` | `runr-acquisition:runr-acquisition`, `0750` |
| Backup root | `/srv/runr/backups` | `runr-acquisition:runr-acquisition`, `0750` |
| Candidate evidence (reserved; not created) | `/srv/runr/rc027-evidence/6e9a1e9301ffca644aca916aad6fc8827e4a792d/` | would be acquisition-owned |
| Customer logs | `/var/log/runr/customer` | `runr:runr`, `0750` |
| Acquisition logs | `/var/log/runr/acquisition` | `runr-acquisition:runr-acquisition`, `0750` |

The canonical master input, manifest and raw sidecar were copied to the
read-only shared input area and retained their recorded hashes:

- master CSV: 17,601 x 118, SHA-256
  `7f416ec6ebbcb936a42061ef0adaa07e4a6c04d2959d0eb579779126682440d9`;
- manifest SHA-256
  `72b61f100a0d9edbba315b5f19db589f40cfecd42c19ce3ef95b78b331621873`;
- raw sidecar SHA-256
  `cda46fee441e2e6e02d52ffe2fc86ae33121c82edc9f0636562367b63cbb5ef7`.

The preserved packet/setup directory actually present on the host is the
original candidate path
`/srv/runr/rc027-evidence/d326726acab7fffbbf59e294629b8ef002437566/`; it was
not used for live traffic. The corrected 6e9 candidate evidence, export and
app-data paths are reserved but absent because the real pilot did not start.
The running local rehearsal uses `/var/lib/runr/api-data` and
`/var/lib/runr/customer-data` instead.

The four frozen companies remain MALZERS, St. Vincenz, NOVENTI and helmag.
No proposed mappings or unresolved shared organizations were applied.

## Offline/runtime lifecycle evidence

These runs are controlled staging fixtures, not real-source acquisition:

| Evidence | Result |
| --- | --- |
| Synthetic customer queue run `run_996c212f698049d6` | `completed`, attempts `1/1`, zero stages, no external requests |
| `runr-worker.service` restart | stopped/started cleanly; service returned `active` |
| Post-restart heartbeat | `vps_customer_worker`, role `customer`, idle, new process `36464`, current lease |
| Controlled unknown-stage run `run_bc9f72cd89fb43a1` | `failed`, attempts `1/1`; error redacted; no retry expansion |
| Post-failure worker state | service remained active and worker returned idle |

The worker journal recorded task start, failure/complete summary, and loop
restart without exposing the injected exception text. This proves local
classification and restart behavior only. It does not prove producer
checkpoints, publication preservation, real-source retries, Turso contention,
R2 upload/signing, or browser behavior.

## External staging checklist — one remaining action set

The following must be completed by an operator with the corresponding
provider/dashboard authority. Values must be entered directly on the VPS and
must never be pasted into Git, logs, or chat.

1. Create or verify the isolated Turso database
   `runr-staging-turso-rc027`; issue a staging-only URL/token with no
   production database privilege; run migrations 001 through
   `058_customer_task_queue` once using the release owner; record the
   migration status without recording the token.
2. Create or verify a private R2 bucket dedicated to RC-027, with the
   immutable prefix
   `rc027/6e9a1e9301ffca644aca916aad6fc8827e4a792d/`; issue a credential
   scoped only to that bucket/prefix and confirm it cannot list/write a
   production bucket or prefix. A prefix inside a production credential scope
   is not sufficient.
3. Apply the approved R2 CORS policy for the actual staging frontend origin:
   `GET`/`HEAD`, request headers `Range`, `Content-Type`, `Accept`, exposed
   headers `Accept-Ranges`, `Content-Length`, `Content-Disposition`,
   `Content-Type`, `ETag`, and max age 600 seconds. Do not use `*` with
   credentials. Record the exact origin without a secret.
4. Enter these names, with staging-only values, into the protected host
   locations: `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, `S3_ENDPOINT_URL`,
   `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_BUCKET`, and the approved
   proxy/provider settings. Keep `.env` customer-only and `.env.acquisition`
   acquisition-only; preserve `0640` role ownership.
5. Verify the selected source path (direct or approved proxy), provider price,
   remaining US$5 ceiling, retry cost treatment, and persistent cumulative
   counters. Keep ScrapeOps disabled unless its price is verified. Do not buy,
   upgrade, top up or enable automatic billing.
6. Supply isolated test identity/origin configuration for authenticated Jobs,
   API and UI verification. Do not put customer OAuth, email, billing or
   document credentials in the acquisition environment.

The specific management access still required is:

- Turso organization/database administration sufficient to create
  `runr-staging-turso-rc027`, run the migration owner step, and issue a
  database-scoped staging token that cannot access the production database;
- Cloudflare account/R2 administration sufficient to create the private
  staging bucket, apply the listed CORS policy, and issue an access key scoped
  to that bucket and the immutable candidate prefix only;
- a source/provider account or approved direct-source decision with visible
  pricing, quota and billing state sufficient to prove the four-company pilot
  stays below US$5; and
- valid Render read/deployment access to inspect the API, worker and frontend
  service revisions/logs. The present Render key is unauthorized, so the
  public 503 cannot be diagnosed from this session.

These are access requirements, not permission to expand the company set,
purchase capacity, upgrade a plan, enable ScrapeOps, or access production
secrets.

Secure host-side entry must be performed interactively by the operator. The
following commands preserve the existing files, open them only in the local
protected editor, and reassert the role permissions; the editor must not be
configured to log or sync its buffer:

```sh
sudoedit /opt/runr/.env
sudo chown root:runr /opt/runr/.env
sudo chmod 0640 /opt/runr/.env
sudoedit /opt/runr/.env.acquisition
sudo chown root:runr-acquisition /opt/runr/.env.acquisition
sudo chmod 0640 /opt/runr/.env.acquisition
sudo systemctl daemon-reload
```

Use the customer file only for customer/API names and the acquisition file
only for acquisition/provider names. Do not use `echo`, shell history, command
arguments, or a chat paste for secret values. Before enabling a service, these
non-secret checks are permitted:

```sh
sudo grep -E '^(TURSO_DATABASE_URL|TURSO_AUTH_TOKEN|S3_ENDPOINT_URL|S3_ACCESS_KEY_ID|S3_SECRET_ACCESS_KEY|S3_BUCKET)=' /opt/runr/.env /opt/runr/.env.acquisition | sed -E 's#=.*#=<present>#'
sudo systemctl show runr-api.service runr-worker.service runr-acquisition-worker.service -p User -p Environment -p ActiveState -p SubState
sudo -u runr /opt/runr/.venv/bin/python -m backend.database.migrate --database /var/lib/runr/api-data/rc027-staging.sqlite3 --status
curl -fsS http://127.0.0.1:8000/health/live
```

The R2 check must use only the staging bucket/prefix and a non-secret
`HeadObject`/metadata result. Acceptance remains blocked until resource
isolation, price/cost authorization, credentials, and all RC-027 real-source,
UI and storage evidence are present.

## Pilot limits and unrun criteria

Once the checklist passes, use only the four frozen companies, at most two
cycles, 200 cumulative acquisition HTTP/provider/browser requests, 30 per
company per cycle, concurrency two, one browser, 120 minutes, and US$5
incremental/prepaid ceiling. Persist counters across retries and restarts and
check them before dispatch. Unknown cost is not zero; a cap or unresolved
failure is partial/incomplete, never zero/pass.

Not executed in this pass: real cycles, LinkedIn/employer request accounting,
canonical ingestion/publication, authenticated Jobs/API/UI proof, duplicate
publication/resume proof, real interruption/checkpoint/lease proof, R2
upload/signed download, browser/CORS checks, or Turso/R2 external evidence.

## Rollback and shutdown

No external resource or production state was changed. To abandon this staging
rehearsal, stop and disable only the RC-027 acquisition unit (already inactive
and disabled), leave the customer/API services at the accepted local-runtime
state, and preserve `/srv/runr/state`, `/srv/runr/backups`, and the verified
input artifacts for audit. Do not delete historical source databases or move
the shared input originals. A code rollback is the prior candidate
`d326726acab7fffbbf59e294629b8ef002437566` only after reviewing the demonstrated
worker-log-path defect; the safer release rollback is to leave the deployment
branch unchanged until the external gate is satisfied.

RC-006b, RC-028 and RC-029 were not started.
