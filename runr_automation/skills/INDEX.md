# Runr automation skills

These canonical skills are the source of truth for user-invoked workflows. The local controller is an optional automation path; merge, deployment, and discard skills must never treat its state database or approvals as prerequisites.

- `runr-ticket-creation`
- `runr-ticket-deduplication`
- `runr-ticket-research`
- `runr-parallelization-plan`
- `runr-ticket-start`
- `runr-ticket-implementation`
- `runr-ticket-merge-predeployment`
- `runr-ticket-batch-merge-predeployment`
- `runr-ticket-merge-deployment`
- `runr-ticket-batch-merge-deployment`
- `runr-discard-issue`

The corresponding `.agents/skills/runr-*` files are discovery shims only. `docs/subsystems.yaml` remains the sole repository subsystem registry.
