import type {
  AssistedApplyPreferences,
  ExtensionSessionSummary,
} from "@runr/extension-messages";

export interface CreateConnectionRequestInput {
  code_challenge: string;
  state: string;
  installation_id: string;
  extension_version: string;
}

export interface ExchangeTokenInput {
  request_id: string;
  authorization_code: string;
  code_verifier: string;
}

export interface UpdatePreferencesInput {
  permit_sensitive_autofill: boolean;
  permit_demographic_autofill: boolean;
}

export interface ConnectionRequestResult {
  requestId: string;
  expiresAt: string;
}

export interface SessionTokenResult {
  sessionToken: string;
  session: ExtensionSessionSummary;
  preferences: AssistedApplyPreferences;
}

export interface SessionResult {
  session: ExtensionSessionSummary;
  preferences: AssistedApplyPreferences;
}

export const DEFAULT_ASSISTED_APPLY_PREFERENCES: AssistedApplyPreferences = {
  schemaVersion: 1,
  permitSensitiveAutofill: false,
  permitDemographicAutofill: false,
  requireLegalAnswerConfirmation: true,
  revision: 0,
  updatedAt: "",
};

function asRecord(value: unknown, name: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`Runr returned an invalid ${name}.`);
  }
  return value as Record<string, unknown>;
}

function requiredString(
  record: Record<string, unknown>,
  key: string,
  name: string,
  maximumLength = 512,
): string {
  const value = record[key];
  if (typeof value !== "string" || value.length === 0 || value.length > maximumLength) {
    throw new Error(`Runr returned an invalid ${name}.`);
  }
  return value;
}

function optionalString(
  record: Record<string, unknown>,
  key: string,
  name: string,
  maximumLength = 512,
): string | undefined {
  const value = record[key];
  if (value === undefined || value === null || value === "") return undefined;
  if (typeof value !== "string" || value.length > maximumLength) {
    throw new Error(`Runr returned an invalid ${name}.`);
  }
  return value;
}

function requiredIsoDate(record: Record<string, unknown>, key: string, name: string): string {
  const value = requiredString(record, key, name, 128);
  if (!Number.isFinite(Date.parse(value))) throw new Error(`Runr returned an invalid ${name}.`);
  return value;
}

function optionalIsoDate(
  record: Record<string, unknown>,
  key: string,
  name: string,
): string | undefined {
  const value = optionalString(record, key, name, 128);
  if (value === undefined) return undefined;
  if (!Number.isFinite(Date.parse(value))) throw new Error(`Runr returned an invalid ${name}.`);
  return value;
}

export function parsePreferences(value: unknown): AssistedApplyPreferences {
  const record = asRecord(value, "Assisted Apply preferences");
  if (
    record.schema_version !== 1 ||
    typeof record.permit_sensitive_autofill !== "boolean" ||
    typeof record.permit_demographic_autofill !== "boolean" ||
    record.require_legal_answer_confirmation !== true ||
    typeof record.revision !== "number" ||
    !Number.isInteger(record.revision) ||
    record.revision < 0
  ) {
    throw new Error("Runr returned invalid Assisted Apply preferences.");
  }
  return {
    schemaVersion: 1,
    permitSensitiveAutofill: record.permit_sensitive_autofill,
    permitDemographicAutofill: record.permit_demographic_autofill,
    requireLegalAnswerConfirmation: true,
    revision: record.revision,
    updatedAt: requiredIsoDate(record, "updated_at", "preference update time"),
  };
}

export function parseSession(value: unknown): ExtensionSessionSummary {
  const record = asRecord(value, "extension session");
  const session: ExtensionSessionSummary = {
    sessionId: requiredString(record, "session_id", "session identifier", 256),
    userId: requiredString(record, "user_id", "session user", 256),
    expiresAt: requiredIsoDate(record, "expires_at", "session expiry"),
  };
  const createdAt = optionalIsoDate(record, "created_at", "session creation time");
  const displayName = optionalString(record, "display_name", "display name", 256);
  const email = optionalString(record, "email", "email address", 320);
  if (createdAt !== undefined) session.createdAt = createdAt;
  if (displayName !== undefined) session.displayName = displayName;
  if (email !== undefined) session.email = email;
  return session;
}

function requireFutureExpiry(expiresAt: string, nowMs: number, name: string): void {
  if (Date.parse(expiresAt) <= nowMs) throw new Error(`Runr returned an expired ${name}.`);
}

export function parseConnectionRequestResponse(
  value: unknown,
  nowMs: number,
): ConnectionRequestResult {
  const record = asRecord(value, "connection request");
  const result = {
    requestId: requiredString(record, "request_id", "connection request identifier", 256),
    expiresAt: requiredIsoDate(record, "expires_at", "connection request expiry"),
  };
  requireFutureExpiry(result.expiresAt, nowMs, "connection request");
  return result;
}

export function parseSessionTokenResponse(value: unknown, nowMs: number): SessionTokenResult {
  const record = asRecord(value, "extension token response");
  const sessionToken = requiredString(record, "session_token", "extension session token", 4096);
  if (sessionToken.length < 20) throw new Error("Runr returned an invalid extension session token.");
  const session = parseSession(record.session);
  requireFutureExpiry(session.expiresAt, nowMs, "extension session");
  return {
    sessionToken,
    session,
    preferences: parsePreferences(record.preferences),
  };
}

export function parseSessionResponse(value: unknown, nowMs: number): SessionResult {
  const record = asRecord(value, "extension session response");
  const session = parseSession(record.session);
  requireFutureExpiry(session.expiresAt, nowMs, "extension session");
  return { session, preferences: parsePreferences(record.preferences) };
}

export function parsePreferencesResponse(value: unknown): AssistedApplyPreferences {
  const record = asRecord(value, "preference response");
  return parsePreferences(record.preferences);
}
