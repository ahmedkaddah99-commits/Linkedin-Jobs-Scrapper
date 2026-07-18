export type SupportedAts = "greenhouse" | "lever";

export type FixtureExecutionStatus =
  | "filled"
  | "already_filled"
  | "preserved_existing"
  | "skipped_hidden"
  | "skipped_disabled"
  | "rejected"
  | "mismatch";

export interface FixtureExecutionSummary {
  fieldLabel: string;
  status: FixtureExecutionStatus;
  acceptedValue?: string;
  reasons: string[];
}

export interface FixtureInspectionMessage {
  ats: SupportedAts | null;
  fixtureAvailable: boolean;
  fieldCount: number;
  manualReasons: string[];
}

export interface FixtureProofMessage extends FixtureInspectionMessage {
  execution: FixtureExecutionSummary | null;
}

export interface AssistedApplyTabState {
  tabId: number;
  url: string;
  ats: SupportedAts | null;
  status: "unsupported" | "recognized" | "fixture_ready" | "fixture_verified" | "error";
  fixtureAvailable: boolean;
  fieldCount: number;
  manualReasons: string[];
  execution: FixtureExecutionSummary | null;
  errorCode?: "permission_required" | "page_unavailable" | "runner_error";
  updatedAt: string;
}

export interface AssistedApplyPreferences {
  schemaVersion: 1;
  permitSensitiveAutofill: boolean;
  permitDemographicAutofill: boolean;
  requireLegalAnswerConfirmation: true;
  revision: number;
  updatedAt: string;
}

export interface ExtensionSessionSummary {
  sessionId: string;
  userId: string;
  expiresAt: string;
  createdAt?: string;
  displayName?: string;
  email?: string;
}

export interface ExtensionConnectionState {
  status: "disconnected" | "connected" | "expired";
  session: ExtensionSessionSummary | null;
  preferences: AssistedApplyPreferences;
  warning?: string;
}

export interface AssistedApplyPreferenceUpdate {
  permitSensitiveAutofill: boolean;
  permitDemographicAutofill: boolean;
}

export type PanelRequest =
  | { type: "GET_ACTIVE_TAB_STATE" }
  | { type: "REFRESH_ACTIVE_TAB_STATE" }
  | { type: "RUN_GREENHOUSE_FIXTURE_PROOF" }
  | { type: "GET_EXTENSION_CONNECTION" }
  | { type: "CONNECT_RUNR" }
  | { type: "DISCONNECT_RUNR" }
  | ({ type: "UPDATE_ASSISTED_APPLY_PREFERENCES" } & AssistedApplyPreferenceUpdate);

export type ContentRequest = {
  type: "CONTENT_RUN_GREENHOUSE_FIXTURE_PROOF";
  proposedEmail: string;
};

export interface PanelResponse {
  ok: boolean;
  state?: AssistedApplyTabState;
  connection?: ExtensionConnectionState;
  error?: string;
}

export function isExactGreenhouseFixtureUrl(value: unknown): value is string {
  if (typeof value !== "string") return false;
  try {
    const url = new URL(value);
    return (
      url.protocol === "http:" &&
      (url.hostname === "127.0.0.1" || url.hostname === "localhost") &&
      url.port === "4174" &&
      url.pathname === "/greenhouse-application.html" &&
      url.search === "" &&
      url.hash === "" &&
      url.username === "" &&
      url.password === ""
    );
  } catch {
    return false;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isIsoDate(value: unknown): value is string {
  return typeof value === "string" && value.length > 0 && Number.isFinite(Date.parse(value));
}

function isSupportedAts(value: unknown): value is SupportedAts | null {
  return value === null || value === "greenhouse" || value === "lever";
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isFixtureExecutionSummary(value: unknown): value is FixtureExecutionSummary {
  if (!isRecord(value)) return false;
  const statuses: FixtureExecutionStatus[] = [
    "filled",
    "already_filled",
    "preserved_existing",
    "skipped_hidden",
    "skipped_disabled",
    "rejected",
    "mismatch",
  ];
  return (
    typeof value.fieldLabel === "string" &&
    statuses.includes(value.status as FixtureExecutionStatus) &&
    (value.acceptedValue === undefined || typeof value.acceptedValue === "string") &&
    isStringArray(value.reasons)
  );
}

export function isFixtureInspectionMessage(value: unknown): value is FixtureInspectionMessage {
  if (!isRecord(value)) return false;
  return (
    isSupportedAts(value.ats) &&
    typeof value.fixtureAvailable === "boolean" &&
    typeof value.fieldCount === "number" &&
    Number.isInteger(value.fieldCount) &&
    value.fieldCount >= 0 &&
    isStringArray(value.manualReasons)
  );
}

export function isFixtureProofMessage(value: unknown): value is FixtureProofMessage {
  return (
    isFixtureInspectionMessage(value) &&
    isRecord(value) &&
    (value.execution === null || isFixtureExecutionSummary(value.execution))
  );
}

export function isAssistedApplyTabState(value: unknown): value is AssistedApplyTabState {
  if (!isRecord(value)) return false;
  const statuses: AssistedApplyTabState["status"][] = [
    "unsupported",
    "recognized",
    "fixture_ready",
    "fixture_verified",
    "error",
  ];
  const errorCodes: NonNullable<AssistedApplyTabState["errorCode"]>[] = [
    "permission_required",
    "page_unavailable",
    "runner_error",
  ];
  return (
    typeof value.tabId === "number" &&
    Number.isInteger(value.tabId) &&
    value.tabId >= 0 &&
    typeof value.url === "string" &&
    isSupportedAts(value.ats) &&
    statuses.includes(value.status as AssistedApplyTabState["status"]) &&
    typeof value.fixtureAvailable === "boolean" &&
    typeof value.fieldCount === "number" &&
    Number.isInteger(value.fieldCount) &&
    value.fieldCount >= 0 &&
    isStringArray(value.manualReasons) &&
    (value.execution === null || isFixtureExecutionSummary(value.execution)) &&
    (value.errorCode === undefined ||
      errorCodes.includes(value.errorCode as NonNullable<AssistedApplyTabState["errorCode"]>)) &&
    typeof value.updatedAt === "string"
  );
}

export function isAssistedApplyPreferences(value: unknown): value is AssistedApplyPreferences {
  if (!isRecord(value)) return false;
  return (
    value.schemaVersion === 1 &&
    typeof value.permitSensitiveAutofill === "boolean" &&
    typeof value.permitDemographicAutofill === "boolean" &&
    value.requireLegalAnswerConfirmation === true &&
    typeof value.revision === "number" &&
    Number.isInteger(value.revision) &&
    value.revision >= 0 &&
    (value.updatedAt === "" || isIsoDate(value.updatedAt))
  );
}

export function isExtensionSessionSummary(value: unknown): value is ExtensionSessionSummary {
  if (!isRecord(value)) return false;
  return (
    typeof value.sessionId === "string" &&
    value.sessionId.length > 0 &&
    typeof value.userId === "string" &&
    value.userId.length > 0 &&
    isIsoDate(value.expiresAt) &&
    (value.createdAt === undefined || isIsoDate(value.createdAt)) &&
    (value.displayName === undefined || typeof value.displayName === "string") &&
    (value.email === undefined || typeof value.email === "string")
  );
}

export function isExtensionConnectionState(value: unknown): value is ExtensionConnectionState {
  if (!isRecord(value) || !isAssistedApplyPreferences(value.preferences)) return false;
  const statuses: ExtensionConnectionState["status"][] = [
    "disconnected",
    "connected",
    "expired",
  ];
  if (!statuses.includes(value.status as ExtensionConnectionState["status"])) return false;
  if (value.warning !== undefined && typeof value.warning !== "string") return false;
  if (value.status === "connected") return isExtensionSessionSummary(value.session);
  return value.session === null;
}

export function isPanelResponse(value: unknown): value is PanelResponse {
  if (!isRecord(value) || typeof value.ok !== "boolean") return false;
  if (value.ok) {
    const hasTabState = isAssistedApplyTabState(value.state);
    const hasConnection = isExtensionConnectionState(value.connection);
    return hasTabState !== hasConnection;
  }
  return value.error === undefined || typeof value.error === "string";
}

export function isPanelRequest(value: unknown): value is PanelRequest {
  if (!isRecord(value)) return false;
  const type = value.type;
  if (type === "UPDATE_ASSISTED_APPLY_PREFERENCES") {
    return (
      typeof value.permitSensitiveAutofill === "boolean" &&
      typeof value.permitDemographicAutofill === "boolean"
    );
  }
  return (
    type === "GET_ACTIVE_TAB_STATE" ||
    type === "REFRESH_ACTIVE_TAB_STATE" ||
    type === "RUN_GREENHOUSE_FIXTURE_PROOF" ||
    type === "GET_EXTENSION_CONNECTION" ||
    type === "CONNECT_RUNR" ||
    type === "DISCONNECT_RUNR"
  );
}

export function isContentRequest(value: unknown): value is ContentRequest {
  if (!value || typeof value !== "object") return false;
  const candidate = value as { type?: unknown; proposedEmail?: unknown };
  return (
    candidate.type === "CONTENT_RUN_GREENHOUSE_FIXTURE_PROOF" &&
    typeof candidate.proposedEmail === "string" &&
    candidate.proposedEmail.length > 0
  );
}
