import {
  inspectGreenhouseFixture,
  runGreenhouseFixtureProof,
} from "@runr/ats-core";
import {
  isContentRequest,
  isExactGreenhouseFixtureUrl,
} from "@runr/extension-messages";
import { browser } from "wxt/browser";
import { defineUnlistedScript } from "wxt/utils/define-unlisted-script";

declare global {
  interface Window {
    __runrAssistedApplyFixtureBridgeInstalled?: boolean;
  }
}

export default defineUnlistedScript(async () => {
  const testingFixturePage =
    import.meta.env.MODE === "testing" &&
    isExactGreenhouseFixtureUrl(window.location.href);
  if (testingFixturePage && !window.__runrAssistedApplyFixtureBridgeInstalled) {
    browser.runtime.onMessage.addListener((message: unknown) => {
      if (!isContentRequest(message)) return undefined;
      if (!isExactGreenhouseFixtureUrl(window.location.href)) {
        return {
          ats: null,
          fixtureAvailable: false,
          fieldCount: 0,
          manualReasons: [],
          execution: null,
        };
      }
      return runGreenhouseFixtureProof(document, window.location.href, message.proposedEmail);
    });
    window.__runrAssistedApplyFixtureBridgeInstalled = true;
  }

  const inspection = await inspectGreenhouseFixture(document, window.location.href);
  return {
    ...inspection,
    fixtureAvailable: testingFixturePage && inspection.fixtureAvailable,
  };
});
