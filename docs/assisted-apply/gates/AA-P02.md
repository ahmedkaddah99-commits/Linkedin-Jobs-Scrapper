# AA-P02 policing gate — PASS

Date: 2026-08-01
Branch: `deployment/render-turso-r2`
Reviewed commit: `9e973e1` (`Complete Assisted Apply foundation through AA-221`)
Prior gate baseline: `5ac36c7` (`Perform policing gate AA-P01`)
Gate report commit: `9e973e1` (amended with this final report)

## Verdict

**PASS.** The three blocking findings from the initial review were remediated
and independently rerun. No unresolved safety, ownership, data-integrity, or
test defect remains in the reviewed AA-210 through AA-221 scope.

## Remediation evidence

### Submission ownership

`packages/ats-core/src/submission-guard.ts` now blocks synthetic terminal
clicks, submit events, Enter, requestSubmit, form.submit, fetch, XHR, and
navigation signals, while allowing a trusted user terminal gesture to reach
the existing explicit confirmation path. The previous failing test now passes:
`apps/browser-extension/tests/e2e/assisted-apply.spec.ts:634-675`.

### Approved-package integrity

`backend/domain/application_package.py:469` now rejects approved-content
mutation at the serialization/extension-payload boundary by validating the
approved content hash before output. Direct post-approval list mutation is
covered by `tests/test_aa03_application_package.py` and raises
`ApplicationPackageMutationError`; guarded `replace_content()` still requires
a new version.

### Reproducible review boundary

AA-210 through AA-221 implementation, tests, architecture records, and this
gate report are committed in `e4ce931`. The unrelated
`frontend/src/pages/CareerProfilesPage.jsx` change remains outside the commit.

## Invariant checklist

| Invariant | Evidence | Result |
|---|---|---|
| Protocol validation/versioning and replay/forgery rejection | `packages/extension-messages/src/index.ts`; AA-210 tests | PASS |
| Provenance continuity and legacy fallback | tailored-document pipeline and tests | PASS |
| Immutable package precedence and mutation safety | `ApplicationPackage.assert_content_hashes`, `to_dict`, `to_extension_payload`; AA-212 tests | PASS |
| Durable state ownership, TTL, expiry, retry | AA-213 domain/service/routes/tests | PASS |
| Optional permission flow and sidepanel-only prompting | AA-214 command/permission tests | PASS |
| Local-only tab/window IDs and restart behavior | AA-215 local-session tests and worker code | PASS |
| Declarative adapter boundary | AA-216 closed action union and static scan | PASS |
| Executor/navigation isolation | AA-216/218 tests and boundary scan | PASS |
| Submission-path denial with explicit user confirmation | submission guard plus full Playwright suite | PASS |
| Reconciliation idempotency and ambiguity | AA-217 unit and AA-202 Playwright fixtures | PASS |
| Complex-control verification | AA-218 unit suite | PASS |
| Fresh document grants and exact upload intent | AA-221 backend and Playwright fixtures | PASS |
| No broad permissions, backend browser IDs, or raw telemetry | manifest/static review and targeted search | PASS |
| Migration safety | migration tests and additive grant-intent migration | PASS |
| No TODO/FIXME placeholders or weakened tests | targeted search and test review | PASS |

## Commands and results

- `git branch --show-current` → `deployment/render-turso-r2`.
- `.venv\Scripts\python.exe --version` → Python 3.12.7.
- `.venv\Scripts\python.exe -m pytest tests/test_aa03_application_package.py tests/test_aa213_preparation.py tests/test_assisted_apply_document_grants.py tests/test_tailored_document_generation.py tests/test_database_migrations.py -q` → **76 passed, 4 subtests passed**.
- `.venv\Scripts\python.exe -m ruff check backend tests` → passed.
- `npm run test:unit` → **20 files, 174 tests passed**.
- `npm run typecheck` → passed.
- `npm run verify:assisted-apply-boundary` → passed.
- `npm run verify:manifest` → passed.
- `npm run test:e2e` → **19 passed**.
- `git diff --check` → passed before commit.
- `git status --short` after commit → only unrelated pre-existing `frontend/src/pages/CareerProfilesPage.jsx` remains modified.

## Authorization

**AA-P02: PASS.** The reviewed AA-210 through AA-221 foundation is cleared
for the next authorized phase.
