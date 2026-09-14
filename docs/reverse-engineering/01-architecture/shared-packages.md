> Source: deployment/render-turso-r2 | SHA: 58a96674 | Verified: 2026-09-14

# Shared packages (`packages/**`)

Secondary WS-9 doc. It covers public exports, internal dependencies and consumers. For the never-submit boundary and flows, see the primary doc [assisted-apply.md](../05-subsystems/assisted-apply.md). The build is described in [apps-and-extensions.md](apps-and-extensions.md).

## 1. Purpose

Two private, source-only TypeScript packages used by the browser extension:
- `@runr/ats-core` holds ATS detection, inspection, matching and planning adapters, the central DOM executor, the runtime submission guard, answer policy, dynamic-form observation, the page bridge, reconciliation and telemetry.
- `@runr/extension-messages` holds the message and payload types plus runtime validators shared by the worker, side panel, content scripts and the Runr web protocol.

Neither has a build step, its own tests or a lockfile. `exports` point directly at `.ts` sources, and the packages are consumed through `file:` dependencies plus `tsconfig` `paths` in `apps/browser-extension/tsconfig.json`. No backend or frontend code imports them (by `git grep "@runr/"` at 58a96674).

## 2. Owned paths (12 files)

| Path | Lines |
|---|---:|
| `packages/ats-core/package.json` | 12 |
| `packages/ats-core/src/index.ts` | 1763 |
| `packages/ats-core/src/declarative-actions.ts` | 337 |
| `packages/ats-core/src/policy.ts` | 334 |
| `packages/ats-core/src/reconciliation-spike.ts` | 218 |
| `packages/ats-core/src/telemetry.ts` | 202 |
| `packages/ats-core/src/page-bridge.ts` | 143 |
| `packages/ats-core/src/dynamic-form.ts` | 98 |
| `packages/ats-core/src/submission-guard.ts` | 97 |
| `packages/ats-core/src/reconciliation.ts` | 2 |
| `packages/extension-messages/package.json` | 9 |
| `packages/extension-messages/src/index.ts` | 1170 |

Governing docs: AA architecture records `docs/architecture/assisted_apply_aa216_declarative_executor_2026-08-01.md`, `docs/architecture/assisted_apply_aa219_greenhouse_adapter_2026-08-01.md`, `docs/architecture/assisted_apply_aa220_lever_adapter_2026-08-01.md`; gate `docs/assisted-apply/gates/AA-P03.md`.

## 3. `@runr/ats-core` public surface

`packages/ats-core/package.json` exports: `.` → `src/index.ts`, `./policy`, `./dynamic-form`, `./page-bridge`. `index.ts` re-exports `./telemetry`, `./declarative-actions`, `./submission-guard` and `./reconciliation`, which re-exports `./reconciliation-spike` (L4-7).

| Module | Key exports |
|---|---|
| `index.ts` | Types `AtsType` (`"greenhouse" \| "lever"`, L9), `UploadFieldIntent`, `ApplicationDocumentKind`, `PageContext`, `DetectionResult`, `DetectedField`, `InspectedApplicationForm`, `ApplicationPackage*`, `FieldMatch`, `ApprovedFieldMatch`, `FieldExecutionResult`, `DocumentUpload*`, `FormValidationResult`, `SubmissionEvidence`; **`AtsAdapter`** (L171-188); `ATS_ADAPTER_CAPABILITIES` (L190); **`ADAPTER_SUBMISSION_CAPABILITY_FORBIDDEN`** (L207); `detectAtsFromUrl` (L219: `boards.greenhouse.io`, `*.lever.co`, https only); `uploadFieldIntentFor`; `StandardFactsAdapter` (L652), `GreenhouseAdapter` (L1163), `LeverAdapter` (L1422); `executeApprovedField` (L1172); `planGreenhouseApplication`, `planLeverApplication`; `uploadApplicationDocument` (L1507), `uploadGreenhousePdf`; fixture helpers `inspectGreenhouseFixture`, `runGreenhouseFixtureProof`, `inspectLeverFixture`, `runLeverFixtureProof`; production runners `runGreenhouseStandardFacts` (L1636), `runLeverStandardFacts` (L1721) |
| `declarative-actions.ts` | `DeclarativeAction` union (fill_text/rich_text, select_combobox_option, select, set_date, set_checkbox/radio, add_repeatable_section, upload_document, propose_intermediate_navigation), `DeclarativePlan` (adapter `greenhouse\|lever`), `NativeValueAction`, `ActionExecution`, `isDeclarativeAction`, `isDeclarativePlan`, `planFillAction`, `authorizeIntermediateNavigation` (L102), `readControlValue`, `inspectControlValidation`, `verifyControlValue`, `writeControlValue`, `executeNativeValueAction`, `executeComboboxOptionAction`, `executeDeclarativeAction` (L320). Header: "adapter plans are data; only this module may execute DOM mutations." |
| `submission-guard.ts` | `installSubmissionGuard(document)`, `SubmissionGuard`, `SubmissionGuardEvent` (behaviour: primary §6.1 L3) |
| `policy.ts` (`./policy`) | Source constants (`profile_verified`, `scoped_preference`, `ai_suggestion`, `context_dependent`), sensitivities (standard/personal/legal/demographic), scopes, `ProfileValue`, `validateProfileValue`, `PolicySettings`, `FieldDecision`, `decideFieldAction` (L180). Mirrors `backend/domain/application_policy.py` using shared fixtures `tests/fixtures/policy_fixtures.json`. |
| `dynamic-form.ts` (`./dynamic-form`) | `observeDynamicForm`, `DynamicFormMonitor`, `DynamicFormSnapshot`, `DynamicFormChangeReason` |
| `page-bridge.ts` (`./page-bridge`) | `PAGE_BRIDGE_REQUEST_EVENT`/`RESPONSE_EVENT`, `installPageContextBridge` (MAIN world), `requestPageContextSet`, type guards: sets controlled (React-style) field values through CustomEvents |
| `reconciliation-spike.ts` | `ReconciliationCandidate`, `reconcileVisibleEntries`, `scoreReconciliationCandidate`, `verifyApprovedContentHash`, `normalizeReconciliationText` (repeatable experience/education) |
| `telemetry.ts` | `createTelemetryReporter`, `TelemetryTransport`, `executionStatusToOutcome`, `executionStatusToErrorCategory`, `uploadStatusTo*` |

Internal dependency: `packages/ats-core/src/telemetry.ts:19` imports from `@runr/extension-messages`. `extension-messages` imports nothing from ats-core, so there is no cycle.

## 4. `@runr/extension-messages` public surface

Single export `.` → `src/index.ts`.

| Group | Exports |
|---|---|
| Portals | `SupportedAts = "greenhouse" \| "lever"` (L1) |
| Panel ↔ worker | `PanelRequest` (L102), `PanelResponse` (L622), `isPanelRequest`, `isPanelResponse`, `AssistedApplyTabState`, `ExtensionConnectionState`, `ExtensionSessionSummary`, `AssistedApplyPreferences`, `AssistedApplyPreferenceUpdate`, `PreparationPanelState/Status` |
| Web ↔ extension | `RunrWebLaunchRequest` (L146), `isRunrWebLaunchRequest`; `RunrWebLinkedInConnectionsRequest/Response`; preparation protocol `ASSISTED_APPLY_PREPARATION_PROTOCOL = "runr.assisted_apply.preparation"`, `…_VERSION = 1`, `…_MAX_AGE_MS = 5 min` (L158-160), `AssistedApplyPreparationMessage` (L216), `isAssistedApplyPreparationMessage`, `AssistedApplyPreparationValidator` (L365) |
| Worker ↔ content | `ContentRequest` (L536), `isContentRequest`, `isApplicationPackageContentRequest`, `PackageExecutionMessage`, `DocumentUploadMessage`, `ContentRuntimeEvent`, fixture messages + `isExactGreenhouseFixtureUrl`/`isExactLeverFixtureUrl` |
| Package payload | `ApplicationPackagePayload` (L458), `ApplicationPackageJob`, `ApplicationPackageAnswer`, `ApplicationPackageDocumentMeta`, `ApplicationDocumentKind/MimeType`, `ApplicationCorrectionScope`, `APPLICATION_CORRECTION_SCOPE_OPTIONS`, `isApplicationPackagePayload` |
| Success / tracker | `PossibleSuccessEvidence(Category)`, `PendingApplicationConfirmation`, `TrackerConfirmationResult` + guards |
| Telemetry | `LifecycleStage`, `AggregateOutcome`, `ErrorCategory`, `AdapterHealthTelemetry`, `RemoteTelemetryConfig` + guards |

No message type expresses submission (primary §6.1 L5).

## 5. Consumers (at 58a96674)

| Consumer | Imports |
|---|---|
| `apps/browser-extension/entrypoints/background.ts` | ats-core `detectAtsFromUrl`, `uploadFieldIntentFor`; extension-messages types/guards |
| `apps/browser-extension/entrypoints/application-form.ts` | ats-core `installSubmissionGuard`, standard-facts runners, fixture inspectors, `uploadApplicationDocument`; `@runr/ats-core/dynamic-form`; extension-messages |
| `apps/browser-extension/entrypoints/controlled-field-bridge.ts` | `@runr/ats-core/page-bridge` `installPageContextBridge` |
| `apps/browser-extension/entrypoints/inactive-fixture-spike.ts` | ats-core (testing only) |
| `apps/browser-extension/entrypoints/sidepanel/App.tsx` | extension-messages (`APPLICATION_CORRECTION_SCOPE_OPTIONS`, `isPanelResponse`, types) |
| `apps/browser-extension/src/auth/connection-service.ts`, `apps/browser-extension/src/auth/protocol.ts`, `apps/browser-extension/src/documents/grant-validation.ts`, `apps/browser-extension/src/fixture-runner.ts`, `apps/browser-extension/src/preparation/external-command.ts`, `apps/browser-extension/src/review/panel-model.ts`, `apps/browser-extension/src/state/tab-state.ts`, `apps/browser-extension/src/success/possible-success-observer.ts` | extension-messages |
| `packages/ats-core/src/telemetry.ts` | extension-messages |
| Tests | 13 unit files import `@runr/*` (e.g. `apps/browser-extension/tests/unit/ats-core.test.ts`, `apps/browser-extension/tests/unit/messages.test.ts`, `apps/browser-extension/tests/unit/policy.test.ts`, `apps/browser-extension/tests/unit/aa216-declarative-actions.test.ts`) |
| Frontend (not an import) | `frontend/src/lib/assistedApplyLaunch.js`, `frontend/src/lib/assistedApplyPreparation.js`, `frontend/src/lib/linkedinSync.js` send messages that must match these shapes by hand (WS-8) |

## 6. Invariants
- `AtsAdapter` must never gain a key containing `submit`/`Submit`, a compile-time error via `ADAPTER_SUBMISSION_CAPABILITY_FORBIDDEN`.
- DOM mutation is confined to `declarative-actions.ts` (plus `page-bridge.ts` and `submission-guard.ts`), which is the exemption list of `apps/browser-extension/scripts/verify-assisted-apply-boundary.mjs:14`. Other ats-core files must not contain `.click(`, `submit(`, location assignment, Enter synthesis or navigation-event dispatch.
- Executor refuses buttons and terminal inputs (`packages/ats-core/src/declarative-actions.ts:215-217,239-241`). `propose_intermediate_navigation` never executes (L325-331).
- Both packages are scanned by `apps/browser-extension/scripts/verify-manifest.mjs` (source roots L99-104) for eval, remote import and submit-like calls.
- Policy decisions must stay in parity with `backend/domain/application_policy.py` (`apps/browser-extension/tests/unit/policy.test.ts`, `tests/test_application_policy.py`).

## 7. Tests and safe verification commands (not executed)
There are no package-local tests. Coverage is through `apps/browser-extension/tests/unit/{ats-core,policy,aa08-dynamic-forms,aa15-telemetry,aa202-reconciliation,aa216-declarative-actions,aa218-controlled-controls,aa219-greenhouse-adapter,aa220-lever-adapter,aa221-upload-intent,messages}.test.ts`.
```bash
npm --prefix apps/browser-extension run typecheck
npm --prefix apps/browser-extension run test:unit
npm --prefix apps/browser-extension run verify:assisted-apply-boundary
```

## 8. History
Created with the extension (`75bfdbc1`, `aa656b65`). Policy parity `e9701702`/`43d92507`, telemetry `7f2a352e`, adapters `2a46a5f0`/`66b2d039`, adapter `fill` removed from the contract `a4a53e61`. Full list in primary §8.

## 9. Status

| Capability | Classification |
|---|---|
| Package manifests, exports map, consumers | VERIFIED (scope: static — package.json files read; `git grep "@runr/"` consumer list at 58a96674) |
| `AtsAdapter` submit-name type constraint | VERIFIED (scope: static read of `index.ts:171-209`; not compiled) |
| Greenhouse / Lever adapters, executor, guard, policy, telemetry | IMPLEMENTED-UNVERIFIED (tests present, not run) |
| Generic multi-ATS planner, field intent, question model, resume match | PLANNED-NOT-IMPLEMENTED on baseline: UNMERGED (feature/admin-analytics-final-production @ ce3718b0), T03 |

UNMERGED package changes (commit `0d7f2b5c`): added UNMERGED `packages/ats-core/src/{application-context,field-intent,generic-inspector,generic-planner,generic-upload,question-model,resume-match}.ts`. Modified: `packages/ats-core/package.json` (8 new subpath exports, including `./declarative-actions`), `packages/ats-core/src/index.ts`, `packages/ats-core/src/declarative-actions.ts` (new `select_enhanced_options`; `DeclarativePlan.adapter` widened from `greenhouse|lever` to any `/^[a-z][a-z0-9_]{1,31}$/`), `packages/extension-messages/src/index.ts` (+26). The generic files contain no boundary-script forbidden tokens by grep, but indirect execution paths are not traced (primary §9.2).

### Deployment evidence (documentary only)
None specific to the packages; they ship inside extension bundles (primary §9).

## 10. Gaps
- **WS9-G7:** duplicated type definitions can drift: `AtsType` (`packages/ats-core/src/index.ts:9`) vs `SupportedAts` (`packages/extension-messages/src/index.ts:1`); `ApplicationDocumentKind` and `ApplicationPackageAnswer` are defined in both packages. The frontend message shapes are hand-maintained (no shared import).
- **WS9-G1** (boundary script scope and gating): see primary §10.
- `reconciliation.ts` is a 2-line re-export of `reconciliation-spike.ts`. The "spike" name hides production use (AA-217 production reconciliation). This is a naming question, not a defect.

## Agent context and remaining work
- **Context packet:** primary doc (a), plus `packages/ats-core/package.json`, `packages/ats-core/src/index.ts:1-220`, `packages/extension-messages/src/index.ts`. Changes to message shapes require updating the frontend senders (WS-8) and backend payload producers (WS-4) in lockstep.
- **Registry:** covered by the primary doc row (owned glob `packages/**`).
- **Ticket candidates:** consolidate duplicated portal and document types into `@runr/extension-messages` (WS9-G7); extend boundary scan to any new ats-core subdirectories and the UNMERGED generic modules if accepted (T03).
