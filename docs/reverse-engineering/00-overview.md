> Source: deployment/render-turso-r2 | SHA: 58a96674 | Verified: 2026-09-14

# Runr technical overview (WS-12 synthesis)

This is the single narrative entry point for the reverse-engineering corpus. It is produced last, after WS-1…WS-11, and cites their docs rather than re-deriving their evidence. For routing by task, use [docs/INDEX.md](../INDEX.md). For the machine-readable subsystem registry, use [docs/subsystems.yaml](../subsystems.yaml).

## 1. Provenance

- **Baseline (verified by git ancestry, not a narrative claim):** `58a96674b5cc77bd9da0877d2adaad64abe41b85` — "Resolve SQLite row company matches", 2026-09-13 11:00:57+02:00. This is `origin/deployment/render-turso-r2`'s tip and the sole common ancestor of every `docs/re-phase2-ws0X` branch (confirmed with `git merge-base` across all 11 pairs; each branch is 1–3 commits ahead of it, doc-only).
- **Integration branch:** `docs/phase3-integration`, created from that baseline, with `docs/re-phase2-ws01`…`ws11` merged in sequentially (0 conflicts).
- **Unmerged reference branch:** `feature/admin-analytics-final-production` @ `ce3718b0` — 16 commits ahead / 179 behind the baseline. Its content is cited only where explicitly labelled `UNMERGED`; see §4.
- **Live production state: UNKNOWN.** Every production claim below is "recorded" (from a handoff/report/ledger document), never verified against a running endpoint or host. See §5.

## 2. What Runr is

Runr is a job-acquisition and application-assistance product with four moving parts sharing one backend:

1. **Acquisition** — scheduled producers (LinkedIn, employer career sites) collect job postings and company data outside of any customer request, running on a VPS, never on Render (`render.yaml` L82, L199).
2. **Publication and catalog** — acquired records are normalized, deduplicated, identity-reconciled against a company registry, and published into a queryable job catalog (Turso/libSQL in production, SQLite locally).
3. **Customer application services** — the web app lets a signed-in customer browse personalized jobs, generate tailored CVs/cover letters, track applications, and (optionally) prepare Assisted Apply packages.
4. **Assisted Apply extension** — a browser extension that fills employer application forms from prepared data. It is explicitly **never-submit**: it stops at the last step before a terminal submit control, enforced by a runtime guard (`installSubmissionGuard`) and a static boundary scan, independent of this documentation. See the standing safety-posture decision recorded in project memory (`runr-extension-safety-posture`) and [05-subsystems/assisted-apply.md](05-subsystems/assisted-apply.md).

Billing (Creem) gates paid features; auth is Clerk-issued bearer tokens with a legacy opaque-token fallback. Retired: an admin analytics/operations dashboard, removed in `dd47acf9` (2026-09-10) by owner decision — see [06-history-and-provenance/retired-features.md](06-history-and-provenance/retired-features.md). No workstream documents it as a live feature; only its residue is tracked (§4 of that doc, and C7/U7 below).

## 3. Cross-subsystem data flow

Full detail: [01-architecture/data-flow.md](01-architecture/data-flow.md). Summary:

```
VPS timers (systemd)
  → LinkedIn / employer producers (backend/acquisition, backend/connectors)
  → per-source SQLite state + exports (backend/repositories/sqlite_acquisition.py)
  → company identity canonicalization + enrichment (backend/application/company_*)
  → publisher (scripts/publish_producer_states.py, backend/acquisition/publication.py, job_publication_completeness.py)
  → catalog store (Turso/libSQL in production; SQLite locally)
  → HTTP API (backend/api/server.py, route registry)
  → customer frontend (/jobs) and, when prepared, the Assisted Apply extension
```

Auth (Clerk bearer tokens), billing (Creem webhooks/checkout) and object storage (R2 via S3 API, for CV/document artifacts) cross-cut this pipeline rather than sitting inside it.

## 4. Branch divergence and historical provenance

Full detail, including every retained branch's disposition: [06-history-and-provenance/branch-divergence.md](06-history-and-provenance/branch-divergence.md). Headline facts, all verified by git ancestry:

- The repository has **one active line of development** — the baseline above. `feature/admin-analytics-final-production` is a reference-only side branch; most of its content is either patch-equivalent to the baseline already (`git cherry` shows `-`) or covered by an explicit review ticket (T03, T04, T05 — see §6).
- 60 local and 26 remote-tracking branches existed at the 2026-09-14 clean-slate closure; none were deleted. Their disposition (historical/ancestor/valuable-bundled/customer-personal) is fully recorded in the branch-divergence doc — it is not re-derived here.
- The clean-slate preservation work (archive, git bundle, stash export, hash verification) that produced this disposition is **complete and verified**; it is not reopened by Phase 3. See [06-history-and-provenance/branch-divergence.md](06-history-and-provenance/branch-divergence.md) §3 and `clean-slate-2026-09-13/clean-slate-final-report.md` (external evidence, cited not duplicated).

## 5. Reconciliation of conflicting subsystem claims

The independent Phase-1 delta audit (`phase-1-delta-audit-2026-09-13.md`, verdict **APPROVED FOR PHASE 2**) checked every claim in the evidence package against the baseline with git commands and corrected several before Phase 2 started; those corrections (N-1…N-12) are already folded into `evidence-package-2026-09-13/contradictions-and-unknowns.md` and into [06-history-and-provenance/known-gaps.md](06-history-and-provenance/known-gaps.md), which is the canonical, already-reconciled table of every contradiction (C1–C10) and unknown (U1–U13). This overview does not re-litigate them; it states the two with the widest blast radius:

- **C1/C2/C9 — three disagreeing "current production" records.** `RELEASE_LEDGER.md` says `3c5e609a` (stale, 250 commits behind); the production-completion handoff says Render is on `5dfdd106`; an untracked 2026-09-12 report says the VPS is on `4a1b1df5`. All three are ancestors of the baseline and all three are **documentary, not live-verified**. Resolving which (if any) is still running requires host/dashboard access this documentation effort does not have (U1, U2) — recorded as a verification task, not as a claim that any of them is wrong.
- **C7/U7 — admin-retirement residue, corrected by audit finding N-1.** The original evidence package described `POST /analytics/events` and the customer `/dashboard` analytics payload as live-but-unrouted. The independent audit reproduced the opposite: both are **unreachable at baseline** (the routes are never registered; requests 404). The only surviving writer of `analytics_events` is worker-side (`stage_adapters.py`). The open item is not "is this live" but "delete the dead handler/frontend emitter, or re-register it" — an owner decision, tracked as backlog candidate T18.

Every other C#/U# item, and every workstream-local gap (`WS<n>-G<k>`), is catalogued with its owning workstream, target doc and status in [06-history-and-provenance/known-gaps.md](06-history-and-provenance/known-gaps.md). Facts this synthesis cannot verify stay **UNKNOWN** there; none are asserted as resolved here.

## 6. Remaining work

The full, deduplicated backlog is `RUNR_REVERSE_ENGINEERING_2026-09-10/clean-slate-2026-09-13/linear-ticket-candidates.md` (external evidence directory; GitHub is the source of truth for the documentation and evidence a ticket cites, Linear owns status/priority/assignment — see [docs/tickets/TEMPLATE.md](../tickets/TEMPLATE.md)). It combines:

- The 10 active clean-slate preservation/review tickets (T01, T03–T06, T08, T10–T12, T14) carried forward unchanged, plus 5 closed ones (T02, T07, T09, T13, T15) recorded as done with evidence and **not reopened**.
- 9 new, evidence-backed, outcome-grouped candidates (T16–T24) added in Phase 3, consolidating the ~60 workstream-local gaps (`WS<n>-G<k>`) found across WS-1…WS-11 into bounded tickets — never one ticket per file, commit or gap ID.

## 7. Reading order

New to the codebase and need the full picture: [01-architecture/backend-api.md](01-architecture/backend-api.md) → [01-architecture/backend-workers-and-orchestration.md](01-architecture/backend-workers-and-orchestration.md) → [05-subsystems/acquisition-and-collectors.md](05-subsystems/acquisition-and-collectors.md) → [05-subsystems/publication-and-catalog.md](05-subsystems/publication-and-catalog.md) → [03-data/schema-and-migrations.md](03-data/schema-and-migrations.md) → [02-deployment/render.md](02-deployment/render.md) and [02-deployment/vps-runtime-and-acquisition-timers.md](02-deployment/vps-runtime-and-acquisition-timers.md). For a specific task, start at [docs/INDEX.md](../INDEX.md) instead.

---

*This documentation is independently reviewed, not independently verified. Every "recorded"/"documentary" production claim above still needs the live check named next to it (§5, `known-gaps.md`) before anyone treats it as current truth.*
