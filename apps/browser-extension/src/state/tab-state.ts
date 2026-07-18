import {
  isAssistedApplyTabState,
  type AssistedApplyTabState,
} from "@runr/extension-messages";
import { browser } from "wxt/browser";

function storageKey(tabId: number): string {
  return `assisted-apply-tab:${tabId}`;
}

export async function readTabState(tabId: number): Promise<AssistedApplyTabState | null> {
  const key = storageKey(tabId);
  const result = await browser.storage.session.get(key);
  return isAssistedApplyTabState(result[key]) ? result[key] : null;
}

export async function writeTabState(state: AssistedApplyTabState): Promise<void> {
  await browser.storage.session.set({ [storageKey(state.tabId)]: state });
}

export async function removeTabState(tabId: number): Promise<void> {
  await browser.storage.session.remove(storageKey(tabId));
}
