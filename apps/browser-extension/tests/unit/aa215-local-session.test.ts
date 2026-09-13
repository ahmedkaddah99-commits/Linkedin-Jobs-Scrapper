import { beforeEach, describe, expect, it } from "vitest";
import { fakeBrowser } from "wxt/testing/fake-browser";
import {
  canActivateExactPreparationTab,
  classifyPreparationTabChange,
  hasActivePreparation,
  isOwnedPreparationUrl,
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

  it("keeps ownership across the same ATS application flow but not another role", () => {
    const lever = { ...record, ats: "lever" as const, applicationUrl: "https://jobs.lever.co/acme/job-215/apply" };
    expect(isOwnedPreparationUrl(lever, "https://jobs.lever.co/acme/job-215/application/step-2")).toBe(true);
    expect(classifyPreparationTabChange(lever, { url: "https://jobs.lever.co/acme/job-215/application/step-2" }, undefined)).toBeNull();
    expect(isOwnedPreparationUrl(lever, "https://jobs.lever.co/acme/another-job/apply")).toBe(false);
    expect(isOwnedPreparationUrl(record, "https://boards.greenhouse.io/acme/jobs/215/review")).toBe(true);
    expect(isOwnedPreparationUrl(record, "https://boards.greenhouse.io/acme/jobs/999")).toBe(false);
  });

  it("keeps exact ownership for controlled non-HTTPS fixture URLs only", () => {
    const fixture = {
      ...record,
      ats: "lever" as const,
      applicationUrl: "http://127.0.0.1:4174/lever-application.html",
    };
    expect(isOwnedPreparationUrl(fixture, fixture.applicationUrl)).toBe(true);
    expect(isOwnedPreparationUrl(fixture, `${fixture.applicationUrl}?step=2`)).toBe(false);
    expect(isOwnedPreparationUrl(fixture, "http://127.0.0.1:4174/greenhouse-application.html")).toBe(false);
  });

  it("activates only the exact owned, matching, reviewable tab", () => {
    expect(canActivateExactPreparationTab({ ...record, status: "ready_for_review" }, { id: 215, url: record.applicationUrl })).toBe(true);
    expect(canActivateExactPreparationTab({ ...record, status: "ready_for_review" }, { id: 215, url: `${record.applicationUrl}/review` })).toBe(true);
    expect(canActivateExactPreparationTab({ ...record, status: "ready_for_review" }, { id: 216, url: record.applicationUrl })).toBe(false);
    expect(canActivateExactPreparationTab({ ...record, status: "ready_for_review" }, { id: 215, url: "https://evil.example" })).toBe(false);
  });
});
