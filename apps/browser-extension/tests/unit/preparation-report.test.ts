import { describe, expect, it } from "vitest";
import { preparationProgressResult } from "../../src/preparation/report";

describe("durable preparation progress reports", () => {
  it("contains only backend-approved sanitized result keys", () => {
    expect(preparationProgressResult("ready_for_review", 3, 4)).toEqual({
      status: "ready_for_review",
      completed: 3,
      total: 4,
    });
    expect(preparationProgressResult("ready_for_review", 3, 4)).not.toHaveProperty("reviewId");
  });

  it("bounds malformed aggregate counts", () => {
    expect(preparationProgressResult("progress", 8.9, 3.7)).toEqual({
      status: "progress",
      completed: 3,
      total: 3,
    });
  });
});
