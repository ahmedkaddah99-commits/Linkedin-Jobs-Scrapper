import {
  isApplicationPackagePayload,
  isAssistedApplyTabState,
  isPendingApplicationConfirmation,
  type ApplicationPackagePayload,
  type AssistedApplyTabState,
  type PendingApplicationConfirmation,
} from "@runr/extension-messages";
import { browser } from "wxt/browser";

function storageKey(tabId: number): string {
  return `assisted-apply-tab:${tabId}`;
}

function packageStorageKey(tabId: number): string {
  return `assisted-apply-package:${tabId}`;
}

function confirmationStorageKey(tabId: number): string {
  return `assisted-apply-confirmation:${tabId}`;
}

function uploadStorageKey(tabId: number): string {
  return `assisted-apply-uploads:${tabId}`;
}

export async function readUploadedDocuments(
  tabId: number,
): Promise<Array<{ documentId: string; documentVersion: number }>> {
  const key = uploadStorageKey(tabId);
  const result = await browser.storage.session.get(key);
  return Array.isArray(result[key]) ? result[key].filter((value: unknown) =>
    Boolean(value) && typeof value === "object" &&
    typeof (value as { documentId?: unknown }).documentId === "string" &&
    Number.isInteger((value as { documentVersion?: unknown }).documentVersion)) : [];
}

export async function recordUploadedDocument(
  tabId: number,
  documentId: string,
  documentVersion: number,
): Promise<void> {
  const current = await readUploadedDocuments(tabId);
  const next = current.filter((item) => item.documentId !== documentId);
  next.push({ documentId, documentVersion });
  await browser.storage.session.set({ [uploadStorageKey(tabId)]: next });
}

export async function readPendingConfirmation(tabId: number): Promise<PendingApplicationConfirmation | null> {
  const key = confirmationStorageKey(tabId);
  const result = await browser.storage.session.get(key);
  return isPendingApplicationConfirmation(result[key]) ? result[key] : null;
}

export async function writePendingConfirmation(
  tabId: number,
  value: PendingApplicationConfirmation,
): Promise<void> {
  await browser.storage.session.set({ [confirmationStorageKey(tabId)]: value });
}

export async function clearPendingConfirmation(tabId: number): Promise<void> {
  await browser.storage.session.remove(confirmationStorageKey(tabId));
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
  await browser.storage.session.remove([
    storageKey(tabId), packageStorageKey(tabId), confirmationStorageKey(tabId), uploadStorageKey(tabId),
  ]);
}
