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
} from "@runr/extension-messages";

describe("extension message boundaries", () => {
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

  it("bounds document upload commands and results to fixed-version PDF metadata", () => {
    const upload = {
      type: "CONTENT_UPLOAD_GREENHOUSE_CV",
      packageId: "aapkg_1",
      documentId: "cv_v7",
      documentVersion: 7,
      fileName: "Candidate.pdf",
      mimeType: "application/pdf",
      base64Bytes: "JVBERg==",
    };
    expect(isContentRequest(upload)).toBe(true);
    expect(isContentRequest({ ...upload, mimeType: "application/msword" })).toBe(false);
    expect(isContentRequest({ ...upload, base64Bytes: "" })).toBe(false);
    const result = {
      documentId: "cv_v7",
      documentVersion: 7,
      fileName: "Candidate.pdf",
      status: "uploaded",
      reasons: ["Portal retained the file."],
    };
    expect(isDocumentUploadMessage(result)).toBe(true);
    expect(isPanelResponse({ ok: true, documentUpload: result })).toBe(true);
    expect(isDocumentUploadMessage({ ...result, status: "submitted" })).toBe(false);
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
