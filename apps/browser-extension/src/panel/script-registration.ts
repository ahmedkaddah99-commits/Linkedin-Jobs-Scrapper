import { browser } from "wxt/browser";

export const ASSISTANT_PANEL_SCRIPT_ID = "runr-assistant-panel";
export const ASSISTANT_PANEL_SCRIPT_FILE = "/assistant-panel.js";

/**
 * Origins Runr holds for its own first-party traffic. The assistant panel must
 * never be injected into these — they are the Runr API and the LinkedIn
 * connection sync, not application portals.
 */
const NON_PORTAL_ORIGIN_PATTERNS: ReadonlyArray<RegExp> = [
  /^https:\/\/runr-api\.onrender\.com\//u,
  /^https:\/\/(?:www\.)?linkedin\.com\//u,
  /^https:\/\/app\.userunr\.com\//u,
  /^https:\/\/runr-frontend\.onrender\.com\//u,
];

/**
 * Reduces the set of granted origins to the match patterns the assistant panel
 * should run on.
 *
 * Host access is granted broadly at install, so the broad pattern is the normal
 * case and is kept. When it is present it subsumes every narrower pattern, so
 * the result collapses to it — registering the same script twice for
 * overlapping patterns would run it twice on the same page.
 *
 * Runr's own first-party origins are still excluded when they can be, so the
 * panel never mounts on the Runr web app or the LinkedIn sync page.
 */
export function assistantPanelMatchPatterns(origins: ReadonlyArray<string>): string[] {
  const broad = origins.find((origin) => origin === "<all_urls>" || origin === "https://*/*");
  if (broad) return [broad === "<all_urls>" ? "https://*/*" : broad];

  const patterns = origins.filter((origin) => {
    if (origin === "http://*/*") return false;
    if (!/^https?:\/\//u.test(origin)) return false;
    return !NON_PORTAL_ORIGIN_PATTERNS.some((pattern) => pattern.test(origin));
  });
  return Array.from(new Set(patterns)).sort();
}

/**
 * Origins the panel must not mount on even under a broad grant. Checked in the
 * page rather than at registration time, because a broad match pattern cannot
 * express an exclusion.
 */
export function isExcludedPanelUrl(url: string): boolean {
  return NON_PORTAL_ORIGIN_PATTERNS.some((pattern) => pattern.test(url));
}

/**
 * Brings the registered content scripts in line with the origins the user has
 * actually granted. Called at startup and whenever permissions change, so a
 * grant takes effect on the next page load without a browser restart, and a
 * revocation stops injection immediately.
 */
export async function reconcileAssistantPanelRegistration(): Promise<string[]> {
  const granted = await browser.permissions.getAll();
  const matches = assistantPanelMatchPatterns(granted.origins ?? []);

  const registered = await browser.scripting.getRegisteredContentScripts({ ids: [ASSISTANT_PANEL_SCRIPT_ID] })
    .catch(() => []);

  if (matches.length === 0) {
    if (registered.length > 0) {
      await browser.scripting.unregisterContentScripts({ ids: [ASSISTANT_PANEL_SCRIPT_ID] }).catch(() => undefined);
    }
    return [];
  }

  const definition = {
    id: ASSISTANT_PANEL_SCRIPT_ID,
    js: [ASSISTANT_PANEL_SCRIPT_FILE],
    matches,
    runAt: "document_idle" as const,
    allFrames: false,
    persistAcrossSessions: true,
  };

  if (registered.length > 0) {
    await browser.scripting.updateContentScripts([definition]).catch(async () => {
      await browser.scripting.unregisterContentScripts({ ids: [ASSISTANT_PANEL_SCRIPT_ID] }).catch(() => undefined);
      await browser.scripting.registerContentScripts([definition]).catch(() => undefined);
    });
  } else {
    await browser.scripting.registerContentScripts([definition]).catch(() => undefined);
  }
  return matches;
}

/**
 * Runs the panel in tabs that are already open on a newly granted origin.
 *
 * `registerContentScripts` only affects future navigations, so without this a
 * user who grants access while sitting on the application page would have to
 * reload before anything happened. The script guards itself against double
 * installation, so injecting into a tab that already has it is harmless.
 */
export async function injectIntoMatchingTabs(matches: ReadonlyArray<string>): Promise<number> {
  if (matches.length === 0) return 0;
  const tabs = await browser.tabs.query({ url: [...matches] }).catch(() => []);
  let injected = 0;
  for (const tab of tabs) {
    if (tab.id == null) continue;
    const done = await browser.scripting
      .executeScript({ target: { tabId: tab.id }, files: [ASSISTANT_PANEL_SCRIPT_FILE] })
      .then(() => true)
      .catch(() => false);
    if (done) injected += 1;
  }
  return injected;
}
