import { describe, expect, it } from "vitest";
import { buildReviewPanelModel } from "../../src/review/panel-model";
import type { ApplicationPackagePayload, AssistedApplyTabState, DocumentUploadMessage } from "@runr/extension-messages";

const pkg: ApplicationPackagePayload = {
  packageId: "pkg-1", jobId: "job-1", version: 3, schemaVersion: 1,
  job: { jobId: "job-1", title: "Engineer", company: "Runr", portal: "greenhouse", location: "Berlin" },
  answers: [
    { fieldIntent: "candidate.email", label: "Email", proposedValue: "a@example.com", source: "profile_verified", sensitivity: "standard", scope: "global", confidence: 1, requiresReview: false, reasons: [] },
    { fieldIntent: "candidate.salary", label: "Salary", proposedValue: "100", source: "ai_suggestion", sensitivity: "standard", scope: "application", confidence: .95, requiresReview: true, reasons: ["Confirm"] },
    { fieldIntent: "candidate.phone", label: "Phone", proposedValue: "", source: "profile_verified", sensitivity: "personal", scope: "global", confidence: 1, requiresReview: false, reasons: [] },
    { fieldIntent: "candidate.declaration", label: "Declaration", proposedValue: "Yes", source: "profile_verified", sensitivity: "legal", scope: "application", confidence: 1, requiresReview: false, reasons: [] },
    { fieldIntent: "application.captcha", label: "CAPTCHA", proposedValue: "", source: "profile_verified", sensitivity: "standard", scope: "application", confidence: 1, requiresReview: false, reasons: [] },
    { fieldIntent: "application.terms", label: "Terms", proposedValue: "true", source: "profile_verified", sensitivity: "standard", scope: "application", confidence: 1, requiresReview: false, reasons: [] },
    { fieldIntent: "application.assessment", label: "Assessment", proposedValue: "", source: "profile_verified", sensitivity: "standard", scope: "application", confidence: 1, requiresReview: false, reasons: ["unsupported_control"] },
  ],
  documents: [
    { documentId: "cv_v1", documentVersion: 1, documentKind: "cv", mimeType: "application/pdf", fileName: "cv.pdf" },
    { documentId: "cover_v1", documentVersion: 1, documentKind: "cover_letter", mimeType: "application/pdf", fileName: "cover.pdf" },
  ],
  warnings: [],
  policy: { permitSensitiveAutofill: false, permitDemographicAutofill: false, requireLegalAnswerConfirmation: true },
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
    // Email: verified -> ready
    expect(model.rows.ready).toHaveLength(1);
    // Salary: ai_suggestion + requiresReview -> review
    expect(model.rows.review).toHaveLength(1);
    // Phone: empty -> missing
    // CAPTCHA: empty -> missing (field intent pattern doesn't override empty check)
    // Assessment: empty + unsupported_control reason -> missing (empty takes priority)
    expect(model.rows.missing).toHaveLength(3);
    // Declaration: legal sensitivity -> manual
    // Terms: has /terms/ pattern -> manual
    expect(model.rows.manual).toHaveLength(2);
    // manualControls: captcha + legal_declaration from state
    expect(model.counts).toMatchObject({ ready: 1, review: 1, missing: 3, manual: 4, documents: 2, verified: 0 });
    expect(model.manualControls).toEqual(["captcha", "legal_declaration"]);
  });

  it("marks manual section for CAPTCHA and disallowed sensitive answers by field intent", () => {
    const model = buildReviewPanelModel(pkg, state);
    const manualFieldIntents = model.rows.manual.map((row) => row.fieldIntent);
    expect(manualFieldIntents).toContain("candidate.declaration");
    expect(manualFieldIntents).toContain("application.terms");
  });

  it("marks answer with disallowed sensitivity as manual", () => {
    const answer = pkg.answers.find((a) => a.fieldIntent === "candidate.declaration")!;
    expect(answer.sensitivity).toBe("legal");
    const model = buildReviewPanelModel(pkg, state);
    const manual = model.rows.manual.find((r) => r.fieldIntent === "candidate.declaration");
    expect(manual).toBeDefined();
    expect(manual!.liveAcceptance).toBe("manual");
  });

  it("flags required empty fields with requiredAndEmpty", () => {
    const model = buildReviewPanelModel(pkg, state);
    // Phone is empty and matches /phone/ pattern
    const phone = model.rows.missing.find((r) => r.fieldIntent === "candidate.phone");
    expect(phone).toBeDefined();
    expect(phone!.requiredAndEmpty).toBe(true);
    // CAPTCHA is empty but doesn't match required patterns
    const captcha = model.rows.missing.find((r) => r.fieldIntent === "application.captcha");
    expect(captcha).toBeDefined();
    expect(captcha!.requiredAndEmpty).toBe(false);
  });

  it("sets liveAcceptance correctly per section", () => {
    const model = buildReviewPanelModel(pkg, state);
    expect(model.rows.ready[0].liveAcceptance).toBe("not_attempted");
    expect(model.rows.review[0].liveAcceptance).toBe("needs_review");
    expect(model.rows.manual[0].liveAcceptance).toBe("manual");
  });

  it("marks as accepted when a matching execution exists", () => {
    const executedState: AssistedApplyTabState = {
      ...state,
      execution: { fieldLabel: "Email", status: "filled", reasons: [], acceptedValue: "a@example.com" },
    };
    const model = buildReviewPanelModel(pkg, executedState);
    expect(model.rows.ready[0].liveAcceptance).toBe("accepted");
    expect(model.counts.verified).toBe(1);
  });

  it("tracks document upload status per document", () => {
    const upload: DocumentUploadMessage = {
      documentId: "cv_v1", documentVersion: 1, documentKind: "cv",
      fileName: "cv.pdf", status: "uploaded", reasons: [],
      telemetry: {
        schemaVersion: 1, adapter: "greenhouse", adapterVersion: "1.0.0",
        lifecycleStage: "upload", aggregateOutcome: "accepted",
        errorCategory: "none", documentRole: "cv",
      },
    };
    const model = buildReviewPanelModel(pkg, state, upload);
    expect(model.documents).toHaveLength(2);
    const cv = model.documents.find((d) => d.documentId === "cv_v1");
    expect(cv).toBeDefined();
    expect(cv!.uploadStatus).toBe("uploaded");
    const cover = model.documents.find((d) => d.documentId === "cover_v1");
    expect(cover).toBeDefined();
    expect(cover!.uploadStatus).toBe("idle");
  });

  it("disables review when package and live portal do not match", () => {
    expect(buildReviewPanelModel(pkg, { ...state, ats: "lever" }).enabled).toBe(false);
    expect(buildReviewPanelModel(null, state).enabled).toBe(false);
  });

  it("disables review for unsupported or error status", () => {
    expect(buildReviewPanelModel(pkg, { ...state, status: "unsupported" }).enabled).toBe(false);
    expect(buildReviewPanelModel(pkg, { ...state, status: "error" }).enabled).toBe(false);
  });

  it("returns empty model for null package", () => {
    const model = buildReviewPanelModel(null, state);
    expect(model.rows.ready).toHaveLength(0);
    expect(model.rows.review).toHaveLength(0);
    expect(model.rows.missing).toHaveLength(0);
    expect(model.rows.manual).toHaveLength(0);
    expect(model.documents).toHaveLength(0);
    expect(model.counts.documents).toBe(0);
    expect(model.enabled).toBe(false);
  });
});
