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
  | ({ type: "UPDATE_ASSISTED_APPLY_PREFERENCES" } & AssistedApplyPreferenceUpdate)
  | { type: "BIND_APPLICATION_PACKAGE"; bindingId: string }
  | { type: "GET_BOUND_APPLICATION_PACKAGE" }
  | { type: "REFETCH_APPLICATION_PACKAGE"; packageId: string }
  | {
      type: "SAVE_APPLICATION_CORRECTION";
      package: ApplicationPackagePayload;
      fieldIntent: string;
      correctedValue: string;
      scope: ApplicationCorrectionScope;
    }
  | {
      type: "RUN_GREENHOUSE_APPLICATION_PACKAGE" | "RUN_LEVER_APPLICATION_PACKAGE";
      package: ApplicationPackagePayload;
    }
  | { type: "UPLOAD_GREENHOUSE_CV"; package: ApplicationPackagePayload; documentId: string };

export interface ApplicationPackageJob {
  jobId: string;
  title: string;
  company: string;
  portal: "greenhouse" | "lever" | "";
  location: string;
}

export interface ApplicationPackageAnswer {
  fieldIntent: string;
  label: string;
  proposedValue: string;
  source: "profile_verified" | "scoped_preference" | "ai_suggestion";
  sensitivity: "standard" | "personal" | "legal" | "demographic";
  scope: string;
  confidence: number;
  requiresReview: boolean;
  reasons: string[];
}

export type ApplicationCorrectionScope =
  | "application"
  | "country"
  | "role"
  | "company"
  | "global"
  | "do_not_save";

export const APPLICATION_CORRECTION_SCOPE_OPTIONS: ReadonlyArray<{
  value: ApplicationCorrectionScope;
  label: string;
}> = [
  { value: "application", label: "This application" },
  { value: "country", label: "Applications in the country" },
  { value: "role", label: "Similar roles" },
  { value: "company", label: "This company" },
  { value: "global", label: "All future applications" },
  { value: "do_not_save", label: "Do not save" },
];

export interface ApplicationPackageDocumentMeta {
  documentId: string;
  documentVersion: number;
  documentKind: string;
  mimeType: string;
  fileName: string;
}

export interface ApplicationPackagePayload {
  packageId: string;
  jobId: string;
  version: number;
  schemaVersion: number;
  job: ApplicationPackageJob;
  answers: ApplicationPackageAnswer[];
  documents: ApplicationPackageDocumentMeta[];
  warnings: string[];
  policy: {
    permitSensitiveAutofill: boolean;
    permitDemographicAutofill: boolean;
    requireLegalAnswerConfirmation: boolean;
  };
}

export interface PackageLaunchResult {
  packageId: string;
  bindingId: string;
  bindingExpiresAt: string;
  status: string;
}

export type ContentRequest =
  | { type: "CONTENT_RUN_GREENHOUSE_FIXTURE_PROOF"; proposedEmail: string }
  | { type: "CONTENT_RUN_GREENHOUSE_APPLICATION_PACKAGE"; package: ApplicationPackagePayload }
  | { type: "CONTENT_RUN_LEVER_APPLICATION_PACKAGE"; package: ApplicationPackagePayload }
  | {
      type: "CONTENT_UPLOAD_GREENHOUSE_CV";
      packageId: string;
      documentId: string;
      documentVersion: number;
      fileName: string;
      mimeType: "application/pdf";
      base64Bytes: string;
    };

export interface DocumentUploadMessage {
  documentId: string;
  documentVersion: number;
  fileName: string;
  status: "uploaded" | "rejected" | "mismatch" | "preserved_existing";
  reasons: string[];
}

export interface PackageExecutionMessage extends FixtureInspectionMessage {
  packageId: string;
  executions: FixtureExecutionSummary[];
}

export interface PanelResponse {
  ok: boolean;
  state?: AssistedApplyTabState;
  connection?: ExtensionConnectionState;
  package?: ApplicationPackagePayload;
  packageExecution?: PackageExecutionMessage;
  documentUpload?: DocumentUploadMessage;
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

export function isExactLeverFixtureUrl(value: unknown): value is string {
  if (typeof value !== "string") return false;
  try {
    const url = new URL(value);
    return url.protocol === "http:" &&
      (url.hostname === "127.0.0.1" || url.hostname === "localhost") &&
      url.port === "4174" && url.pathname === "/lever-application.html" &&
      url.search === "" && url.hash === "" && url.username === "" && url.password === "";
  } catch { return false; }
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

export function isApplicationPackagePayload(value: unknown): value is ApplicationPackagePayload {
  if (!isRecord(value)) return false;
  return (
    typeof value.packageId === "string" && value.packageId.length > 0 &&
    typeof value.jobId === "string" && value.jobId.length > 0 &&
    Number.isInteger(value.version) && Number(value.version) > 0 &&
    Number.isInteger(value.schemaVersion) && Number(value.schemaVersion) > 0 &&
    isRecord(value.job) && typeof value.job.jobId === "string" &&
    typeof value.job.title === "string" && typeof value.job.company === "string" &&
    (value.job.portal === "" || value.job.portal === "greenhouse" || value.job.portal === "lever") &&
    typeof value.job.location === "string" &&
    Array.isArray(value.answers) && value.answers.every((answer) => isRecord(answer) &&
      typeof answer.fieldIntent === "string" && typeof answer.proposedValue === "string" &&
      ["profile_verified", "scoped_preference", "ai_suggestion"].includes(String(answer.source)) &&
      ["standard", "personal", "legal", "demographic"].includes(String(answer.sensitivity)) &&
      typeof answer.scope === "string" && typeof answer.confidence === "number" &&
      answer.confidence >= 0 && answer.confidence <= 1 &&
      typeof answer.requiresReview === "boolean" && isStringArray(answer.reasons)) &&
    Array.isArray(value.documents) && value.documents.every((document) => isRecord(document) &&
      typeof document.documentId === "string" && document.documentId.length > 0 &&
      Number.isInteger(document.documentVersion) && Number(document.documentVersion) > 0 &&
      typeof document.documentKind === "string" && typeof document.mimeType === "string" &&
      typeof document.fileName === "string") &&
    isStringArray(value.warnings) && isRecord(value.policy) &&
    typeof value.policy.permitSensitiveAutofill === "boolean" &&
    typeof value.policy.permitDemographicAutofill === "boolean" &&
    typeof value.policy.requireLegalAnswerConfirmation === "boolean"
  );
}

export function isPackageExecutionMessage(value: unknown): value is PackageExecutionMessage {
  return isFixtureInspectionMessage(value) && isRecord(value) &&
    typeof value.packageId === "string" && value.packageId.length > 0 &&
    Array.isArray(value.executions) && value.executions.every(isFixtureExecutionSummary);
}

export function isDocumentUploadMessage(value: unknown): value is DocumentUploadMessage {
  return isRecord(value) &&
    typeof value.documentId === "string" && value.documentId.length > 0 &&
    Number.isInteger(value.documentVersion) && Number(value.documentVersion) > 0 &&
    typeof value.fileName === "string" && value.fileName.length > 0 &&
    ["uploaded", "rejected", "mismatch", "preserved_existing"].includes(String(value.status)) &&
    isStringArray(value.reasons);
}

export function isPanelResponse(value: unknown): value is PanelResponse {
  if (!isRecord(value) || typeof value.ok !== "boolean") return false;
  if (value.ok) {
    const hasTabState = isAssistedApplyTabState(value.state);
    const hasConnection = isExtensionConnectionState(value.connection);
    const hasPackage = isApplicationPackagePayload(value.package);
    const hasPackageExecution = isPackageExecutionMessage(value.packageExecution);
    const hasDocumentUpload = isDocumentUploadMessage(value.documentUpload);
    return [hasTabState, hasConnection, hasPackage, hasPackageExecution, hasDocumentUpload]
      .filter(Boolean).length === 1;
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
  if (type === "BIND_APPLICATION_PACKAGE") {
    return typeof value.bindingId === "string" && value.bindingId.length > 0;
  }
  if (type === "REFETCH_APPLICATION_PACKAGE") {
    return typeof value.packageId === "string" && value.packageId.length > 0;
  }
  if (type === "SAVE_APPLICATION_CORRECTION") {
    return isApplicationPackagePayload(value.package) &&
      typeof value.fieldIntent === "string" && value.fieldIntent.length > 0 &&
      typeof value.correctedValue === "string" && value.correctedValue.trim().length > 0 &&
      ["application", "country", "role", "company", "global", "do_not_save"].includes(String(value.scope));
  }
  if (type === "RUN_GREENHOUSE_APPLICATION_PACKAGE" || type === "RUN_LEVER_APPLICATION_PACKAGE") {
    return isApplicationPackagePayload(value.package);
  }
  if (type === "UPLOAD_GREENHOUSE_CV") {
    return isApplicationPackagePayload(value.package) &&
      typeof value.documentId === "string" && value.documentId.length > 0;
  }
  return (
    type === "GET_ACTIVE_TAB_STATE" ||
    type === "REFRESH_ACTIVE_TAB_STATE" ||
    type === "RUN_GREENHOUSE_FIXTURE_PROOF" ||
    type === "GET_EXTENSION_CONNECTION" ||
    type === "GET_BOUND_APPLICATION_PACKAGE" ||
    type === "CONNECT_RUNR" ||
    type === "DISCONNECT_RUNR"
  );
}

export function isContentRequest(value: unknown): value is ContentRequest {
  if (!isRecord(value)) return false;
  return (
    ((value.type === "CONTENT_RUN_GREENHOUSE_APPLICATION_PACKAGE" ||
      value.type === "CONTENT_RUN_LEVER_APPLICATION_PACKAGE") &&
      isApplicationPackagePayload(value.package)) ||
    (value.type === "CONTENT_UPLOAD_GREENHOUSE_CV" &&
      typeof value.packageId === "string" && value.packageId.length > 0 &&
      typeof value.documentId === "string" && value.documentId.length > 0 &&
      Number.isInteger(value.documentVersion) && Number(value.documentVersion) > 0 &&
      typeof value.fileName === "string" && value.fileName.length > 0 && value.fileName.length <= 255 &&
      value.mimeType === "application/pdf" &&
      typeof value.base64Bytes === "string" && value.base64Bytes.length > 0) ||
    (
    value.type === "CONTENT_RUN_GREENHOUSE_FIXTURE_PROOF" &&
    typeof value.proposedEmail === "string" &&
    value.proposedEmail.length > 0)
  );
}

export function isApplicationPackageContentRequest(
  value: unknown,
): value is Exclude<ContentRequest, { type: "CONTENT_RUN_GREENHOUSE_FIXTURE_PROOF" }> {
  return isRecord(value) &&
    (((value.type === "CONTENT_RUN_GREENHOUSE_APPLICATION_PACKAGE" ||
      value.type === "CONTENT_RUN_LEVER_APPLICATION_PACKAGE") &&
      isApplicationPackagePayload(value.package)) ||
      (value.type === "CONTENT_UPLOAD_GREENHOUSE_CV" &&
        typeof value.packageId === "string" && value.packageId.length > 0 &&
        typeof value.documentId === "string" && value.documentId.length > 0 &&
        Number.isInteger(value.documentVersion) && Number(value.documentVersion) > 0 &&
        typeof value.fileName === "string" && value.fileName.length > 0 && value.fileName.length <= 255 &&
        value.mimeType === "application/pdf" &&
        typeof value.base64Bytes === "string" && value.base64Bytes.length > 0));
}
