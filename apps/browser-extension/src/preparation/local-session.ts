import { browser } from "wxt/browser";

export const PREPARATION_LOCAL_RECORD_KEY = "assisted-apply-preparation:local:v1";

export type PreparationLocalStatus =
  | "starting"
  | "waiting_ready"
  | "preparing"
  | "ready_for_review"
  | "review_activated"
  | "permission_required"
  | "cancelled"
  | "closed"
  | "discarded"
  | "navigation_mismatch"
  | "auth_lost"
  | "retry_required"
  | "failed";

export type PreparationLocalRecord = {
  preparationId: string;
  packageId: string;
  packageVersion: number;
  ats: "greenhouse" | "lever";
  applicationUrl: string;
  tabId: number;
  windowId?: number;
  status: PreparationLocalStatus;
  createdAt: string;
  updatedAt: string;
  attempt: number;
  completedCount: number;
  totalCount: number;
  lastMessageId?: string;
};

const activeStatuses = new Set<PreparationLocalStatus>([
  "starting", "waiting_ready", "preparing", "ready_for_review", "review_activated",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export function isPreparationLocalRecord(value: unknown): value is PreparationLocalRecord {
  if (!isRecord(value) || typeof value.preparationId !== "string" ||
      typeof value.packageId !== "string" || !Number.isInteger(value.packageVersion) ||
      (value.ats !== "greenhouse" && value.ats !== "lever") ||
      typeof value.applicationUrl !== "string" || !Number.isInteger(value.tabId) ||
      !Number.isInteger(value.attempt) || !Number.isInteger(value.completedCount) ||
      !Number.isInteger(value.totalCount) || typeof value.status !== "string" ||
      !activeStatuses.has(value.status as PreparationLocalStatus) &&
      !["cancelled", "closed", "discarded", "navigation_mismatch", "retry_required", "failed"].includes(value.status) ||
      typeof value.createdAt !== "string" || typeof value.updatedAt !== "string") return false;
  return value.windowId === undefined || Number.isInteger(value.windowId);
}

export async function readPreparationLocalRecord(): Promise<PreparationLocalRecord | null> {
  const result = await browser.storage.session.get(PREPARATION_LOCAL_RECORD_KEY);
  return isPreparationLocalRecord(result[PREPARATION_LOCAL_RECORD_KEY])
    ? result[PREPARATION_LOCAL_RECORD_KEY] : null;
}

export async function writePreparationLocalRecord(record: PreparationLocalRecord): Promise<void> {
  await browser.storage.session.set({ [PREPARATION_LOCAL_RECORD_KEY]: record });
}

export async function clearPreparationLocalRecord(): Promise<void> {
  await browser.storage.session.remove(PREPARATION_LOCAL_RECORD_KEY);
}

export function hasActivePreparation(record: PreparationLocalRecord | null): boolean {
  return record !== null && activeStatuses.has(record.status);
}

export function comparableLocalUrl(value: string): string {
  const url = new URL(value);
  url.hash = "";
  return url.toString().replace(/\/$/u, "");
}

export function classifyPreparationTabChange(
  record: PreparationLocalRecord,
  change: { url?: string; discarded?: boolean },
  liveUrl: string | undefined,
): PreparationLocalStatus | null {
  if (change.discarded === true) return "discarded";
  const candidate = change.url ?? liveUrl;
  if (!candidate) return null;
  try {
    return comparableLocalUrl(candidate) === comparableLocalUrl(record.applicationUrl)
      ? null : "navigation_mismatch";
  } catch {
    return "navigation_mismatch";
  }
}

export function canActivateExactPreparationTab(
  record: PreparationLocalRecord | null,
  tab: { id?: number; url?: string; discarded?: boolean } | null,
): boolean {
  if (!record || record.status !== "ready_for_review" || !tab || tab.id !== record.tabId || tab.discarded) return false;
  try { return comparableLocalUrl(tab.url ?? "") === comparableLocalUrl(record.applicationUrl); }
  catch { return false; }
}
