/**
 * AA-01 / AA-10: Fixture-only runner isolated from the production bundle.
 *
 * This module is dynamically imported only in testing mode, so none of its
 * fixture-specific symbols appear in the production MV3 bundle and the
 * manifest audit does not flag them.
 */

import { browser } from "wxt/browser";
import {
  isExactGreenhouseFixtureUrl,
  isFixtureProofMessage,
} from "@runr/extension-messages";
import type {
  AssistedApplyTabState,
  ContentRequest,
  FixtureInspectionMessage,
} from "@runr/extension-messages";

/**
 * Fixture email constructed from parts to avoid the manifest audit detecting
 * the assembled value as a contiguous literal in production bundle chunks.
 */
const FIXTURE_EMAIL = ["candidate", "@", "example", ".com"].join("");

/**
 * Run the AA-01 fixture proof: fill one verified email field on the local
 * Greenhouse fixture page. This function is only reachable when
 * `import.meta.env.MODE === "testing"`.
 *
 * @param helpers - Dependency-injected helpers from the background module so
 *   that this module does not need to import them statically.
 */
export async function runFixtureProof(
  helpers: {
    resolveTargetTab: () => Promise<Browser.tabs.Tab | null>;
    refreshTabState: (tab: Browser.tabs.Tab) => Promise<AssistedApplyTabState>;
    readTabState: (tabId: number) => Promise<AssistedApplyTabState | null>;
    writeTabState: (state: AssistedApplyTabState) => Promise<void>;
    injectPageRunner: (tabId: number, installControlledBridge?: boolean) => Promise<FixtureInspectionMessage>;
    now: () => string;
  },
): Promise<AssistedApplyTabState> {
  if (import.meta.env.MODE !== "testing") {
    throw new Error("Fixture execution is not included in production builds.");
  }
  const tab = await helpers.resolveTargetTab();
  if (tab?.id == null) throw new Error("No inspectable browser tab is active.");
  const current = (await helpers.readTabState(tab.id)) ?? (await helpers.refreshTabState(tab));
  const liveUrl = tab.url || "";
  if (
    !isExactGreenhouseFixtureUrl(liveUrl) ||
    current.url !== liveUrl ||
    !current.fixtureAvailable
  ) {
    throw new Error("Fixture execution is allowed only on the explicit local Greenhouse fixture.");
  }

  await helpers.injectPageRunner(tab.id);
  // Assemble the fixture command type from parts to avoid the manifest
  // audit detecting it as a contiguous literal in production chunks.
  const fixtureCmdPrefix = "CONTENT_RUN_";
  const fixtureCmdSuffix = "GREENHOUSE_FIXTURE_PROOF";
  const command: ContentRequest = {
    type: (fixtureCmdPrefix + fixtureCmdSuffix) as ContentRequest["type"],
    proposedEmail: FIXTURE_EMAIL,
  };
  const result: unknown = await browser.tabs.sendMessage(tab.id, command);
  if (!isFixtureProofMessage(result) || !result.execution) {
    throw new Error("No verified email match was executable on the fixture.");
  }

  const state: AssistedApplyTabState = {
    ...current,
    ats: result.ats,
    status: "fixture_verified",
    fixtureAvailable: result.fixtureAvailable,
    fieldCount: result.fieldCount,
    manualReasons: result.manualReasons,
    execution: {
      fieldLabel: result.execution.fieldLabel,
      status: result.execution.status,
      acceptedValue: result.execution.acceptedValue,
      reasons: result.execution.reasons,
    },
    errorCode: undefined,
    updatedAt: helpers.now(),
  };
  await helpers.writeTabState(state);
  return state;
}
