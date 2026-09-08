# RC-018 worker roles

Target branch: `deployment/render-turso-r2`

The shared worker entrypoint now requires an explicit workload boundary. The
safe default is `customer`; acquisition is opt-in.

| Role | Allowed task family | Claims/executes | Does not enter |
| --- | --- | --- | --- |
| `customer` | `customer` | personalized intelligence and queued customer runs, including CV/document workflows | scheduled acquisition, company enrichment, admin imports |
| `acquisition` | `acquisition` | admin imports, scheduled LinkedIn/employer acquisition, company enrichment | personalized intelligence and queued customer runs |

Role checks happen before a queue claim. The acquisition import and customer
intelligence stores reject a mismatched role without changing queue state, and
the run lifecycle refuses a non-customer claim. This keeps a mixed queue safe
even when both processes poll the same database.

Heartbeats and structured worker logs include:

- `worker_role`
- `worker_version` (default `rc018-v1`, override with `RUNR_WORKER_VERSION`)
- `capacity_slots` (default `1`, override with `RUNR_WORKER_CAPACITY_SLOTS`)
- `active_task_family`
- `allowed_task_families`

Each process executes one task at a time. Production CLI identities append the
runtime host and process ID when `RUNR_ENV` is production. Role-specific
processes must still use distinct `WORKER_ID` values; the Render customer
service is configured as `render_customer_worker`.

## Rollout and compatibility

Existing `run-worker` and `process-next` invocations without a role continue as
customer workers. They no longer run acquisition work implicitly. An
acquisition process must set both a unique identity and the role explicitly:

```text
WORKER_ID=render_acquisition_worker WORKER_ROLE=acquisition deploy/start.sh worker
```

The current Render service is explicitly configured for the customer role.
Provisioning a separate acquisition service/process, and applying host-level
CPU/RAM limits, belongs to the later VPS/runtime ticket; this change provides
the process boundary and capacity contract without making a live deployment.

Rollback is configuration-only: stop using `WORKER_ROLE=acquisition`, restore
the prior worker command/configuration, and revert the RC-018 files. Existing
queued records remain queued when claimed by the wrong role, so no queue
cleanup or database rollback is required.
