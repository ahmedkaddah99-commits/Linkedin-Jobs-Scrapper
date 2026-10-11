# Contabo VPS resource record

Recorded: 2026-09-11

## Provider-plan evidence

The supplied Contabo screenshot shows:

- Instance: `vmd205749`
- Product: `Cloud VPS 6 (2026) (ohne Setup)`
- Status: `Running`
- Region: `EU`
- Public IP shown in the screenshot: `144.91.99.90`

The screenshot identifies the purchased product but does not display a CPU-credit policy, sustained CPU allowance, network quota, or monthly billing limit. Those values must not be inferred from the product name.

## Host measurements and runtime guardrails

Read-only inspection of `runr-vps` on 2026-09-11 recorded:

- 6 vCPU
- 11,960 MiB RAM
- 193 GB filesystem
- No swap
- Approximately 11,098 MiB free and 11,233 MiB available at inspection time

The acquisition systemd units define these application guardrails:

- `CPUQuota=300%` (up to three CPU cores of aggregate service time)
- `MemoryHigh=9G`
- `MemoryMax=12G`
- `TasksMax=512`

These are safety ceilings, not proof that a continuous scraping workload fits the provider plan. Production must record CPU time, memory peak, request count, rate limits, and cycle duration before the caps are increased.

## Operational interpretation

The acquisition service should run as a bounded rotating cycle. A full sweep of every company is not a daily-cycle assumption. The request budget, worker count, and cohort size must be configured below the guardrails and adjusted only from measured cgroup usage.

