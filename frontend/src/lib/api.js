import { labelize } from "./formatters";

const STORAGE_KEYS = {
  baseUrl: "runr.api.baseUrl",
};

// This must match the Clerk JWT Template name configured in the Clerk dashboard.
export const CLERK_JWT_TEMPLATE_NAME = "runr_backend";

export const QUOTA_EXCEEDED_EVENT = "runr:quota-exceeded";

export function getDefaultApiBaseUrl() {
  return String(import.meta.env.VITE_API_BASE_URL || "/v1").replace(/\/$/, "");
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
  const normalizedBase = String(baseUrl || getDefaultApiBaseUrl()).replace(/\/$/, "");
  const normalizedPath = String(path || "").trim();
  if (/^https?:\/\//i.test(normalizedPath)) {
    return normalizedPath;
  }
  if (normalizedPath.startsWith("/")) {
    if (/^https?:\/\//i.test(normalizedBase)) {
      const base = new URL(normalizedBase);
      return `${base.origin}${normalizedPath}`;
    }
    return normalizedPath;
  }
  return `${normalizedBase}/${normalizedPath.replace(/^\//, "")}`;
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

export async function apiRequest(baseUrl, accessTokenOrResolver, path, options = {}) {
  const {
    method = "GET",
    body,
    headers = {},
    responseType = "json",
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
  const response = await fetch(resolveApiUrl(baseUrl, path), {
    method,
    headers: requestHeaders,
    body: requestBody,
  });
  if (responseType === "blob") {
    if (!response.ok) {
      const text = await response.text();
      const payload = parseJsonText(text);
      throw buildApiError(response, payload, text);
    }
    return response.blob();
  }
  const text = await response.text();
  const payload = parseJsonText(text);
  if (!response.ok) {
    throw buildApiError(response, payload, text);
  }
  return payload || {};
}
