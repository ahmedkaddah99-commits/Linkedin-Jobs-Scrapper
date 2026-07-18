import {
  isApplicationPackagePayload,
  isAssistedApplyTabState,
  type ApplicationPackagePayload,
  type AssistedApplyTabState,
} from "@runr/extension-messages";
import { browser } from "wxt/browser";

function storageKey(tabId: number): string {
  return `assisted-apply-tab:${tabId}`;
}

function packageStorageKey(tabId: number): string {
  return `assisted-apply-package:${tabId}`;
}

export async function readTabPackage(tabId: number): Promise<ApplicationPackagePayload | null> {
  const key = packageStorageKey(tabId);
  const result = await browser.storage.session.get(key);
  return isApplicationPackagePayload(result[key]) ? result[key] : null;
}

export async function writeTabPackage(tabId: number, value: ApplicationPackagePayload): Promise<void> {
  await browser.storage.session.set({ [packageStorageKey(tabId)]: value });
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
  await browser.storage.session.remove([storageKey(tabId), packageStorageKey(tabId)]);
}
