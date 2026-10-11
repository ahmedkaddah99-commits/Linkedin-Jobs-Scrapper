// CP-040R: Tests for evidence review flow helpers.
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { computeCanonicalReadiness, REVIEW_ACTION } from "./careerEvidenceFlow.js";

describe("REVIEW_ACTION constants", () => {
  it("exports Confirm, Reject, Edit actions", () => {
    assert.equal(REVIEW_ACTION.CONFIRM, "confirm");
    assert.equal(REVIEW_ACTION.REJECT, "reject");
    assert.equal(REVIEW_ACTION.EDIT, "edit");
  });
});

describe("computeCanonicalReadiness", () => {
  it("returns zero readiness for empty evidence", () => {
    const result = computeCanonicalReadiness([]);
    assert.equal(result.total, 0);
    assert.equal(result.readinessRatio, 0);
    assert.equal(result.isReady, false);
    assert.equal(result.legacyCountersExcluded, true);
  });

  it("returns ready when all items confirmed and mapped", () => {
    const items = [
      {
        status: "confirmed",
        experience_mapping: { experience_id: "exp_1" },
      },
      {
        status: "confirmed",
        experience_mapping: { experience_id: "exp_2" },
      },
    ];
    const result = computeCanonicalReadiness(items);
    assert.equal(result.confirmed, 2);
    assert.equal(result.mapped, 2);
    assert.equal(result.mappedReady, 2);
    assert.equal(result.readinessRatio, 1.0);
    assert.equal(result.isReady, true);
  });

  it("returns not ready when items need review", () => {
    const items = [
      { status: "needs_review", experience_mapping: {} },
    ];
    const result = computeCanonicalReadiness(items);
    assert.equal(result.needsReview, 1);
    assert.equal(result.isReady, false);
  });

  it("calculates mixed state correctly", () => {
    const items = [
      {
        status: "confirmed",
        experience_mapping: { experience_id: "exp_1" },
      },
      { status: "rejected", experience_mapping: {} },
      { status: "needs_review", experience_mapping: {} },
    ];
    const result = computeCanonicalReadiness(items);
    assert.equal(result.total, 3);
    assert.equal(result.confirmed, 1);
    assert.equal(result.rejected, 1);
    assert.equal(result.needsReview, 1);
    assert.equal(result.mappedReady, 1);
    // actionable = 2 (confirmed + needs_review), mappedReady = 1
    assert.equal(result.readinessRatio, 0.5);
    assert.equal(result.isReady, false);
  });

  it("counts only mapped confirmed items as ready", () => {
    const items = [
      {
        status: "confirmed",
        experience_mapping: { experience_id: "exp_1" },
      },
      {
        status: "confirmed",
        experience_mapping: {},
      },
    ];
    const result = computeCanonicalReadiness(items);
    assert.equal(result.confirmed, 2);
    assert.equal(result.mapped, 1);
    assert.equal(result.mappedReady, 1);
    // 1/2 = 0.5, not >= 0.9
    assert.equal(result.isReady, false);
  });

  it("handles merged items correctly", () => {
    const items = [
      { status: "merged", experience_mapping: {} },
      {
        status: "confirmed",
        experience_mapping: { experience_id: "exp_1" },
      },
    ];
    const result = computeCanonicalReadiness(items);
    assert.equal(result.merged, 1);
    // actionable = total - merged - rejected = 2 - 1 - 0 = 1
    // mappedReady = 1, readinessRatio = 1.0
    assert.equal(result.readinessRatio, 1.0);
    assert.equal(result.isReady, true);
  });

  it("marks legacyCountersExcluded true", () => {
    const result = computeCanonicalReadiness([]);
    assert.equal(result.legacyCountersExcluded, true);
    assert.equal(result.computedFrom, "canonical_evidence");
  });
});
