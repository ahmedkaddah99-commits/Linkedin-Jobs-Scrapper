import { labelize } from "./formatters";

const STORAGE_KEYS = {
  baseUrl: "runr.api.baseUrl",
  accessToken: "runr.api.accessToken",
};

export function getDefaultApiBaseUrl() {
  return String(import.meta.env.VITE_API_BASE_URL || "/v1").replace(/\/$/, "");
}

export function loadStoredConnection() {
  const storedBaseUrl = window.localStorage.getItem(STORAGE_KEYS.baseUrl) || "";
  const storedAccessToken = window.localStorage.getItem(STORAGE_KEYS.accessToken) || "";
  return {
    baseUrl: storedBaseUrl || getDefaultApiBaseUrl(),
    accessToken: storedAccessToken || String(import.meta.env.VITE_RUNR_ACCESS_TOKEN || "").trim(),
  };
}

export function persistConnection({ baseUrl, accessToken }) {
  window.localStorage.setItem(STORAGE_KEYS.baseUrl, String(baseUrl || "").trim() || getDefaultApiBaseUrl());
  window.localStorage.setItem(STORAGE_KEYS.accessToken, String(accessToken || "").trim());
}

export function clearStoredConnection() {
  window.localStorage.removeItem(STORAGE_KEYS.baseUrl);
  window.localStorage.removeItem(STORAGE_KEYS.accessToken);
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

export async function apiRequest(baseUrl, accessToken, path, options = {}) {
  const { method = "GET", body, headers = {}, responseType = "json" } = options;
  const requestHeaders = {
    ...headers,
  };
  if (accessToken) {
    requestHeaders.Authorization = `Bearer ${accessToken}`;
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
      let message = `${response.status} ${response.statusText}`;
      let details = null;
      let code = "";
      let payload = null;
      try {
        payload = await response.json();
        message = payload?.error?.message || message;
        code = payload?.error?.code || "";
        details = payload?.error?.details || null;
      } catch {
        // ignore blob/json parsing errors on download failures
      }
      const error = new Error(message);
      error.status = response.status;
      error.code = code;
      error.details = details;
      error.payload = payload;
      throw error;
    }
    return response.blob();
  }
  const text = await response.text();
  const payload = parseJsonText(text);
  if (!response.ok) {
    const error = new Error(
      payload?.error?.message || text || `${response.status} ${response.statusText}`,
    );
    error.status = response.status;
    error.code = payload?.error?.code || "";
    error.details = payload?.error?.details || null;
    error.payload = payload;
    throw error;
  }
  return payload || {};
}
