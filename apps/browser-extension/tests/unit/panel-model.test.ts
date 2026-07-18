import { describe, expect, it } from "vitest";
import { buildReviewPanelModel } from "../../src/review/panel-model";
import type { ApplicationPackagePayload, AssistedApplyTabState } from "@runr/extension-messages";

const pkg: ApplicationPackagePayload = {
  packageId: "pkg-1", jobId: "job-1", version: 3, schemaVersion: 1,
  job: { jobId: "job-1", title: "Engineer", company: "Runr", portal: "greenhouse", location: "Berlin" },
  answers: [
    { fieldIntent: "candidate.email", label: "Email", proposedValue: "a@example.com", source: "profile_verified", sensitivity: "standard", scope: "global", confidence: 1, requiresReview: false, reasons: [] },
    { fieldIntent: "candidate.salary", label: "Salary", proposedValue: "100", source: "ai_suggestion", sensitivity: "standard", scope: "application", confidence: .95, requiresReview: true, reasons: ["Confirm"] },
    { fieldIntent: "candidate.phone", label: "Phone", proposedValue: "", source: "profile_verified", sensitivity: "personal", scope: "global", confidence: 1, requiresReview: false, reasons: [] },
    { fieldIntent: "candidate.declaration", label: "Declaration", proposedValue: "Yes", source: "profile_verified", sensitivity: "legal", scope: "application", confidence: 1, requiresReview: false, reasons: [] },
  ],
  documents: [{ documentId: "cv_v1", documentVersion: 1, documentKind: "cv", mimeType: "application/pdf", fileName: "cv.pdf" }],
  warnings: [], policy: { permitSensitiveAutofill: false, permitDemographicAutofill: false, requireLegalAnswerConfirmation: true },
};

const state: AssistedApplyTabState = {
  tabId: 1, url: "https://boards.greenhouse.io/runr/jobs/1", ats: "greenhouse",
  status: "recognized", fixtureAvailable: false, fieldCount: 5,
  manualReasons: ["captcha", "legal_declaration"], execution: null,
  updatedAt: "2026-07-18T00:00:00Z",
};

describe("review panel model", () => {
  it("classifies package evidence conservatively and counts manual live controls", () => {
    const model = buildReviewPanelModel(pkg, state);
    expect(model.enabled).toBe(true);
    expect(model.rows.ready).toHaveLength(1);
    expect(model.rows.review).toHaveLength(1);
    expect(model.rows.missing).toHaveLength(1);
    expect(model.rows.manual).toHaveLength(1);
    expect(model.counts).toMatchObject({ ready: 1, review: 1, missing: 1, manual: 3, documents: 1 });
  });

  it("disables review when package and live portal do not match", () => {
    expect(buildReviewPanelModel(pkg, { ...state, ats: "lever" }).enabled).toBe(false);
    expect(buildReviewPanelModel(null, state).enabled).toBe(false);
  });
});
