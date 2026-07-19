import { labelize } from "./formatters.js";

const STORAGE_KEYS = {
  baseUrl: "runr.api.baseUrl",
};

// This must match the Clerk JWT Template name configured in the Clerk dashboard.
export const CLERK_JWT_TEMPLATE_NAME = "runr_backend";

export const QUOTA_EXCEEDED_EVENT = "runr:quota-exceeded";
const SLOW_REQUEST_THRESHOLD_MS = 5000;
const REQUEST_DIAGNOSTIC_SOURCE = "frontend_api_request_diagnostic";


const _API_BASE_URL_SENTINEL_PATTERN = /^\s*\$\{[^}]*\}\s*$/;
const _API_BASE_URL_INVALID_CHARS = /[<>"'\s]/;

/** Return true when a resolved base URL looks like an unresolved Vite placeholder.
 *  This guards against bundles that ship with literal `${...}` strings because
 *  the build-time environment variable was missing. */
function _isPlaceholderApiBase(value) {
  const trimmed = String(value || "").trim();
  if (!trimmed) {
    return true;
  }
  if (_API_BASE_URL_SENTINEL_PATTERN.test(trimmed)) {
    return true;
  }
  // A relative base like /v1 is always valid.
  if (trimmed.startsWith("/")) {
    return false;
  }
  try {
    const parsed = new URL(trimmed);
    if (!parsed.protocol || !parsed.hostname) {
      return true;
    }
    if (_API_BASE_URL_INVALID_CHARS.test(trimmed)) {
      return true;
    }
    return false;
  } catch {
    return true;
  }
}

export function resolveDefaultApiBaseUrl(env = import.meta.env || {}) {
  const configuredBaseUrl = String(env.VITE_API_BASE_URL || "").trim();
  if (configuredBaseUrl && !_isPlaceholderApiBase(configuredBaseUrl)) {
    return configuredBaseUrl.replace(/\/$/, "");
  }
  const apiExternalHostname = String(env.VITE_API_EXTERNAL_HOSTNAME || "")
    .trim()
    .replace(/^https?:\/\//i, "")
    .replace(/\/.*$/, "");
  if (apiExternalHostname) {
    const derived = `https://${apiExternalHostname}/v1`;
    if (!_isPlaceholderApiBase(derived)) {
      return derived;
    }
  }
  return "/v1";
}

export function getDefaultApiBaseUrl() {
  return resolveDefaultApiBaseUrl();
}

export function loadStoredConnection() {
  const storedBaseUrl = window.localStorage.getItem(STORAGE_KEYS.baseUrl) || "";
  return {
    baseUrl: storedBaseUrl || getDefaultApiBaseUrl(),
    accessToken: "",
  };
}

export function persistConnection({ baseUrl }) {
  window.localStorage.setItem(
    STORAGE_KEYS.baseUrl,
    String(baseUrl || "").trim() || getDefaultApiBaseUrl(),
  );
}

export function clearStoredConnection() {
  window.localStorage.removeItem(STORAGE_KEYS.baseUrl);
}

export function resolveApiUrl(baseUrl, path) {
  const normalizedBase = String(baseUrl || getDefaultApiBaseUrl())
    .trim()
    .replace(/\/+$/, "");
  const normalizedPath = String(path || "").trim();
  if (/^https?:\/\//i.test(normalizedPath)) {
    return normalizedPath;
  }
  if (!normalizedPath) {
    return normalizedBase;
  }
  return `${normalizedBase}/${normalizedPath.replace(/^\/+/, "")}`;
}

// --- AbortController manager (prevents duplicate in-flight requests) ---

const _IN_FLIGHT = new Map();

/** Create or reuse an AbortController keyed by `${method}:${path}`.
 *  Any previous in-flight request to the same key is cancelled. */
export function createDedupedAbortController(method, path) {
  const key = `${String(method || "GET").toUpperCase()}:${String(path || "")}`;
  const existing = _IN_FLIGHT.get(key);
  if (existing) {
    try {
      existing.abort();
    } catch {
      // best-effort
    }
  }
  const controller = new AbortController();
  controller._dedupKey = key;
  _IN_FLIGHT.set(key, controller);
  return controller;
}

/** Mark a previously created deduped controller as settled. */
export function settleDedupedAbortController(controller) {
  if (!controller || !controller._dedupKey) {
    return;
  }
  if (_IN_FLIGHT.get(controller._dedupKey) === controller) {
    _IN_FLIGHT.delete(controller._dedupKey);
  }
}

/** Cancel all tracked in-flight requests (e.g. on page navigation). */
export function cancelAllDedupedRequests() {
  for (const [key, controller] of _IN_FLIGHT) {
    try {
      controller.abort();
    } catch {
      // best-effort
    }
    _IN_FLIGHT.delete(key);
  }
}

// Legacy retry implementation retained from the bad merge. The canonical
// exported implementation appears below `apiRequest`.
// --- Bounded retry with exponential backoff ---

const LEGACY_RETRYABLE_STATUS_CODES = new Set([408, 429, 502, 503, 504]);

/** Maximum total backoff delay across all retries (ms). */
const LEGACY_MAX_TOTAL_RETRY_DELAY_MS = 30000;

function _isLegacyRetryableError(error) {
  if (!error || error.name === "AbortError") {
    return false;
  }
  const status = Number(error?.status || 0);
  if (status > 0 && LEGACY_RETRYABLE_STATUS_CODES.has(status)) {
    return true;
  }
  // Network errors (TypeError from fetch when offline/DNS fails)
  if (error instanceof TypeError && /network|fetch/i.test(String(error.message || ""))) {
    return true;
  }
  return false;
}

/**
 * Wrap apiRequest with bounded retries and exponential backoff.
 *
 * Options (on top of apiRequest options):
 *   maxRetries  – max number of retry attempts (default 2, max 5).
 *   retryDelayMs – initial backoff in ms (default 1000).
 */
async function legacyApiRequestWithRetry(baseUrl, accessTokenOrResolver, path, options = {}) {
  const maxRetries = Math.min(5, Math.max(0, Number(options.maxRetries ?? 2)));
  const initialDelayMs = Math.max(500, Number(options.retryDelayMs ?? 1000));
  let totalDelay = 0;
  let lastError = null;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await apiRequest(baseUrl, accessTokenOrResolver, path, options);
    } catch (error) {
      lastError = error;
      if (attempt >= maxRetries || !_isLegacyRetryableError(error)) {
        throw error;
      }
      const delay = Math.min(initialDelayMs * Math.pow(2, attempt), 15000);
      if (totalDelay + delay > LEGACY_MAX_TOTAL_RETRY_DELAY_MS) {
        throw error;
      }
      totalDelay += delay;
      await new Promise((resolve) => window.setTimeout(resolve, delay));
    }
  }
  throw lastError;
}

function parseJsonText(text) {
  if (!text) {
    return {};
  }
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function nowMs() {
  if (typeof performance !== "undefined" && typeof performance.now === "function") {
    return performance.now();
  }
  return Date.now();
}

export function diagnosticPathShape(path) {
  const rawPath = String(path || "").split("?")[0] || "/";
  return rawPath
    .replace(/\/runs\/[^/]+/g, "/runs/:run_id")
    .replace(/\/workspaces\/[^/]+/g, "/workspaces/:workspace_id")
    .replace(/\/documents\/[^/]+/g, "/documents/:document_id")
    .replace(/\/artifacts\/[^/]+/g, "/artifacts/:artifact_id")
    .replace(/\/by-id\/[^/]+/g, "/by-id/:id")
    .replace(/\/[a-z0-9_-]{32,}(?=\/|$)/gi, "/:id")
    .replace(/\/\d{6,}(?=\/|$)/g, "/:id");
}

function emitApiRequestDiagnostic(level, payload) {
  if (typeof console === "undefined") {
    return;
  }
  const log = level === "warn" && typeof console.warn === "function" ? console.warn : console.info;
  if (typeof log !== "function") {
    return;
  }
  log("[runr-api-request]", payload);
}

function shouldPersistApiRequestDiagnostic(payload) {
  const path = String(payload?.path || "");
  return Boolean(path) && path !== "/analytics/events";
}

function persistApiRequestDiagnostic(baseUrl, accessToken, payload) {
  if (!shouldPersistApiRequestDiagnostic(payload) || !accessToken || typeof fetch !== "function") {
    return;
  }
  const eventName =
    payload.event === "api_request_failed"
      ? "frontend_api_request_failed"
      : "frontend_api_request_slow";
  const body = JSON.stringify({
    event_name: eventName,
    route: String(payload.path || ""),
    source: REQUEST_DIAGNOSTIC_SOURCE,
    payload,
  });
  const headers = {
    Authorization: `Bearer ${accessToken}`,
    "Content-Type": "application/json",
  };
  try {
    fetch(resolveApiUrl(baseUrl, "/analytics/events"), {
      method: "POST",
      headers,
      body,
      keepalive: body.length < 60000,
    }).catch(() => {});
  } catch {
    // Diagnostics must never change the behavior of the original request.
  }
}

function recordApiRequestDiagnostic(level, baseUrl, accessToken, payload) {
  emitApiRequestDiagnostic(level, payload);
  persistApiRequestDiagnostic(baseUrl, accessToken, payload);
}

function normalizeResponseErrorPayload(payload, fallbackMessage) {
  if (!payload || typeof payload !== "object") {
    return {
      message: fallbackMessage,
      code: "",
      details: null,
    };
  }
  if (typeof payload.error === "string") {
    return {
      message: String(payload.message || payload.error || fallbackMessage),
      code: String(payload.error || "").trim(),
      details: payload,
    };
  }
  if (payload.error && typeof payload.error === "object") {
    return {
      message: String(payload.error.message || fallbackMessage),
      code: String(payload.error.code || "").trim(),
      details: payload.error.details || null,
    };
  }
  return {
    message: fallbackMessage,
    code: "",
    details: payload.details || null,
  };
}

async function resolveAccessToken(accessTokenOrResolver) {
  if (typeof accessTokenOrResolver === "function") {
    return String(await accessTokenOrResolver()).trim();
  }
  return String(await Promise.resolve(accessTokenOrResolver || "")).trim();
}

function emitQuotaExceeded(detail) {
  if (typeof window === "undefined") {
    return;
  }
  window.dispatchEvent(new CustomEvent(QUOTA_EXCEEDED_EVENT, { detail }));
}

export function getApiErrorMessage(error, fallbackMessage = "Request failed.") {
  return String(error?.message || fallbackMessage);
}

function dedupeMessages(messages) {
  const seen = new Set();
  return messages.filter((message) => {
    const normalized = String(message || "").trim();
    if (!normalized || seen.has(normalized)) {
      return false;
    }
    seen.add(normalized);
    return true;
  });
}

function formatValidationFieldError(item) {
  if (!item || typeof item !== "object") {
    return "";
  }
  const message = String(item.message || "").trim();
  if (!message) {
    return "";
  }
  const sourceId = String(item.source_id || "").trim();
  const field = String(item.field || "").trim();
  const segments = [];
  if (sourceId) {
    segments.push(labelize(sourceId));
  }
  if (field) {
    segments.push(labelize(field));
  }
  return segments.length ? `${segments.join(" | ")}: ${message}` : message;
}

function formatValidationSourceResult(item) {
  if (!item || typeof item !== "object" || String(item.status || "").trim() === "valid") {
    return [];
  }
  const sourceLabel = labelize(item.source_id || "source");
  const details = Array.isArray(item.details)
    ? item.details.map((detail) => String(detail || "").trim()).filter(Boolean)
    : [];
  if (details.length) {
    return details.map((detail) => `${sourceLabel}: ${detail}`);
  }
  const summary = String(item.summary || "").trim();
  return summary ? [`${sourceLabel}: ${summary}`] : [];
}

export function getApiErrorDetails(error) {
  const details = error?.details;
  if (Array.isArray(details)) {
    return details.map((item) => String(item || "").trim()).filter(Boolean);
  }
  if (typeof details === "string") {
    return details.trim() ? [details.trim()] : [];
  }
  if (!details || typeof details !== "object") {
    return [];
  }
  if (Array.isArray(details.field_errors) || Array.isArray(details.source_results)) {
    return dedupeMessages([
      ...(Array.isArray(details.field_errors) ? details.field_errors.map(formatValidationFieldError) : []),
      ...(Array.isArray(details.source_results)
        ? details.source_results.flatMap((item) => formatValidationSourceResult(item))
        : []),
    ]);
  }
  return Object.entries(details)
    .map(([key, value]) => {
      if (value === undefined || value === null || value === "") {
        return "";
      }
      if (typeof value === "string") {
        return `${key}: ${value}`;
      }
      return `${key}: ${JSON.stringify(value)}`;
    })
    .filter(Boolean);
}

function buildApiError(response, payload, fallbackText) {
  const normalized = normalizeResponseErrorPayload(
    payload,
    fallbackText || `${response.status} ${response.statusText}`,
  );
  const error = new Error(normalized.message);
  error.status = response.status;
  error.code = normalized.code;
  error.details = normalized.details;
  error.payload = payload;
  if (response.status === 402 && payload?.error === "quota_exceeded") {
    emitQuotaExceeded({
      quota_type: String(payload.quota_type || "").trim(),
      used: Number(payload.used || 0),
      limit: Number(payload.limit || 0),
      plan_id: String(payload.plan_id || "").trim(),
      upgrade_url: String(payload.upgrade_url || "/pricing").trim() || "/pricing",
    });
  }
  return error;
}

// --- Bounded retry with exponential backoff ---

const RETRYABLE_STATUS_CODES = new Set([408, 429, 502, 503, 504]);

/** Maximum total backoff delay across all retries (ms). */
const MAX_TOTAL_RETRY_DELAY_MS = 30000;

function _isRetryableError(error) {
  if (!error || error.name === "AbortError") {
    return false;
  }
  const status = Number(error?.status || 0);
  if (status > 0 && RETRYABLE_STATUS_CODES.has(status)) {
    return true;
  }
  // Network errors (TypeError from fetch when offline/DNS fails)
  if (error instanceof TypeError && /network|fetch/i.test(String(error.message || ""))) {
    return true;
  }
  return false;
}

/**
 * Wrap apiRequest with bounded retries and exponential backoff.
 *
 * Options (on top of apiRequest options):
 *   maxRetries  – max number of retry attempts (default 2, max 5).
 *   retryDelayMs – initial backoff in ms (default 1000).
 */
export async function apiRequestWithRetry(baseUrl, accessTokenOrResolver, path, options = {}) {
  const maxRetries = Math.min(5, Math.max(0, Number(options.maxRetries ?? 2)));
  const initialDelayMs = Math.max(500, Number(options.retryDelayMs ?? 1000));
  let totalDelay = 0;
  let lastError = null;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await apiRequest(baseUrl, accessTokenOrResolver, path, options);
    } catch (error) {
      lastError = error;
      if (attempt >= maxRetries || !_isRetryableError(error)) {
        throw error;
      }
      const delay = Math.min(initialDelayMs * Math.pow(2, attempt), 15000);
      if (totalDelay + delay > MAX_TOTAL_RETRY_DELAY_MS) {
        throw error;
      }
      totalDelay += delay;
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }
  throw lastError;
}

export async function apiRequest(baseUrl, accessTokenOrResolver, path, options = {}) {
  const {
    method = "GET",
    body,
    headers = {},
    responseType = "json",
    timeoutMs = 0,
    signal,
  } = options;
  const resolvedAccessToken = await resolveAccessToken(accessTokenOrResolver);
  const requestHeaders = {
    ...headers,
  };
  if (resolvedAccessToken) {
    requestHeaders.Authorization = `Bearer ${resolvedAccessToken}`;
  }
  let requestBody = body;
  if (body !== undefined && body !== null && !(body instanceof FormData) && responseType !== "blob") {
    requestHeaders["Content-Type"] = "application/json";
    requestBody = JSON.stringify(body);
  }
  const controller = timeoutMs > 0 ? new AbortController() : null;
  let timeoutId = null;
  if (controller) {
    timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  }
  if (signal && controller) {
    if (signal.aborted) {
      controller.abort();
    } else {
      signal.addEventListener("abort", () => controller.abort(), { once: true });
    }
  }
  const requestStartedAt = nowMs();
  let responseStatus = 0;
  try {
    const response = await fetch(resolveApiUrl(baseUrl, path), {
      method,
      headers: requestHeaders,
      body: requestBody,
      signal: controller?.signal || signal,
    });
    responseStatus = response.status;
    if (responseType === "blob") {
      if (!response.ok) {
        const text = await response.text();
        const payload = parseJsonText(text);
        throw buildApiError(response, payload, text);
      }
      const blob = await response.blob();
      const durationMs = Math.round(nowMs() - requestStartedAt);
      if (durationMs >= SLOW_REQUEST_THRESHOLD_MS) {
        recordApiRequestDiagnostic("info", baseUrl, resolvedAccessToken, {
          event: "api_request_slow",
          method,
          path: diagnosticPathShape(path),
          status: responseStatus,
          duration_ms: durationMs,
          response_type: "blob",
        });
      }
      return blob;
    }
    const text = await response.text();
    const payload = parseJsonText(text);
    if (!response.ok) {
      throw buildApiError(response, payload, text);
    }
    const durationMs = Math.round(nowMs() - requestStartedAt);
    if (durationMs >= SLOW_REQUEST_THRESHOLD_MS) {
      recordApiRequestDiagnostic("info", baseUrl, resolvedAccessToken, {
        event: "api_request_slow",
        method,
        path: diagnosticPathShape(path),
        status: responseStatus,
        duration_ms: durationMs,
        response_type: "json",
      });
    }
    return payload || {};
  } catch (error) {
    const durationMs = Math.round(nowMs() - requestStartedAt);
    recordApiRequestDiagnostic("warn", baseUrl, resolvedAccessToken, {
      event: "api_request_failed",
      method,
      path: diagnosticPathShape(path),
      status: Number(error?.status || responseStatus || 0),
      duration_ms: durationMs,
      timeout_ms: Number(timeoutMs || 0),
      error_name: String(error?.name || "Error"),
      error_code: String(error?.code || ""),
      aborted: Boolean(error?.name === "AbortError"),
    });
    if (error?.name === "AbortError" && timeoutMs > 0) {
      throw new Error(`Request timed out after ${Math.round(timeoutMs / 1000)} seconds.`);
    }
    throw error;
  } finally {
    if (timeoutId) {
      window.clearTimeout(timeoutId);
    }
  }
}
