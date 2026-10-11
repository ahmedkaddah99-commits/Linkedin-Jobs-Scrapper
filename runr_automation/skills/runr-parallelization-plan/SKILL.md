---
name: runr-parallelization-plan
description: Use when Runr tickets need dependency relations, conflict analysis, execution waves, or a current parallel/serial execution decision.
---

# Runr parallelization plan

Parallelism belongs to a plan version and compatible ticket group, never permanently to one issue. Derive hard edges only from acceptance criteria, required artifacts, migrations, APIs, schemas, and tests. Every inferred edge needs evidence. Never remove a user-created relation automatically; flag conflicts for review.

Build the affected component DAG. A cycle means `Execution Mode: Review Required` and no wave assignment. Derive conflicts from overlapping writes, migrations, generated files, global configuration, contracts, release files, and shared fixtures. Topologically place ready tickets in deterministic waves, with no dependency path or resource conflict inside a wave.

Classify each blocking edge as an `implementation dependency`, `release dependency`, or `external dependency`, and persist the evidence plus the required predecessor revision/state. Compute two gates: `implementation-ready` (implementation dependencies have exact integrated artifacts, including `Predeployment Integrated`) and `release-ready` (release dependencies have `Ready for Production`). A predecessor remaining in native `In Review` is not by itself a reason to block implementation when its exact tested revision is integrated. It remains a release gate until live verification passes.

Persist plan version, validity fingerprint, edge/conflict evidence, and compatibility membership. Linear labels are projections only. `Parallel` is valid only with a current plan version and wave. Replan only the affected connected component.

Treat `/opt/runr`, acquisition systemd units/timers, active producer state, and provider budgets as exclusive VPS verification resources. Repository implementation may overlap when paths and dependencies permit, but host acceptance runs using `docs/reverse-engineering/02-deployment/vps-predeployment-verification.md` are serial. A predecessor's `Predeployment Integrated` label satisfies an implementation edge only after exact tested code content is verified on the permanent branch.

Do not use a permanent boolean parallel flag, delete user edges, or schedule from labels without authoritative plan data.
