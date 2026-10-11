> Source: deployment/render-turso-r2 | SHA: 58a96674 | Verified: 2026-09-14

# Applicant intelligence (Phase G, blocked) (WS-3 secondary)

Secondary doc; primary is [acquisition-and-collectors.md](acquisition-and-collectors.md). Scope: `backend/acquisition/phase_g.py` — applicant-count normalization, the applicant-source gate (all sources **blocked**), the legacy portal audit gate, Pro-facing competition views and the deterministic priority formula — plus its enforcement point in the acquisition store and its consumption by the personalized Jobs ranking.

Method: static reading at `58a96674`. Nothing executed; production state is UNKNOWN.

---

## 1. Purpose and user-facing capabilities

Phase G "applicant intelligence" would show job-seekers how many applicants a posting has (competition) and fold that into job priority. At the baseline it is **deliberately inactive**: no applicant-count source is approved, and `PHASE_G_PRODUCTION_ACTIVATED = False` (phase_g.py:33) blocks the gate in production. What exists:

| Capability | State | Main code |
|---|---|---|
| Applicant-count parsing | Implemented (pure) | `parse_applicant_count` L84, `explicit_applicant_count` L132, `has_applicant_evidence` L148 |
| Snapshot normalization with a safe allow-list payload | Implemented (pure) | `normalize_applicant_snapshot` L233 (payload keys L257–265: no candidate/personal data can cross) |
| Applicant-source gate | Implemented, **closed** | `applicant_source_gate` L205: requires an approved `APPLICANT_SOURCE_DECISIONS` entry + 7 documented audit fields; all 9 connectors decided `blocked` (L39–49) + `production_activation_disabled` (L214–215) |
| Source decisions | All blocked, evidence-backed | `APPLICANT_SOURCE_DECISIONS` L39–49 (LinkedIn: authorization unavailable/terms risk; Greenhouse/Lever/Arbeitsagentur: no applicant-count field; others: authorization/cost/quality unverified) |
| Legacy portal audit gate | Implemented, separate from Phase G approval | `portal_audit_gate` L167 ("does not approve Phase G", docstring L168); enforced for portal targets in the store and Phase A scheduler |
| Competition view (Pro) | Implemented (pure projection of stored columns) | `build_applicant_competition` L328 (public fields nulled unless `include_pro`; Pro block L410–417; low-competition/recently-verified alerts L405–409) |
| Priority formula | Implemented, missing data stays neutral | `build_priority` L421: score = 0.60·user_fit + 0.20·freshness + 0.20·competition (`PRIORITY_WEIGHTS` L32, formula `phase_g_priority_v1`) |
| Freshness classification | Implemented | `freshness_status` L286 (fresh ≤30 h, aging ≤72 h, stale) |

## 2. Owned paths and governing instructions

| Path | Lines | Role |
|---|---:|---|
| `backend/acquisition/phase_g.py` | 467 | all Phase G primitives (policy `phase_g_applicant_intelligence_v1`, L29) |
| `backend/acquisition/phase_b.py` | — | imports `is_portal_target` (L16) |
| Enforcement + ranking (not owned, cited) | — | `backend/repositories/sqlite_acquisition.py:24–25,1458–1462` (gate at ingest; `applicant_snapshots_blocked` counter L1433/1479); `backend/application/acquisition_scheduler.py:33,955` (portal gate); `backend/application/personalized_jobs_service.py:29,1418–1419,1488,1761,1784` (competition + priority in Jobs ranking — service owned by WS-4) |

Governing docs: module docstring (L1–6: "deliberately inactive in production until a source decision is documented and approved"); weights are deliberately non-configurable at runtime (comment L31–33). No Phase G report exists in the baseline `docs/` corpus (checked).

## 3. Entry points

No CLI, no route, no unit. Phase G code is invoked only:
1. at observation ingest in the store (`sqlite_acquisition.py:1458` — every delivered batch passes `applicant_source_gate`; producer targets use `connector=producer_<source>` precisely so this gate cannot block source delivery, `scripts/publish_producer_states.py:536–539`);
2. in the Jobs read path (`personalized_jobs_service.py` builds competition/priority per row; `include_pro` gates Pro visibility).

## 4. Inputs, outputs, storage and dependencies

- Input: canonical job rows with `applicant_latest_*`/`applicant_first_*` columns (written by migrations `037_phase_g_applicant_competition` / `041_phase_g_applicant_boundary`, `backend/repositories/sqlite_migrations.py:3415,3436` — WS-5 owns the registry) and target config `phase_g_applicant_audit` / `phase_g_audit`.
- Output: pure dicts (competition view, priority, gate verdicts). No persistence, no raw payload storage (docstring L5: "never persist raw payloads").
- Dependencies: none beyond stdlib; `personalized_jobs_service` supplies match intelligence (WS-4 [05-subsystems/personalized-jobs-and-customer-app-services.md](personalized-jobs-and-customer-app-services.md)).

## 5. Important call/data flows

1. Producer/publisher delivery → store `ingest` builds `target_for_gate` from the stored target row → `applicant_source_gate(target)` → since no connector is approved and `PHASE_G_PRODUCTION_ACTIVATED=False`, the gate always reports missing requirements; portal targets additionally must pass `portal_audit_gate` or the ingest raises `portal_audit_not_passed:…` (`sqlite_acquisition.py:1458–1462`). Applicant snapshots are counted as `applicant_snapshots_blocked`.
2. Jobs ranking → `build_applicant_competition(row, include_pro)` (nulls public fields when not Pro) → `build_priority(row, match, competition)` → neutral 50.0 defaults when applicant data is missing (L441); stale competition scores are discarded (L439–440).

## 6. Invariants, failure handling and recovery

| Invariant | Where |
|---|---|
| No applicant source may activate without a documented, approved decision + 7 documented audit fields | `applicant_source_gate` L205–230 |
| Production activation is compile-time false; not runtime-configurable | L31–33, L214–215 |
| Safe payload allow-list: no candidate identity/application data crosses the boundary | L255–265 |
| Missing values are `unknown`, never invented; ranges stay ranges; uncertain counts stay neutral in ranking | L84–129, L441 |
| Structured feeds are not applicant sources (decisions are evidence-backed, not an allow-list) | L36–38 comment |
| Portal gate is legacy and separate: passing it does not approve Phase G | L168, scheduler use L955 |

No recovery path needed (pure functions; nothing persisted).

## 7. Relevant tests and safe verification commands (not executed in Phase 2)

- `tests/test_phase_g_applicant_competition.py` (gate, decisions, parsing, priority).
- Related: `tests/test_phase_a_rc016…rc021` (portal gates), `tests/test_producer_state_delivery.py` (producer connector separation).

Safe commands, not executed in Phase 2:

```bash
node scripts/run-python.cjs -m pytest -q tests/test_phase_g_applicant_competition.py
git grep -n "PHASE_G_PRODUCTION_ACTIVATED" 58a96674 -- backend
git grep -l "phase_g" 58a96674 -- tests   # full Phase G test inventory (defer to WS-10)
```

(WS-10 owns the definitive test inventory; the second command's file names were not individually confirmed and are listed only as candidates — see WS3-G14.)

## 8. Historical decisions and supporting commits

| Commit | Subject | Decision |
|---|---|---|
| Phase G era (see primary §8 commit list) | applicant competition + boundary migrations | migrations `037`/`041` (WS-5 registry) |
| `a2c6fea7` | reject easy apply from display feed | Easy Apply evidence retained at producer, rejected at publication — complements the `easy_apply_marker` here |
| `dd47acf9` | remove admin surfaces | applicant review UI (if any) removed with admin routes |

## 9. Current implementation status

| Capability | Classification |
|---|---|
| Applicant-count parsing/normalization | VERIFIED (scope: static full read of `phase_g.py`; deterministic parsing traced) |
| Competition/priority projections | VERIFIED (scope: static; formula and neutral defaults traced; consumed at `personalized_jobs_service.py:1418–1419`) |
| Applicant-source gate, all sources blocked | VERIFIED (scope: static; all 9 decisions `blocked`; `PHASE_G_PRODUCTION_ACTIVATED=False`; enforced at store ingest L1458) |
| Any approved applicant data source | PLANNED-NOT-IMPLEMENTED (no approved source exists; activation requires documented decisions per the gate — no ticket at baseline; **WS3-G13**) |
| Pro visibility split | VERIFIED (scope: static; public fields nulled without `include_pro`) |
| Legacy portal audit gate | VERIFIED (scope: static; enforced in store + scheduler) |

### Deployment evidence (documentary only — not live verification)
- None specific to Phase G at the baseline. Untracked production reports (T06) record no applicant-intelligence activity; LIVE PRODUCTION UNKNOWN.

## 10. Confirmed gaps and unresolved questions

| ID | Gap |
|---|---|
| **WS3-G13** | No path exists to approve an applicant source (gate requires decisions + audit docs that no ticket currently tracks). Confirm whether Phase G is planned, parked or to be retired. |
| **WS3-G14** | Phase G test coverage beyond `test_phase_g_applicant_competition.py` was not inventoried here; defer to WS-10's map. |
| U7-adjacent | `applicant_latest_*` columns and migrations 037/041 remain in the schema while no source can write them (residue risk; coordinate WS-5). |

## Agent context and remaining work

**(a) Agent context packet — applicant intelligence**
- Required reading: this doc; `backend/acquisition/phase_g.py` (full); `backend/repositories/sqlite_acquisition.py` L1440–1490; `backend/application/personalized_jobs_service.py` L1400–1500 (WS-4).
- Allowed paths: `backend/acquisition/phase_g.py`; read-only reference to the enforcement/ranking sites above.
- Tests to run: `node scripts/run-python.cjs -m pytest -q tests/test_phase_g_applicant_competition.py`.
- Prohibited: flipping `PHASE_G_PRODUCTION_ACTIVATED` or approving any `APPLICANT_SOURCE_DECISIONS` entry without a documented owner decision; collecting applicant data from a structured job feed.

**(b) Registry proposal**

| subsystem id | name | owned globs | primary doc | test globs | owner |
|---|---|---|---|---|---|
| `applicant-intelligence` | Phase G applicant intelligence (blocked) | `backend/acquisition/phase_g.py` | this doc (secondary to `05-subsystems/acquisition-and-collectors.md`) | `tests/test_phase_g_*.py` | WS-3 |

**(c) Gap/ticket candidates**
1. WS3-G13: owner decision on Phase G (approve a source with documented audit, or retire the projections and migrations 037/041 residue with WS-5).
2. WS3-G14: complete the Phase G test inventory with WS-10.
