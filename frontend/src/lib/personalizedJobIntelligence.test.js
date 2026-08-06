import assert from "node:assert/strict";
import test from "node:test";
import { MATCH_VERSION_LABELS, buildEvidenceReview, improveResumeEntitlement, selectMatchScore } from "./personalizedJobIntelligence.js";

test("match selector exposes both named deterministic versions", () => {
  assert.equal(MATCH_VERSION_LABELS.v1, "v1 · ATS-style");
  assert.equal(MATCH_VERSION_LABELS.v2, "v2 · Semantic/evidence-aware");
  assert.equal(selectMatchScore({ v1: { score: 41 }, v2: { score: 73 } }, "v1").score, 41);
  assert.equal(selectMatchScore({ v1: { score: 41 }, v2: { score: 73 } }, "v2").score, 73);
});

test("Free evidence review includes every required review category", () => {
  const review = buildEvidenceReview({ v2: { matched_keywords: ["SQL"], missing_keywords: ["German"], matched_requirements: ["Reporting"], unproven_requirements: ["Degree"], apparent_non_matches: ["Visa"], matched_evidence: [{ requirement: "Reporting", evidence: "Built reports" }] }, difference: { score_delta: 8, summary: "Semantic support" } });
  assert.deepEqual(Object.keys(review), ["matched_keywords", "missing_keywords", "matched_requirements", "unproven_requirements", "apparent_non_matches", "matched_evidence", "v1_v2_difference"]);
  assert.equal(review.v1_v2_difference.score_delta, 8);
});

test("rewriting is unavailable to Free and available to Pro", () => {
  assert.deepEqual(improveResumeEntitlement({ improveResume: { review_available: true, rewriting_available: false } }), { reviewAvailable: true, rewriteAvailable: false, tailoredDocumentsAvailable: false });
  assert.equal(improveResumeEntitlement({ improveResume: { rewriting_available: true, tailored_documents_available: true } }).rewriteAvailable, true);
});
