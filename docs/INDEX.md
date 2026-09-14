# Runr documentation index

This is the single technical entry point. GitHub (this repo) owns technical documentation and implementation evidence; Linear owns current work status, priority, dependencies and assignment (see [tickets/TEMPLATE.md](tickets/TEMPLATE.md)). Every future implementation ticket must update the docs and registry entries it touches.

Start with [reverse-engineering/00-overview.md](reverse-engineering/00-overview.md) for the narrative overview, cross-subsystem data flow, and branch/production-record reconciliation. The machine-readable subsystem registry is [subsystems.yaml](subsystems.yaml).

## Route by task

| I want to... | Go to |
|---|---|
| Understand the whole system before touching anything | [reverse-engineering/00-overview.md](reverse-engineering/00-overview.md) |
| Trace a job from acquisition to the customer UI | [reverse-engineering/01-architecture/data-flow.md](reverse-engineering/01-architecture/data-flow.md) |
| Work on the HTTP API or CLI (`workspace_runner.py`) | [reverse-engineering/01-architecture/backend-api.md](reverse-engineering/01-architecture/backend-api.md) |
| Work on the worker/orchestration engine | [reverse-engineering/01-architecture/backend-workers-and-orchestration.md](reverse-engineering/01-architecture/backend-workers-and-orchestration.md) |
| Work on domain models or repositories | [reverse-engineering/01-architecture/domain-model.md](reverse-engineering/01-architecture/domain-model.md) |
| Work on auth, Clerk, or CORS | [reverse-engineering/01-architecture/security-and-auth.md](reverse-engineering/01-architecture/security-and-auth.md) |
| Work on the customer web frontend | [reverse-engineering/01-architecture/frontend-app.md](reverse-engineering/01-architecture/frontend-app.md) |
| Work on the browser extension or shared TS packages | [reverse-engineering/01-architecture/apps-and-extensions.md](reverse-engineering/01-architecture/apps-and-extensions.md), [shared-packages.md](reverse-engineering/01-architecture/shared-packages.md) |
| Work on Render deploy config | [reverse-engineering/02-deployment/render.md](reverse-engineering/02-deployment/render.md) |
| Work on the VPS / systemd acquisition timers | [reverse-engineering/02-deployment/vps-runtime-and-acquisition-timers.md](reverse-engineering/02-deployment/vps-runtime-and-acquisition-timers.md) |
| Work on Docker images | [reverse-engineering/02-deployment/docker.md](reverse-engineering/02-deployment/docker.md) |
| Work on CI | [reverse-engineering/02-deployment/ci-cd.md](reverse-engineering/02-deployment/ci-cd.md) |
| Understand what's actually deployed where | [reverse-engineering/02-deployment/release-process-and-production-records.md](reverse-engineering/02-deployment/release-process-and-production-records.md) |
| Work on database schema / migrations | [reverse-engineering/03-data/schema-and-migrations.md](reverse-engineering/03-data/schema-and-migrations.md) |
| Work on the Turso/libSQL connection layer | [reverse-engineering/03-data/turso-and-libsql.md](reverse-engineering/03-data/turso-and-libsql.md) |
| Work on R2 object storage | [reverse-engineering/03-data/object-storage-r2.md](reverse-engineering/03-data/object-storage-r2.md) |
| Work on acquisition source-state / producer inputs | [reverse-engineering/03-data/acquisition-source-state.md](reverse-engineering/03-data/acquisition-source-state.md) |
| Find or run a test | [reverse-engineering/04-testing/test-suite-map.md](reverse-engineering/04-testing/test-suite-map.md) |
| Work on acquisition producers/collectors | [reverse-engineering/05-subsystems/acquisition-and-collectors.md](reverse-engineering/05-subsystems/acquisition-and-collectors.md) |
| Work on publication / the job catalog | [reverse-engineering/05-subsystems/publication-and-catalog.md](reverse-engineering/05-subsystems/publication-and-catalog.md) |
| Work on company identity, enrichment, or logos | [reverse-engineering/05-subsystems/company-identity-enrichment-and-logos.md](reverse-engineering/05-subsystems/company-identity-enrichment-and-logos.md) |
| Work on applicant intelligence (Phase G, blocked) | [reverse-engineering/05-subsystems/applicant-intelligence.md](reverse-engineering/05-subsystems/applicant-intelligence.md) |
| Work on personalized jobs / customer app services | [reverse-engineering/05-subsystems/personalized-jobs-and-customer-app-services.md](reverse-engineering/05-subsystems/personalized-jobs-and-customer-app-services.md) |
| Work on CVs, cover letters, career profile/evidence | [reverse-engineering/05-subsystems/career-profiles-and-documents.md](reverse-engineering/05-subsystems/career-profiles-and-documents.md) |
| Work on the Assisted Apply extension (never-submit boundary) | [reverse-engineering/05-subsystems/assisted-apply.md](reverse-engineering/05-subsystems/assisted-apply.md) |
| Work on billing / Creem | [reverse-engineering/05-subsystems/billing-and-creem.md](reverse-engineering/05-subsystems/billing-and-creem.md) |
| Find out what was retired and why (admin dashboard) | [reverse-engineering/06-history-and-provenance/retired-features.md](reverse-engineering/06-history-and-provenance/retired-features.md) |
| Understand branch history / what's unmerged and why | [reverse-engineering/06-history-and-provenance/branch-divergence.md](reverse-engineering/06-history-and-provenance/branch-divergence.md) |
| Check a known contradiction or open unknown before assuming something is broken | [reverse-engineering/06-history-and-provenance/known-gaps.md](reverse-engineering/06-history-and-provenance/known-gaps.md) |
| Classify a root-level report/doc file | [reverse-engineering/06-history-and-provenance/repository-artifacts.md](reverse-engineering/06-history-and-provenance/repository-artifacts.md) |
| File or read a work item | [tickets/TEMPLATE.md](tickets/TEMPLATE.md) and the consolidated backlog (see below) |

## Root-level docs

- [../AGENTS.md](../AGENTS.md) — short, project-wide agent instructions (Python venv usage). Detailed per-subsystem agent guidance lives in each subsystem doc's "Agent context and remaining work" section, not here.
- [../ARCHITECTURE.md](../ARCHITECTURE.md) — an earlier "unified backend" architecture note. It predates the acquisition/publication/Turso/Render system described in this corpus and is kept as history; for current architecture, use this index and `00-overview.md` instead.

## Backlog

The consolidated, deduplicated work backlog lives outside this repository, at `RUNR_REVERSE_ENGINEERING_2026-09-10/clean-slate-2026-09-13/linear-ticket-candidates.md` (alongside the rest of the Phase 1/2 evidence). It is the single live source of ticket candidates — do not create a second one. Once its items are created in Linear, the file becomes a migration cross-reference, not a second live backlog (see [tickets/TEMPLATE.md](tickets/TEMPLATE.md) §Maintenance).

## Verification

Documentation changes should be checked with focused local commands, not a full product run:

```powershell
# Every [text](path) link in docs/ resolves to a tracked file
.venv\Scripts\python.exe -c "import re,pathlib,sys; root=pathlib.Path('docs'); bad=[]; [bad.append((p,m)) for p in root.rglob('*.md') for m in re.findall(r'\]\(([^)]+\.md)[^)]*\)', p.read_text(encoding='utf-8')) if not (p.parent / m.split('#')[0]).resolve().exists()]; print('\n'.join(f'{p}: {m}' for p,m in bad)) or sys.exit(1 if bad else 0)"

# Every owned_globs path prefix in subsystems.yaml exists in the tree
git ls-tree -r --name-only HEAD | Select-String -Pattern '^(backend|frontend|apps|packages|scripts|deploy|tests|data)/' | Select-Object -First 5
```
