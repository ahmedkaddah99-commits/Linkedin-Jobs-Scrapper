import { beforeEach, describe, expect, it } from "vitest";
import { fakeBrowser } from "wxt/testing/fake-browser";
import {
  canActivateExactPreparationTab,
  classifyPreparationTabChange,
  hasActivePreparation,
  readPreparationLocalRecord,
  writePreparationLocalRecord,
  type PreparationLocalRecord,
} from "../../src/preparation/local-session";

const record: PreparationLocalRecord = {
  preparationId: "prep_215", packageId: "pkg_215", packageVersion: 1, ats: "greenhouse",
  applicationUrl: "https://boards.greenhouse.io/acme/jobs/215", tabId: 215, windowId: 7,
  status: "waiting_ready", createdAt: "2026-08-01T10:00:00.000Z", updatedAt: "2026-08-01T10:00:00.000Z",
  attempt: 1, completedCount: 0, totalCount: 3,
};

describe("AA-215 local preparation ownership", () => {
  beforeEach(() => fakeBrowser.reset());

  it("reconstructs the session-to-tab mapping after module memory is gone", async () => {
    await writePreparationLocalRecord(record);
    expect(await readPreparationLocalRecord()).toEqual(record);
    expect(hasActivePreparation(await readPreparationLocalRecord())).toBe(true);
  });

  it("does not treat permission_required or auth_lost as an owned active tab", () => {
    expect(hasActivePreparation({ ...record, status: "permission_required", tabId: -1 })).toBe(false);
    expect(hasActivePreparation({ ...record, status: "auth_lost" })).toBe(false);
  });

  it("fails closed on state loss and does not imply silent recreation", async () => {
    expect(await readPreparationLocalRecord()).toBeNull();
    expect(canActivateExactPreparationTab(null, { id: 215, url: record.applicationUrl })).toBe(false);
  });

  it("classifies discard, close-equivalent navigation, and preserved navigation deterministically", () => {
    expect(classifyPreparationTabChange(record, { discarded: true }, record.applicationUrl)).toBe("discarded");
    expect(classifyPreparationTabChange(record, { url: "https://evil.example/app" }, record.applicationUrl)).toBe("navigation_mismatch");
    expect(classifyPreparationTabChange(record, {}, `${record.applicationUrl}#review`)).toBeNull();
  });

  it("activates only the exact owned, matching, reviewable tab", () => {
    expect(canActivateExactPreparationTab({ ...record, status: "ready_for_review" }, { id: 215, url: record.applicationUrl })).toBe(true);
    expect(canActivateExactPreparationTab({ ...record, status: "ready_for_review" }, { id: 216, url: record.applicationUrl })).toBe(false);
    expect(canActivateExactPreparationTab({ ...record, status: "ready_for_review" }, { id: 215, url: "https://evil.example" })).toBe(false);
  });
});
