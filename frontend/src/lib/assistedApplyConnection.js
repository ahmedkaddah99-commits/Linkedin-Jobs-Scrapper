const OPAQUE_ID_PATTERN = /^[A-Za-z0-9_-]{8,200}$/;
const CHROMIUM_IDENTITY_CALLBACK_PATTERN =
  /^https:\/\/[a-p]{32}\.chromiumapp\.org\/runr\/connect(?:\?[^#\s]*)?$/;

export const DEFAULT_ASSISTED_APPLY_PREFERENCES = Object.freeze({
  permit_sensitive_autofill: false,
  permit_demographic_autofill: false,
  require_legal_answer_confirmation: true,
});

export const ASSISTED_APPLY_CAPABILITIES = Object.freeze([
  "Inspect supported Greenhouse and Lever application forms.",
  "Fill approved values from the application package you launched in Runr.",
  "Upload only the documents selected for that application.",
  "Report possible submission success so you can confirm tracking in Runr.",
]);

export const ASSISTED_APPLY_BOUNDARIES = Object.freeze([
  "Runr never clicks the employer's final Submit button.",
  "Runr never reads or stores employer passwords, passkeys, or account credentials.",
  "CAPTCHA, assessments, account creation, signatures, declarations, and legal terms stay manual.",
  "Legal answers always require your explicit confirmation.",
]);

function stringValue(value) {
  return String(value || "").trim();
}

export function normalizeOpaqueId(value) {
  const normalized = stringValue(value);
  return OPAQUE_ID_PATTERN.test(normalized) ? normalized : "";
}

export function parseAssistedApplyConnectionSearch(search = "") {
  const params = search instanceof URLSearchParams
    ? search
    : new URLSearchParams(String(search || "").replace(/^\?/, ""));
  const rawRequestId = stringValue(params.get("request_id"));
  return {
    requestId: normalizeOpaqueId(rawRequestId),
    invalidRequestId: Boolean(rawRequestId) && !normalizeOpaqueId(rawRequestId),
  };
}

export function normalizeAssistedApplyPreferences(value = {}) {
  return {
    permit_sensitive_autofill: value?.permit_sensitive_autofill === true,
    permit_demographic_autofill: value?.permit_demographic_autofill === true,
    require_legal_answer_confirmation: true,
  };
}

export function buildAssistedApplyPreferencesPayload(value = {}) {
  const preferences = normalizeAssistedApplyPreferences(value);
  return {
    permit_sensitive_autofill: preferences.permit_sensitive_autofill,
    permit_demographic_autofill: preferences.permit_demographic_autofill,
    require_legal_answer_confirmation: true,
  };
}

export function normalizeAssistedApplyConnectionPayload(
  payload = {},
  { requestId = "" } = {},
) {
  const pendingSource =
    payload?.pending_request ||
    payload?.connection_request ||
    (payload?.request_id ? payload : null);
  const pendingId = normalizeOpaqueId(pendingSource?.request_id || pendingSource?.id);
  const pendingStatus = stringValue(pendingSource?.status).toLowerCase();
  const pendingRequest = pendingId && pendingId === requestId && ["", "pending"].includes(pendingStatus)
    ? {
        request_id: pendingId,
        status: pendingStatus || "pending",
        expires_at: stringValue(pendingSource?.expires_at || pendingSource?.request_expires_at),
        client_label:
          stringValue(
            pendingSource?.client_label ||
            pendingSource?.browser_name ||
            pendingSource?.extension_version,
          ) ||
          "Runr browser extension",
      }
    : null;
  const requestState = stringValue(payload?.request_state || pendingStatus).toLowerCase();
  const state = pendingRequest
    ? "pending"
    : requestId && ["expired", "rejected", "revoked", "not_found"].includes(requestState)
      ? requestState
      : requestId && ["active", "authorized", "connected"].includes(requestState)
        ? "connected"
        : "disconnected";
  return {
    state,
    pending_request: pendingRequest,
    preferences: normalizeAssistedApplyPreferences(payload?.preferences),
  };
}

function encodeOpaquePathId(value, label) {
  const normalized = normalizeOpaqueId(value);
  if (!normalized) throw new Error(`${label} is invalid.`);
  return encodeURIComponent(normalized);
}

export function assistedApplyConnectionPath(requestId = "") {
  const normalized = normalizeOpaqueId(requestId);
  return normalized
    ? `/assisted-apply/connection?request_id=${encodeURIComponent(normalized)}`
    : "/assisted-apply/connection";
}

export function assistedApplyConnectionRequestActionPath(requestId, action) {
  if (!new Set(["approve", "reject"]).has(action)) {
    throw new Error("Connection request action is invalid.");
  }
  return `/assisted-apply/connection-requests/${encodeOpaquePathId(
    requestId,
    "Connection request",
  )}/${action}`;
}

export function normalizeBackendCompletionUrl(value) {
  const normalized = stringValue(value);
  if (!CHROMIUM_IDENTITY_CALLBACK_PATTERN.test(normalized)) return "";
  try {
    const parsed = new URL(normalized);
    if (
      parsed.protocol !== "https:" ||
      parsed.username ||
      parsed.password ||
      parsed.port ||
      parsed.pathname !== "/runr/connect" ||
      parsed.hash
    ) {
      return "";
    }
    return parsed.toString();
  } catch {
    return "";
  }
}
