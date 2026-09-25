> Source: deployment/render-turso-r2 | SHA: 58a96674 | Verified: 2026-09-14

# Branch divergence and historical provenance (WS-12 synthesis)

Secondary to [../00-overview.md](../00-overview.md). Primary doc for repository/docs classification: [repository-artifacts.md](repository-artifacts.md). Gap registry: [known-gaps.md](known-gaps.md). This doc does not re-run preservation work — the clean-slate closure it cites is complete and verified; nothing here reopens it.

## 1. The single active line

The baseline `58a96674b5cc77bd9da0877d2adaad64abe41b85` (`origin/deployment/render-turso-r2`) is the newest ref in the repository by commit date and is confirmed identical to `temp/runr-production-final`. Every `docs/re-phase2-ws0X` Phase-2 branch, and the Phase-3 integration branch `docs/phase3-integration`, descend from it directly (git-verified: it is the sole `git merge-base` of all 11 workstream branches, each 1–3 commits ahead, doc-only). There is **one** line of development; every other branch is either an ancestor of the baseline, a reference-only side branch, or historical.

## 2. The reference-only side branch

`feature/admin-analytics-final-production` @ `ce3718b0`: 16 commits ahead of the baseline, 179 behind. `git cherry 58a96674 ce3718b0` shows most of its subject-matter commits (CV editor/performance, frontend fixes) are **patch-equivalent** to commits already on the baseline (`-`) — nothing to restore there. The genuinely new content is:

| Content | Disposition | Ticket |
|---|---|---|
| Assisted-apply panel / generic ATS planner (commit `0d7f2b5cca64a2c3fa0d5efcf0a357fb574b04c3`, 48 paths under `apps/browser-extension`, `packages/ats-core`, `packages/extension-messages`, `backend/api/routes/assisted_apply_packages.py`) | Genuine unmerged product work; needs a never-submit boundary review before any merge | T03 |
| Company-enrichment / LinkedIn transport scripts (same commit, 18 paths under `scripts/`, `tests/`, `requirements*.txt`) | Genuine unmerged scripts/tests; needs per-file review | T04 |
| `Company-Urls/` dataset (554 tracked files, commit `0d7f2b5c`) | Archived and hash-verified (T02, closed); not part of the git line | — |
| Catalog/acquisition design docs, `.worktrees/` ignore rule | PRESERVE-AND-COMMIT; content absent from the baseline | T05, T06 |

No wholesale merge of this branch is planned or permitted; every accepted fragment lands through its own scoped review ticket rebased on the baseline.

## 3. Other branches with undecided content

- **`temp/runr-employer-final` @ `6ea7f460`:** 1 ahead / 42 behind. `git cherry` shows `+` — genuinely new employer-producer scheduling/browser-reuse work, absent from the baseline, conflicting with the baseline's own later changes to `scripts/master_employer_jobs_catalog.py`. Reviewed per capability, not merged wholesale (T01).
- **`temp/opencode-b-collectors` @ `66b61445`:** 1 ahead / 74 behind, `git cherry` `+`, but the sole added commit is a single 80-line handoff doc (`docs/OPENCODE_B_HANDOFF.md`), absent at baseline. UNMERGED, docs-only; resolved (audit N-7), no code content at risk.
- **`codex/master-linkedin-jobs-url`** (commits `ad56f747`, `2c8a3f31`, `0c4c4791`, `43757576`): design-spec and plan documents plus a `.gitignore` rule, none present at baseline. PRESERVE-AND-COMMIT (T05).

## 4. Resolved / historical, not to be re-opened

- `origin/codex/revert-referral-redesign` and `origin/feature/admin-operations-console`: both are ancestors of the baseline (0 ahead / 177 and 243 behind respectively) — historical, already superseded.
- Duplicate-subject commits `af94ef4c` / `2a42c332` ("feat: add branded social links to CVs"): both ancestors of the baseline; contents not diffed further (low-priority unknown, not a ticket).
- `848408f3` "provider spending stop" note: whether the spending stop is still in force is an operational unknown for WS-7/WS-3, not a documentation gap.
- The retired admin-analytics-dashboard line (`c62e2637`, `ce3718b0`, and stash@{1}'s untracked files): historical, not restored — see [retired-features.md](retired-features.md).
- 60 local and 26 remote-tracking branches (plus `origin/HEAD`) existed at the 2026-09-14 clean-slate closure; **none were deleted**. Their full disposition (customer-personal/historical-until-review, valuable-bundled, historical-pushed-to-origin, historical-equivalent-to-baseline) is recorded in the external evidence at `clean-slate-2026-09-13/clean-slate-final-report.md` §7 and is not reproduced field-by-field here to avoid a second copy going stale; that report's disposition stands as canonical.

## 5. Customer-personal branches (privacy-sensitive)

`Bodda`, `Helbo`, `Mohamed-Bahy` — never merged, 591 commits behind the baseline, contain personal CV/profile data for named individuals hosted on GitHub. Retained as-is pending an owner privacy decision; **must never be merged**. Tracked as T10. No path or content from these branches is reproduced in this documentation corpus.

## 6. Preservation record (verified, closed, not reopened)

The 2026-09-14 clean-slate closure (external evidence: `clean-slate-2026-09-13/clean-slate-final-report.md`, `dirty-state-closure.csv`) archived and hash-verified every dataset, stash and disposable artifact found in the working trees, then removed only the approved disposable material (18 worktrees, 5 stashes, agent-tool tmp artifacts). Verdict: `CLEAN SLATE ACHIEVED`. Evidence: archive SHA-256 `f854f1ea…`, full `sha256sum -c` re-verification 7,096/7,096 OK, git preservation bundle SHA-256 `93f4b932…` independently rebuilt and verified. This is **completed preservation work with evidence** — it is carried forward as done in the consolidated backlog (`linear-ticket-candidates.md`, closed candidates T02/T07/T09/T13/T15) and is not re-audited by Phase 3.

## 7. What remains open

Every open item above resolves to one of the active backlog candidates in `RUNR_REVERSE_ENGINEERING_2026-09-10/clean-slate-2026-09-13/linear-ticket-candidates.md` (T01, T03–T06, T08, T10–T12, T14, plus the Phase-3-added T16–T24). None of the branch-provenance facts in this doc are themselves open questions — where a fact could not be verified (for example, whether `temp/opencode-b-collectors`'s sibling `codex/*`/`recovery/*`/`phase-*` branches were individually re-checked against the baseline), it is recorded as UNKNOWN in [known-gaps.md](known-gaps.md) rather than implied here.

## RUN-43 / T43 worktree registry disposition (2026-09-19)

T43 removed the nine approved non-AppData worktree directories from the current Git registry while retaining their local branch refs. The primary checkout, nine AppData Runr worktrees including the RUN-43 implementation worktree, and the active RUN-31/T32 worktree remain registered. The RUN-31/T32 exception is retained because its Linear issue is In Progress and its worktree is an active implementation surface.

This disposition is operational cleanup evidence, not a branch merge or deployment. The primary checkout advanced externally from the T43 pre-delete observation `9b47874832140631ab2476cf680539fcdd9d82f0` to `9212ce6a87e63c33de6b33f1c740d0c19cae6499`; T43 did not reset, revert, stage, or commit the shared checkout. The complete per-path inventory and branch-retention checks are held in the local T43 audit manifest.
