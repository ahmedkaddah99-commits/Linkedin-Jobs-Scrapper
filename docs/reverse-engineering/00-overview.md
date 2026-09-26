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

## 8. Organization acceptance (Phase 4, independent review)

Reviewed by an agent independent of the Phase 2/3 authorship, against documentation commit `69763b79a4d26d42ba2744c825a7116cf1ee3476` (`docs/phase3-integration`) and its recorded source baseline `58a96674b5cc77bd9da0877d2adaad64abe41b85`. Method: automated path/link/ownership scripts over the full tree, plus three independent verification passes (each re-reading a disjoint set of subsystem docs cold and spot-checking ~15-20 cited file:line facts against live source) covering all 11 active subsystems, and one "agent handoff test" per active subsystem (start only from a ticket + its named minimal reading; identify entry point, dependencies, verification method; no implementation attempted). One corrections commit followed: `9cfc5c96ad58ec4073a87cdf0548ae16f0f925bb` (fixed a nonexistent test-file reference in `subsystems.yaml`'s `application-services` verification command; rechecked, the corrected test passes 17/17).

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 1 | Every known subsystem represented | PASS | 11 active `subsystems.yaml` ids + `synthesis`; every id routed from `docs/INDEX.md`. |
| 2 | Referenced paths/entry points/routes exist at the recorded SHA | PASS | Script confirmed every `owned_paths`, `entry_points` and `documentation` path in `subsystems.yaml` resolves to a tracked file at HEAD; ~50 cited `file:line` facts spot-checked by hand across the three passes matched source exactly, with two immaterial off-by-one/two line drifts (`applicant-intelligence.md`'s `PHASE_G_PRODUCTION_ACTIVATED` cite, `security-and-auth.md`'s log-message cite). |
| 3 | Route registration and callers support reachability claims | PASS | Directly verified `backend/api/routes/admin.py`'s `register_routes` (L23-33) registers none of `dashboard`/`users`/`tokens`/`secrets`/`analytics/events`; confirmed via the T18 handoff test and independently by the reviewer. |
| 4 | Source/tested/deployed states distinguished | PASS | Every doc read opens with or carries a "LIVE PRODUCTION = UNKNOWN" / "documentary only" framing; no live-production fact found stated as certain. |
| 5 | Preserved/unmerged work not described as integrated | PASS | `branch-divergence.md` and subsystem docs consistently label such content UNMERGED / PRESERVE-AND-COMMIT / "must never be merged," routed to T01/T03/T04/T05/T10. |
| 6 | Retired admin-dashboard work not proposed for restoration | PASS | Explicit "Prohibited: restoring..." language in every subsystem doc whose owned paths touch the retired surface; T18's re-registration option targets a non-admin customer route, guarded by `tests/test_customer_route_surface.py`. |
| 7 | Registry has explicit ownership/exclusions, no unexplained gaps/overlaps | PASS, 1 minor note | Script confirms 0 double-owned and 0 unowned tracked paths after applying `exclusions`, except two pre-existing stray debug-log files (`.backend_api_stderr.log`, `.backend_api_stdout.log`, tracked since a May 2026 commit, unrelated to this documentation effort) that no `owned_paths` glob covers. Not blocking; flagged for WS-11 to fold in or `.gitignore`. |
| 8 | Reader starts at `docs/INDEX.md` and finds each subsystem without scanning unrelated reports | PASS | INDEX's "Route by task" table links every subsystem doc directly; no subsystem requires reading an unrelated root-level report first. |
| 9 | Shared instructions don't conflict or force excessive context loading | PASS | 8 docs' "Agent context" required-reading lists spot-checked; longest is ~7-8 items, none contradictory. |
| 10 | Active ticket candidates have outcomes, exact context, boundaries, dependencies, meaningful acceptance criteria | PASS | All of T01-T24 read in full; each carries Outcome, Evidence, Source SHA/paths, Minimal required reading, Allowed/Prohibited changes, Dependencies, Acceptance criteria, Verification commands, and Priority/status per `tickets/TEMPLATE.md`. |
| 11 | Completed clean-slate tasks not reopened | PASS | `known-gaps.md` §4 explicitly marks T02/T07/T09/T13/T15 "do not re-open"; corpus-wide grep found no contradicting reference. |
| 12 | Backlog not acquisition-only | PASS | T01-T24 span security (T20), release/data-integrity gating (T16, T19), dead-code/cleanup (T11, T12, T14, T22), documentation correction (T05, T06, T24), CI/safety-boundary hardening (T23), host verification (T17), privacy (T10), data vaulting (T08), alongside acquisition-specific review (T01, T04, T21). |
| 13 | Known gaps have candidates or documented dispositions | PASS, with a follow-up | Nearly all `WS<n>-G<k>` gaps route to a ticket or an explicit disposition. Exception: `repository-artifacts.md`'s WS11-G2/G3/G4 and `security-and-auth.md`'s WS6-G5/G6/G9/G10/G11 are documented in their own doc's §10 but not folded into any T-number. Not silently dropped (still visible in-doc), but incomplete — returned to WS-6 and WS-11 owners to fold into a future ticket batch rather than reopening a full audit here. |
| 14 | No secrets or private customer documents in the deliverables | PASS | Credential-pattern grep (`AKIA…`, `sk-…`, PEM private-key headers) over `docs/` and the external `clean-slate-2026-09-13/` evidence directory returned no matches. |
| 15 | No production behavior changed by the documentation work | PASS | Every non-`docs/` file touched between baseline and HEAD is `AGENTS.md`/`ARCHITECTURE.md`, and both diffs are two-line pointer additions with no runtime content. |

**Agent handoff test — one representative task per active subsystem**, started from the ticket/doc packet alone, no implementation attempted: `http-api-cli` (T18), `workers-orchestration` (add-a-role simulation), `data-domain-model` (T16), `integrations-security` (T20), `acquisition` (T21), `application-services` (T22), `deployment-release-ci` (T19), `backend-test-suite` (locate-the-right-test simulation), `frontend` (route-classification simulation), `assisted-apply-extension` (T23), `docs-and-repository-artifacts` (classification-table spot check). **Result: PASS on all 11** — every entry point, dependency, and verification method was findable from the documented reading path alone; no case required undocumented exploration beyond routine implementation-detail lookups (e.g., grepping a symbol's other call sites, which the packets don't claim to enumerate).

**Blocking defects: none.** One non-blocking registry defect found and corrected (see corrections commit above). One non-blocking gap-ticketing completeness note (requirement 13) and one non-blocking registry-coverage note (requirement 7) are returned to their owning workstreams rather than fixed here.

---

*This documentation is independently reviewed, not independently verified. Every "recorded"/"documentary" production claim above still needs the live check named next to it (§5, `known-gaps.md`) before anyone treats it as current truth.*
