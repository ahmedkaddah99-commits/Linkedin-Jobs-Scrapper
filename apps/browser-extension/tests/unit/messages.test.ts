import { describe, expect, it } from "vitest";
import {
  APPLICATION_CORRECTION_SCOPE_OPTIONS,
  isAssistedApplyTabState,
  isContentRequest,
  isExtensionConnectionState,
  isExactGreenhouseFixtureUrl,
  isFixtureInspectionMessage,
  isFixtureProofMessage,
  isPanelRequest,
  isPanelResponse,
  isDocumentUploadMessage,
  isContentRuntimeEvent,
  isPendingApplicationConfirmation,
  isAdapterHealthTelemetry,
  AssistedApplyPreparationValidator,
  isAssistedApplyPreparationMessage,
  isApplicationPackagePayload,
  isRunrWebLaunchRequest,
} from "@runr/extension-messages";

describe("extension message boundaries", () => {
  it("validates the versioned preparation lifecycle and rejects stale, replayed, forged, and future messages", () => {
    const now = new Date("2026-08-01T12:00:00.000Z");
    const base = {
      protocol: "runr.assisted_apply.preparation",
      protocolVersion: 1,
      source: "web",
      preparationId: "prep_123",
      packageId: "aapkg_123",
      emittedAt: now.toISOString(),
    } as const;
    const start = { ...base, type: "start", messageId: "msg_start", capabilities: { adapters: ["greenhouse"], capabilities: ["fill", "document_attachment"] } };
    const validator = new AssistedApplyPreparationValidator({
      preparationId: "prep_123",
      packageId: "aapkg_123",
      now: () => now,
    });
    expect(isAssistedApplyPreparationMessage(start)).toBe(true);
    expect(validator.validate(start)).toBe(true);
    expect(validator.validate(start)).toBe(false);
    expect(isAssistedApplyPreparationMessage({ ...base, type: "permission_required", source: "extension", messageId: "msg_permission", capability: "document_attachment" })).toBe(true);
    expect(validator.validate({ ...base, type: "accepted", source: "extension", messageId: "msg_accept", result: { status: "accepted" } })).toBe(true);
    expect(validator.validate({ ...base, type: "progress", source: "extension", messageId: "msg_progress", result: { status: "progress", stage: "prepare", completed: 1, total: 2 } })).toBe(true);
    expect(validator.validate({ ...base, type: "ready_for_review", source: "extension", messageId: "msg_ready", result: { status: "ready_for_review", reviewId: "review_123" } })).toBe(true);
    expect(validator.validate({ ...base, type: "review_activate", messageId: "msg_activate", reviewId: "review_123" })).toBe(true);
    expect(validator.validate({ ...base, type: "review_activate", messageId: "msg_replay", reviewId: "review_123" })).toBe(false);

    const rejected = new AssistedApplyPreparationValidator({ preparationId: "prep_123", packageId: "aapkg_123", now: () => now });
    expect(rejected.validate(start)).toBe(true);
    expect(rejected.validate({ ...base, type: "needs_attention", source: "extension", messageId: "msg_attention", result: { status: "needs_attention", code: "manual_control" } })).toBe(true);
    expect(rejected.validate({ ...base, type: "retry", messageId: "msg_retry_attention", retryOf: "msg_attention" })).toBe(true);
    expect(rejected.validate({ ...base, type: "rejected", source: "extension", messageId: "msg_rejected", result: { status: "rejected", code: "conflict", retryable: true } })).toBe(true);
    expect(rejected.validate({ ...base, type: "retry", messageId: "msg_retry", retryOf: "msg_rejected" })).toBe(true);
    expect(rejected.validate({ ...base, type: "retry", messageId: "msg_retry_forged", retryOf: "msg_start" })).toBe(false);
    const cancelled = new AssistedApplyPreparationValidator({ preparationId: "prep_123", packageId: "aapkg_123", now: () => now });
    expect(cancelled.validate(start)).toBe(true);
    expect(cancelled.validate({ ...base, type: "cancel", messageId: "msg_cancel", reason: "user_requested" })).toBe(true);
  });

  it("fails closed for unknown fields, malformed capabilities, forged associations, stale messages, and future versions", () => {
    const now = new Date("2026-08-01T12:00:00.000Z");
    const start = {
      protocol: "runr.assisted_apply.preparation",
      protocolVersion: 1,
      type: "start",
      source: "web",
      messageId: "msg_start_2",
      preparationId: "prep_456",
      packageId: "aapkg_456",
      emittedAt: now.toISOString(),
      capabilities: { adapters: ["lever"], capabilities: ["fill"] },
    };
    expect(isAssistedApplyPreparationMessage({ ...start, candidate: { name: "raw" } })).toBe(false);
    expect(isAssistedApplyPreparationMessage({ ...start, tabId: 42 })).toBe(false);
    expect(isAssistedApplyPreparationMessage({ ...start, capabilities: { adapters: ["greenhouse", "greenhouse"], capabilities: ["fill"] } })).toBe(false);
    expect(isAssistedApplyPreparationMessage({ ...start, protocolVersion: 2 })).toBe(false);

    const validator = new AssistedApplyPreparationValidator({ preparationId: "prep_456", packageId: "aapkg_other", now: () => now });
    expect(validator.validate(start)).toBe(false);
    const stale = { ...start, messageId: "msg_stale", emittedAt: "2026-08-01T11:00:00.000Z" };
    expect(new AssistedApplyPreparationValidator({ preparationId: "prep_456", packageId: "aapkg_456", now: () => now }).validate(stale)).toBe(false);
  });

  it("preserves the existing unversioned web package-binding validator", () => {
    expect(isRunrWebLaunchRequest({
      type: "RUNR_WEB_BIND_APPLICATION_PACKAGE",
      bindingId: "aapkg_binding_123456789",
      applicationUrl: "https://jobs.example.test/apply/123",
    })).toBe(true);
  });

  it("bounds possible-success evidence and requires an explicit confirmation decision", () => {
    const evidence = {
      packageId: "aapkg_14",
      packageVersion: 2,
      adapter: "greenhouse",
      adapterVersion: "1.0.0",
      evidenceCategory: "success_banner",
      observedAt: "2026-07-18T12:00:00.000Z",
      uploadedDocuments: [{ documentId: "cv_v7", documentVersion: 7 }],
    };
    expect(isPendingApplicationConfirmation(evidence)).toBe(true);
    expect(isContentRuntimeEvent({
      type: "ASSISTED_APPLY_POSSIBLE_SUCCESS",
      evidence: {
        packageId: evidence.packageId,
        packageVersion: evidence.packageVersion,
        adapter: evidence.adapter,
        adapterVersion: evidence.adapterVersion,
        evidenceCategory: evidence.evidenceCategory,
        observedAt: evidence.observedAt,
      },
    })).toBe(true);
    expect(isPanelRequest({
      type: "RESPOND_TO_APPLICATION_CONFIRMATION",
      decision: "confirmed",
      evidence,
    })).toBe(true);
    expect(isPanelRequest({
      type: "RESPOND_TO_APPLICATION_CONFIRMATION",
      decision: "automatic",
      evidence,
    })).toBe(false);
    expect(isContentRuntimeEvent({
      type: "ASSISTED_APPLY_POSSIBLE_SUCCESS",
      evidence: { ...evidence, evidenceCategory: "page_text", rawHtml: "private" },
    })).toBe(false);
    expect(isPanelRequest({ type: "SUBMIT_APPLICATION" })).toBe(false);
  });
  it("exposes exactly the six explicit correction scopes", () => {
    expect(APPLICATION_CORRECTION_SCOPE_OPTIONS).toEqual([
      { value: "application", label: "This application" },
      { value: "country", label: "Applications in the country" },
      { value: "role", label: "Similar roles" },
      { value: "company", label: "This company" },
      { value: "global", label: "All future applications" },
      { value: "do_not_save", label: "Do not save" },
    ]);
  });

  it("accepts only known panel commands", () => {
    expect(isPanelRequest({ type: "GET_ACTIVE_TAB_STATE" })).toBe(true);
    expect(isPanelRequest({ type: "RUN_GREENHOUSE_FIXTURE_PROOF" })).toBe(true);
    expect(isPanelRequest({ type: "GET_EXTENSION_CONNECTION" })).toBe(true);
    expect(isPanelRequest({ type: "CONNECT_RUNR" })).toBe(true);
    expect(isPanelRequest({ type: "DISCONNECT_RUNR" })).toBe(true);
    expect(
      isPanelRequest({
        type: "UPDATE_ASSISTED_APPLY_PREFERENCES",
        permitSensitiveAutofill: true,
        permitDemographicAutofill: false,
      }),
    ).toBe(true);
    expect(
      isPanelRequest({
        type: "UPDATE_ASSISTED_APPLY_PREFERENCES",
        permitSensitiveAutofill: "yes",
        permitDemographicAutofill: false,
      }),
    ).toBe(false);
    expect(isPanelRequest({ type: "SUBMIT_APPLICATION" })).toBe(false);
    expect(isPanelRequest(null)).toBe(false);
  });

  it("validates the sanitized preparation panel state and action surface", () => {
    const statuses = [
      "permission_required", "queued", "preparing", "ready_for_review", "review_activated",
      "needs_attention", "interrupted", "retry_required", "auth_lost", "expired", "cancelled",
    ] as const;
    for (const status of statuses) {
      expect(isPanelResponse({
        ok: true,
        preparation: { status, ats: "greenhouse", completedCount: 2, totalCount: 3 },
      })).toBe(true);
    }
    expect(isPanelResponse({
      ok: true,
      preparation: { status: "needs_attention", ats: "lever", completedCount: 1, totalCount: 2, reason: "manual review required" },
    })).toBe(true);
    expect(isPanelResponse({
      ok: true,
      preparation: { status: "ready_for_review", ats: "greenhouse", completedCount: 2, totalCount: 3, tabId: 7 },
    })).toBe(false);
    expect(isPanelResponse({
      ok: true,
      preparation: { status: "ready_for_review", ats: "greenhouse", completedCount: 2, totalCount: 3, candidate: "private" },
    })).toBe(false);
    expect(isPanelRequest({ type: "GET_ASSISTED_APPLY_PREPARATION" })).toBe(true);
    expect(isPanelRequest({ type: "RETRY_ASSISTED_APPLY_PREPARATION" })).toBe(true);
    expect(isPanelRequest({ type: "CANCEL_ASSISTED_APPLY_PREPARATION" })).toBe(true);
    expect(isPanelRequest({ type: "ACTIVATE_ASSISTED_APPLY_PREPARATION" })).toBe(true);
    expect(isPanelRequest({ type: "SUBMIT_ASSISTED_APPLY_PREPARATION" })).toBe(false);
  });

  it("bounds explicit replacement commands to unique field intents", () => {
    const applicationPackage = {
      packageId: "aa08", jobId: "job-aa08", version: 1, schemaVersion: 1,
      job: { jobId: "job-aa08", title: "Engineer", company: "Acme", portal: "greenhouse", location: "Berlin" },
      answers: [], documents: [], warnings: [],
      policy: { permitSensitiveAutofill: false, permitDemographicAutofill: false, requireLegalAnswerConfirmation: true },
    };
    expect(isPanelRequest({
      type: "RUN_GREENHOUSE_APPLICATION_PACKAGE", package: applicationPackage,
      replaceFieldIntents: ["application.city"],
    })).toBe(true);
    expect(isPanelRequest({
      type: "RUN_GREENHOUSE_APPLICATION_PACKAGE", package: applicationPackage,
      replaceFieldIntents: ["application.city", "application.city"],
    })).toBe(false);
    expect(isPanelRequest({
      type: "RUN_GREENHOUSE_APPLICATION_PACKAGE", package: applicationPackage,
      replaceFieldIntents: ["application.city;submit"],
    })).toBe(false);
  });

  it("validates structured Career Memory sections while retaining v1 compatibility", () => {
    const legacy = {
      packageId: "aa-structured", jobId: "job-structured", version: 1, schemaVersion: 1,
      job: { jobId: "job-structured", title: "Engineer", company: "Acme", portal: "lever", location: "Remote" },
      answers: [], documents: [], warnings: [],
      policy: { permitSensitiveAutofill: false, permitDemographicAutofill: false, requireLegalAnswerConfirmation: true },
    };
    expect(isApplicationPackagePayload(legacy)).toBe(true);
    const structured = {
      ...legacy,
      candidate: { firstName: "Ada", lastName: "Lovelace", fullName: "Ada Lovelace", email: "ada@example.com", phone: "+49 123", source: "career_memory", approved: true, provenance: "profile:1", contentHash: "hash" },
      experiences: [{ sourceExperienceId: "exp-1", roleTitle: "Engineer", company: "Acme", period: "2024 - Present", location: "Berlin", bullets: [{ bulletId: "bullet-1", approvedText: "Built reliable systems.", sourceExperienceId: "exp-1", provenanceId: "prov-1", contentHash: "bullet-hash" }], contentHash: "experience-hash" }],
      education: [{ institution: "Example University", degree: "BSc", period: "2018 - 2021", contentHash: "education-hash" }],
      skills: [{ value: "TypeScript", contentHash: "skill-hash" }],
      languages: [{ value: "English", contentHash: "language-hash" }],
      standardAnswers: [{ fieldIntent: "question.exact.safe", label: "Why this role?", proposedValue: "Reliable systems", source: "scoped_preference", sensitivity: "standard", scope: "global", confidence: 1, requiresReview: false, reasons: [] }],
    };
    expect(isApplicationPackagePayload(structured)).toBe(true);
    const firstExperience = structured.experiences[0]!;
    const firstBullet = firstExperience.bullets[0]!;
    expect(isApplicationPackagePayload({
      ...structured,
      experiences: [{ ...firstExperience, bullets: [{ ...firstBullet, approvedText: 7 }] }],
    })).toBe(false);
  });

  it("validates public connection state without permitting legal confirmation to be disabled", () => {
    const connection = {
      status: "connected",
      session: {
        sessionId: "session_123",
        userId: "user_123",
        expiresAt: "2026-07-17T12:15:00.000Z",
      },
      preferences: {
        schemaVersion: 1,
        permitSensitiveAutofill: false,
        permitDemographicAutofill: false,
        requireLegalAnswerConfirmation: true,
        revision: 1,
        updatedAt: "2026-07-17T12:00:00.000Z",
      },
    };
    expect(isExtensionConnectionState(connection)).toBe(true);
    expect(isPanelResponse({ ok: true, connection })).toBe(true);
    expect(
      isExtensionConnectionState({
        ...connection,
        preferences: { ...connection.preferences, requireLegalAnswerConfirmation: false },
      }),
    ).toBe(false);
    expect(
      isExtensionConnectionState({ ...connection, session: null }),
    ).toBe(false);
  });

  it("requires a typed non-empty fixture value", () => {
    expect(
      isContentRequest({
        type: "CONTENT_RUN_GREENHOUSE_FIXTURE_PROOF",
        proposedEmail: "candidate@example.com",
      }),
    ).toBe(true);
    expect(
      isContentRequest({ type: "CONTENT_RUN_GREENHOUSE_FIXTURE_PROOF", proposedEmail: "" }),
    ).toBe(false);
    expect(isContentRequest({ type: "SUBMIT_APPLICATION" })).toBe(false);
  });

  it("bounds selected document uploads and privacy-safe upload telemetry", () => {
    const upload = {
      type: "CONTENT_UPLOAD_SELECTED_DOCUMENT",
      ats: "lever",
      packageId: "aapkg_1",
      documentId: "cv_v7",
      documentVersion: 7,
      documentKind: "cv",
      fileName: "Candidate.pdf",
      mimeType: "application/pdf",
      base64Bytes: "JVBERg==",
    };
    expect(isContentRequest(upload)).toBe(true);
    expect(isContentRequest({ ...upload, mimeType: "application/msword" })).toBe(false);
    expect(isContentRequest({ ...upload, base64Bytes: "" })).toBe(false);
    expect(isContentRequest({
      ...upload,
      documentKind: "cover_letter",
      fileName: "Cover letter.docx",
      mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    })).toBe(true);
    const telemetry = {
      schemaVersion: 1,
      adapter: "lever",
      adapterVersion: "0.3.0",
      lifecycleStage: "upload",
      aggregateOutcome: "success",
      errorCategory: "none",
    } as const;
    const result = {
      documentId: "cv_v7",
      documentVersion: 7,
      documentKind: "cv",
      fileName: "Candidate.pdf",
      status: "uploaded",
      reasons: ["Portal retained the file."],
      telemetry,
    };
    expect(isDocumentUploadMessage(result)).toBe(true);
    expect(isPanelResponse({ ok: true, documentUpload: result })).toBe(true);
    expect(isDocumentUploadMessage({ ...result, status: "submitted" })).toBe(false);
    expect(isAdapterHealthTelemetry(telemetry)).toBe(true);
    for (const forbidden of ["bytes", "url", "token", "fileName", "answer", "rawMarkup"]) {
      expect(isAdapterHealthTelemetry({ ...telemetry, [forbidden]: "secret" })).toBe(false);
    }
  });

  it("accepts only the exact local fixture URL", () => {
    expect(
      isExactGreenhouseFixtureUrl(
        "http://127.0.0.1:4174/greenhouse-application.html",
      ),
    ).toBe(true);
    expect(
      isExactGreenhouseFixtureUrl("http://localhost:4174/greenhouse-application.html"),
    ).toBe(true);
    expect(
      isExactGreenhouseFixtureUrl(
        "http://127.0.0.1:4174/greenhouse-application.html?forged=true",
      ),
    ).toBe(false);
    expect(
      isExactGreenhouseFixtureUrl(
        "http://127.0.0.1:4174/greenhouse-application.html.evil",
      ),
    ).toBe(false);
    expect(
      isExactGreenhouseFixtureUrl(
        "http://127.0.0.1.evil.example:4174/greenhouse-application.html",
      ),
    ).toBe(false);
  });

  it("validates inspection, execution, tab-state, and panel response payloads", () => {
    const inspection = {
      ats: "greenhouse",
      fixtureAvailable: true,
      fieldCount: 7,
      manualReasons: ["captcha"],
    };
    const proof = {
      ...inspection,
      execution: {
        fieldLabel: "Email address",
        status: "filled",
        acceptedValue: "candidate@example.com",
        reasons: ["read back"],
      },
    };
    const state = {
      tabId: 42,
      url: "http://127.0.0.1:4174/greenhouse-application.html",
      ats: "greenhouse",
      status: "fixture_verified",
      fixtureAvailable: true,
      fieldCount: 7,
      manualReasons: ["captcha"],
      execution: proof.execution,
      updatedAt: "2026-07-17T12:00:00.000Z",
    };

    expect(isFixtureInspectionMessage(inspection)).toBe(true);
    expect(isFixtureProofMessage(proof)).toBe(true);
    expect(isAssistedApplyTabState(state)).toBe(true);
    expect(isPanelResponse({ ok: true, state })).toBe(true);
    expect(isFixtureInspectionMessage({ ...inspection, fieldCount: "7" })).toBe(false);
    expect(isFixtureProofMessage({ ...proof, execution: { status: "filled" } })).toBe(false);
    expect(isAssistedApplyTabState({ ...state, status: "submitted" })).toBe(false);
    expect(isPanelResponse({ ok: true, state: { ...state, tabId: "42" } })).toBe(false);
  });
});
