import { describe, expect, it } from "vitest";
import {
  canRetryPreparation,
  hasActivePreparation,
  PREPARATION_MAX_ATTEMPTS,
  type PreparationLocalRecord,
} from "../../src/preparation/local-session";

const record: PreparationLocalRecord = {
  preparationId: "prep_222", packageId: "pkg_222", packageVersion: 1, ats: "greenhouse",
  applicationUrl: "https://boards.greenhouse.io/acme/jobs/222", tabId: 222,
  status: "closed", createdAt: "2026-08-01T10:00:00.000Z", updatedAt: "2026-08-01T10:00:00.000Z",
  attempt: 1, completedCount: 2, totalCount: 4,
};

describe("AA-222 explicit retry policy", () => {
  it("permits retry only from interrupted attention states and below the bounded limit", () => {
    expect(PREPARATION_MAX_ATTEMPTS).toBe(3);
    expect(hasActivePreparation({ ...record, status: "ready_for_review" })).toBe(true);
    expect(canRetryPreparation(record)).toBe(true);
    expect(canRetryPreparation({ ...record, status: "auth_lost" })).toBe(true);
    expect(canRetryPreparation({ ...record, status: "retry_required" })).toBe(true);
    expect(canRetryPreparation({ ...record, attempt: PREPARATION_MAX_ATTEMPTS })).toBe(false);
  });

  it("fails closed for browser-state loss and does not imply tab recreation", () => {
    expect(canRetryPreparation(null)).toBe(false);
    expect(canRetryPreparation({ ...record, status: "retry_required", tabId: -1 })).toBe(true);
  });
});
