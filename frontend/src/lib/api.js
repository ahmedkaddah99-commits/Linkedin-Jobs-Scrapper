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
      try {
        const payload = await response.json();
        message = payload?.error?.message || message;
      } catch {
        // ignore blob/json parsing errors on download failures
      }
      throw new Error(message);
    }
    return response.blob();
  }
  const text = await response.text();
  const payload = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw new Error(payload?.error?.message || `${response.status} ${response.statusText}`);
  }
  return payload;
}
