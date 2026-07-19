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
  detectedFieldId?: string;
  fieldLabel: string;
  fieldIntent?: string;
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
      replaceFieldIntents?: string[];
    }
  | { type: "UPLOAD_SELECTED_DOCUMENT"; package: ApplicationPackagePayload; documentId: string }
  | { type: "GET_PENDING_APPLICATION_CONFIRMATION" }
  | {
      type: "RESPOND_TO_APPLICATION_CONFIRMATION";
      decision: "confirmed" | "declined";
      evidence: PendingApplicationConfirmation;
    }
  | { type: "CHECK_PORTAL_PERMISSION"; portal: "greenhouse" | "lever" }
  | { type: "REQUEST_PORTAL_PERMISSION"; portal: "greenhouse" | "lever" }
  | { type: "CHECK_ALL_OPTIONAL_PERMISSIONS" }
  | { type: "REQUEST_ALL_OPTIONAL_PERMISSIONS" };

/**
 * The only message accepted from the Runr web application. It carries an
 * opaque, short-lived binding ID â€” never profile data, package contents, or
 * executable instructions.
 */
export interface RunrWebLaunchRequest {
  type: "RUNR_WEB_BIND_APPLICATION_PACKAGE";
  bindingId: string;
  applicationUrl: string;
}

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

export type ApplicationDocumentKind = "cv" | "cover_letter" | "supporting_document";
export type ApplicationDocumentMimeType =
  | "application/pdf"
  | "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

export interface ApplicationPackageDocumentMeta {
  documentId: string;
  documentVersion: number;
  documentKind: ApplicationDocumentKind;
  mimeType: ApplicationDocumentMimeType;
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

export type PossibleSuccessEvidenceCategory =
  | "success_banner"
  | "confirmation_page"
  | "url_transition";

export interface PossibleSuccessEvidence {
  packageId: string;
  packageVersion: number;
  adapter: SupportedAts;
  adapterVersion: string;
  evidenceCategory: PossibleSuccessEvidenceCategory;
  observedAt: string;
}

export interface PendingApplicationConfirmation extends PossibleSuccessEvidence {
  uploadedDocuments: Array<{ documentId: string; documentVersion: number }>;
}

export interface TrackerConfirmationResult {
  decision: "confirmed" | "declined";
  created: boolean;
  duplicate: boolean;
  trackerRecordId?: string;
}

export interface PackageLaunchResult {
  packageId: string;
  bindingId: string;
  bindingExpiresAt: string;
  status: string;
}

export type ContentRequest =
  | { type: "CONTENT_RUN_GREENHOUSE_FIXTURE_PROOF"; proposedEmail: string }
  | { type: "CONTENT_RUN_GREENHOUSE_APPLICATION_PACKAGE"; package: ApplicationPackagePayload; replaceFieldIntents?: string[] }
  | { type: "CONTENT_RUN_LEVER_APPLICATION_PACKAGE"; package: ApplicationPackagePayload; replaceFieldIntents?: string[] }
  | {
      type: "CONTENT_UPLOAD_SELECTED_DOCUMENT";
      ats: "greenhouse" | "lever";
      packageId: string;
      documentId: string;
      documentVersion: number;
      documentKind: ApplicationDocumentKind;
      fileName: string;
      mimeType: ApplicationDocumentMimeType;
      base64Bytes: string;
    };

/** @privateRemarks Bounded lifecycle stages — each maps to an adapter method. */
export type LifecycleStage =
  | "detect"
  | "inspect"
  | "match"
  | "fill"
  | "validate"
  | "upload";

/** @privateRemarks Aggregate adapter-health outcome — never exposes specific values. */
export type AggregateOutcome =
  | "success"
  | "failure"
  | "partial"
  | "skipped";

/** @privateRemarks Bounded error category — never exposes answers, PII, or page content. */
export type ErrorCategory =
  | "none"
  | "detection_failed"
  | "inspection_failed"
  | "matching_failed"
  | "fill_rejected"
  | "fill_mismatched"
  | "validation_failed"
  | "control_unavailable"
  | "control_blocked"
  | "mime_rejected"
  | "portal_rejected"
  | "existing_value"
  | "unsupported_role"
  | "unknown";

/**
 * Privacy-safe adapter health telemetry payload.
 *
 * Contains **only** adapter identity, lifecycle stage, aggregate outcome, and a
 * bounded error category. Never includes:
 * - answers, sensitive values, document bytes/URLs/tokens, credentials, filenames
 * - raw DOM/page markup, selectors, or page content
 * - extension session tokens, user IDs, or Runr account identifiers
 */
export interface AdapterHealthTelemetry {
  schemaVersion: 1;
  adapter: "greenhouse" | "lever";
  adapterVersion: string;
  lifecycleStage: LifecycleStage;
  aggregateOutcome: AggregateOutcome;
  errorCategory: ErrorCategory;
}


export interface DocumentUploadMessage {
  documentId: string;
  documentVersion: number;
  documentKind: ApplicationDocumentKind;
  fileName: string;
  status: "uploaded" | "rejected" | "mismatch" | "preserved_existing";
  reasons: string[];
  telemetry: AdapterHealthTelemetry;
}

export interface PackageExecutionMessage extends FixtureInspectionMessage {
  packageId: string;
  executions: FixtureExecutionSummary[];
  formRevision?: number;
  changeReasons?: string[];
}

export interface PanelResponse {
  ok: boolean;
  state?: AssistedApplyTabState;
  connection?: ExtensionConnectionState;
  package?: ApplicationPackagePayload;
  packageExecution?: PackageExecutionMessage;
  documentUpload?: DocumentUploadMessage;
  pendingConfirmation?: PendingApplicationConfirmation | null;
  trackerConfirmation?: TrackerConfirmationResult;
  permissionGranted?: boolean;
  missingPortalPermissions?: Array<{ portal: "greenhouse" | "lever"; origin: string }>;
  error?: string;
}

export type ContentRuntimeEvent = {
  type: "ASSISTED_APPLY_POSSIBLE_SUCCESS";
  evidence: PossibleSuccessEvidence;
};

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

function isBoundedFieldIntentList(value: unknown): value is string[] {
  return value === undefined || (Array.isArray(value) && value.length <= 50 &&
    value.every((item) => typeof item === "string" && /^[a-z0-9_.-]{1,160}$/u.test(item)) &&
    new Set(value).size === value.length);
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
    (value.detectedFieldId === undefined || typeof value.detectedFieldId === "string") &&
    typeof value.fieldLabel === "string" &&
    (value.fieldIntent === undefined || typeof value.fieldIntent === "string") &&
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
      ["cv", "cover_letter", "supporting_document"].includes(String(document.documentKind)) &&
      ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]
        .includes(String(document.mimeType)) &&
      typeof document.fileName === "string") &&
    isStringArray(value.warnings) && isRecord(value.policy) &&
    typeof value.policy.permitSensitiveAutofill === "boolean" &&
    typeof value.policy.permitDemographicAutofill === "boolean" &&
    typeof value.policy.requireLegalAnswerConfirmation === "boolean"
  );
}

function hasPossibleSuccessEvidenceFields(value: unknown): value is PossibleSuccessEvidence {
  if (!isRecord(value)) return false;
  return typeof value.packageId === "string" && value.packageId.length > 0 &&
    Number.isInteger(value.packageVersion) && Number(value.packageVersion) > 0 &&
    (value.adapter === "greenhouse" || value.adapter === "lever") &&
    typeof value.adapterVersion === "string" && /^[0-9]+\.[0-9]+\.[0-9]+$/u.test(value.adapterVersion) &&
    ["success_banner", "confirmation_page", "url_transition"].includes(String(value.evidenceCategory)) &&
    isIsoDate(value.observedAt);
}

export function isPossibleSuccessEvidence(value: unknown): value is PossibleSuccessEvidence {
  return hasPossibleSuccessEvidenceFields(value) && isRecord(value) &&
    Object.keys(value).length === 6 && Object.keys(value).every((key) => [
      "packageId", "packageVersion", "adapter", "adapterVersion", "evidenceCategory", "observedAt",
    ].includes(key));
}

export function isPendingApplicationConfirmation(
  value: unknown,
): value is PendingApplicationConfirmation {
  return hasPossibleSuccessEvidenceFields(value) && isRecord(value) && Object.keys(value).length === 7 &&
    Object.keys(value).every((key) => [
      "packageId", "packageVersion", "adapter", "adapterVersion", "evidenceCategory", "observedAt",
      "uploadedDocuments",
    ].includes(key)) &&
    Array.isArray(value.uploadedDocuments) && value.uploadedDocuments.every((document) =>
      isRecord(document) && typeof document.documentId === "string" && document.documentId.length > 0 &&
      Number.isInteger(document.documentVersion) && Number(document.documentVersion) > 0);
}

export function isTrackerConfirmationResult(value: unknown): value is TrackerConfirmationResult {
  return isRecord(value) && (value.decision === "confirmed" || value.decision === "declined") &&
    typeof value.created === "boolean" && typeof value.duplicate === "boolean" &&
    (value.trackerRecordId === undefined || typeof value.trackerRecordId === "string");
}

export function isContentRuntimeEvent(value: unknown): value is ContentRuntimeEvent {
  return isRecord(value) && value.type === "ASSISTED_APPLY_POSSIBLE_SUCCESS" &&
    isPossibleSuccessEvidence(value.evidence);
}

export function isPackageExecutionMessage(value: unknown): value is PackageExecutionMessage {
  return isFixtureInspectionMessage(value) && isRecord(value) &&
    typeof value.packageId === "string" && value.packageId.length > 0 &&
    Array.isArray(value.executions) && value.executions.every(isFixtureExecutionSummary) &&
    (value.formRevision === undefined || (Number.isInteger(value.formRevision) && Number(value.formRevision) >= 0)) &&
    (value.changeReasons === undefined || isStringArray(value.changeReasons));
}

export function isDocumentUploadMessage(value: unknown): value is DocumentUploadMessage {
  return isRecord(value) &&
    typeof value.documentId === "string" && value.documentId.length > 0 &&
    Number.isInteger(value.documentVersion) && Number(value.documentVersion) > 0 &&
    ["cv", "cover_letter", "supporting_document"].includes(String(value.documentKind)) &&
    typeof value.fileName === "string" && value.fileName.length > 0 &&
    ["uploaded", "rejected", "mismatch", "preserved_existing"].includes(String(value.status)) &&
    isStringArray(value.reasons) && isAdapterHealthTelemetry(value.telemetry);
}

const LIFECYCLE_STAGES: LifecycleStage[] = [
  "detect", "inspect", "match", "fill", "validate", "upload",
];
const AGGREGATE_OUTCOMES: AggregateOutcome[] = [
  "success", "failure", "partial", "skipped",
];
const ERROR_CATEGORIES: ErrorCategory[] = [
  "none", "detection_failed", "inspection_failed", "matching_failed",
  "fill_rejected", "fill_mismatched", "validation_failed",
  "control_unavailable", "control_blocked", "mime_rejected",
  "portal_rejected", "existing_value", "unsupported_role", "unknown",
];

export function isAdapterHealthTelemetry(value: unknown): value is AdapterHealthTelemetry {
  if (!isRecord(value)) return false;
  return value.schemaVersion === 1 &&
    (value.adapter === "greenhouse" || value.adapter === "lever") &&
    typeof value.adapterVersion === "string" && /^[0-9]+\.[0-9]+\.[0-9]+$/u.test(value.adapterVersion) &&
    LIFECYCLE_STAGES.includes(value.lifecycleStage as LifecycleStage) &&
    AGGREGATE_OUTCOMES.includes(value.aggregateOutcome as AggregateOutcome) &&
    ERROR_CATEGORIES.includes(value.errorCategory as ErrorCategory) &&
    Object.keys(value).length === 6 &&
    Object.keys(value).every((key) => ["schemaVersion", "adapter", "adapterVersion",
      "lifecycleStage", "aggregateOutcome", "errorCategory"].includes(key));
}

/**
 * Remote telemetry configuration — strictly data-only.
 *
 * Must be and remain exclusively data: thresholds and toggles that cannot:
 * - change DOM detection, inspection, matching, fill, or validation algorithms
 * - remove submission protections or manual-only classifications
 * - execute arbitrary code, load scripts, or evaluate expressions
 * - enable unsupported adapters or portals
 *
 * The only permitted fields are numeric thresholds and boolean toggles that
 * influence telemetry sampling and batching, never adapter behavior.
 */
export interface RemoteTelemetryConfig {
  schemaVersion: 1;
  /** Events are batched every N seconds (min 5, max 300). */
  batchIntervalSeconds: number;
  /** Probability [0-1] of sending an event. 1 = always. */
  sampleRate: number;
  /** Maximum queued events before forced flush. */
  maxQueueSize: number;
}

export function isRemoteTelemetryConfig(value: unknown): value is RemoteTelemetryConfig {
  if (!isRecord(value)) return false;
  return (
    Object.keys(value).length === 4 &&
    value.schemaVersion === 1 &&
    typeof value.batchIntervalSeconds === "number" &&
    value.batchIntervalSeconds >= 5 &&
    value.batchIntervalSeconds <= 300 &&
    Number.isInteger(value.batchIntervalSeconds) &&
    typeof value.sampleRate === "number" &&
    value.sampleRate >= 0 &&
    value.sampleRate <= 1 &&
    typeof value.maxQueueSize === "number" &&
    value.maxQueueSize >= 1 &&
    value.maxQueueSize <= 1000 &&
    Number.isInteger(value.maxQueueSize) &&
    // Proof: all keys are known data-only primitives. No "eval", "fn", "script",
    // "algorithm", "adapter", "protection", "submit", "command", or similar key
    // is accepted by this validator.
    Object.keys(value).every((key) =>
      ["schemaVersion", "batchIntervalSeconds", "sampleRate", "maxQueueSize"].includes(key))
  );
}

export function isPanelResponse(value: unknown): value is PanelResponse {
  if (!isRecord(value) || typeof value.ok !== "boolean") return false;
  if (value.ok) {
    const hasTabState = isAssistedApplyTabState(value.state);
    const hasConnection = isExtensionConnectionState(value.connection);
    const hasPackage = isApplicationPackagePayload(value.package);
    const hasPackageExecution = isPackageExecutionMessage(value.packageExecution);
    const hasDocumentUpload = isDocumentUploadMessage(value.documentUpload);
    const hasPendingConfirmation = "pendingConfirmation" in value &&
      (value.pendingConfirmation === null || isPendingApplicationConfirmation(value.pendingConfirmation));
    const hasTrackerConfirmation = isTrackerConfirmationResult(value.trackerConfirmation);
    const hasPermissionGranted = "permissionGranted" in value && typeof value.permissionGranted === "boolean";
    const hasMissingPermissions = "missingPortalPermissions" in value &&
      (value.missingPortalPermissions === undefined ||
        (Array.isArray(value.missingPortalPermissions) &&
          value.missingPortalPermissions.every((perm: unknown) => isRecord(perm) &&
            (perm.portal === "greenhouse" || perm.portal === "lever") &&
            typeof perm.origin === "string")));
    const nonErrorFields = [hasTabState, hasConnection, hasPackage, hasPackageExecution, hasDocumentUpload,
      hasPendingConfirmation, hasTrackerConfirmation, hasPermissionGranted, hasMissingPermissions]
      .filter(Boolean).length;
    return nonErrorFields >= 1;
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
    return isApplicationPackagePayload(value.package) && isBoundedFieldIntentList(value.replaceFieldIntents);
  }
  if (type === "UPLOAD_SELECTED_DOCUMENT") {
    return isApplicationPackagePayload(value.package) &&
      typeof value.documentId === "string" && value.documentId.length > 0;
  }
  if (type === "RESPOND_TO_APPLICATION_CONFIRMATION") {
    return (value.decision === "confirmed" || value.decision === "declined") &&
      isPendingApplicationConfirmation(value.evidence);
  }
  if (type === "CHECK_PORTAL_PERMISSION" || type === "REQUEST_PORTAL_PERMISSION") {
    return value.portal === "greenhouse" || value.portal === "lever";
  }
  return (
    type === "GET_ACTIVE_TAB_STATE" ||
    type === "REFRESH_ACTIVE_TAB_STATE" ||
    type === "RUN_GREENHOUSE_FIXTURE_PROOF" ||
    type === "GET_EXTENSION_CONNECTION" ||
    type === "GET_BOUND_APPLICATION_PACKAGE" ||
    type === "CONNECT_RUNR" ||
    type === "DISCONNECT_RUNR" ||
    type === "GET_PENDING_APPLICATION_CONFIRMATION" ||
    type === "CHECK_ALL_OPTIONAL_PERMISSIONS" ||
    type === "REQUEST_ALL_OPTIONAL_PERMISSIONS"
  );
}

export function isContentRequest(value: unknown): value is ContentRequest {
  if (!isRecord(value)) return false;
  return (
    ((value.type === "CONTENT_RUN_GREENHOUSE_APPLICATION_PACKAGE" ||
      value.type === "CONTENT_RUN_LEVER_APPLICATION_PACKAGE") &&
      isApplicationPackagePayload(value.package) && isBoundedFieldIntentList(value.replaceFieldIntents)) ||
    (value.type === "CONTENT_UPLOAD_SELECTED_DOCUMENT" &&
      (value.ats === "greenhouse" || value.ats === "lever") &&
      typeof value.packageId === "string" && value.packageId.length > 0 &&
      typeof value.documentId === "string" && value.documentId.length > 0 &&
      Number.isInteger(value.documentVersion) && Number(value.documentVersion) > 0 &&
      ["cv", "cover_letter", "supporting_document"].includes(String(value.documentKind)) &&
      typeof value.fileName === "string" && value.fileName.length > 0 && value.fileName.length <= 255 &&
      ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]
        .includes(String(value.mimeType)) &&
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
      isApplicationPackagePayload(value.package) && isBoundedFieldIntentList(value.replaceFieldIntents)) ||
      (value.type === "CONTENT_UPLOAD_SELECTED_DOCUMENT" &&
        (value.ats === "greenhouse" || value.ats === "lever") &&
        typeof value.packageId === "string" && value.packageId.length > 0 &&
        typeof value.documentId === "string" && value.documentId.length > 0 &&
        Number.isInteger(value.documentVersion) && Number(value.documentVersion) > 0 &&
        ["cv", "cover_letter", "supporting_document"].includes(String(value.documentKind)) &&
        typeof value.fileName === "string" && value.fileName.length > 0 && value.fileName.length <= 255 &&
        ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]
          .includes(String(value.mimeType)) &&
        typeof value.base64Bytes === "string" && value.base64Bytes.length > 0));
}

export function isRunrWebLaunchRequest(value: unknown): value is RunrWebLaunchRequest {
  if (!isRecord(value) || value.type !== "RUNR_WEB_BIND_APPLICATION_PACKAGE") return false;
  if (typeof value.bindingId !== "string" || value.bindingId.length < 20 || value.bindingId.length > 256) {
    return false;
  }
  if (typeof value.applicationUrl !== "string" || value.applicationUrl.length > 2048) return false;
  try {
    const url = new URL(value.applicationUrl);
    return url.protocol === "https:" ||
      (url.protocol === "http:" && url.hostname === "127.0.0.1");
  } catch {
    return false;
  }
}
