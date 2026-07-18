import { beforeEach, describe, expect, it } from "vitest";
import type { AssistedApplyTabState } from "@runr/extension-messages";
import { fakeBrowser } from "wxt/testing/fake-browser";
import { readTabState, removeTabState, writeTabState } from "../../src/state/tab-state";

const state: AssistedApplyTabState = {
  tabId: 42,
  url: "https://boards.greenhouse.io/acme/jobs/1",
  ats: "greenhouse",
  status: "fixture_verified",
  fixtureAvailable: true,
  fieldCount: 3,
  manualReasons: ["final_submission"],
  execution: {
    fieldLabel: "Email address",
    status: "filled",
    acceptedValue: "candidate@example.com",
    reasons: ["read back"],
  },
  updatedAt: "2026-07-17T12:00:00.000Z",
};

describe("reconstructable MV3 tab state", () => {
  beforeEach(() => fakeBrowser.reset());

  it("reads state from storage.session without relying on module memory", async () => {
    await writeTabState(state);
    const raw = await fakeBrowser.storage.session.get("assisted-apply-tab:42");

    expect(raw["assisted-apply-tab:42"]).toEqual(state);
    expect(await readTabState(42)).toEqual(state);
  });

  it("removes state when a tab closes", async () => {
    await writeTabState(state);
    await removeTabState(42);
    expect(await readTabState(42)).toBeNull();
  });

  it("rejects malformed session data instead of trusting a cast", async () => {
    await fakeBrowser.storage.session.set({
      "assisted-apply-tab:42": { ...state, status: "submitted" },
    });
    expect(await readTabState(42)).toBeNull();
  });
});
