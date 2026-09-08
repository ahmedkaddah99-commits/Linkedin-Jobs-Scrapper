import assert from "node:assert/strict";
import test from "node:test";

import { apiRequest, apiRequestWithRetry, cancelAllDedupedRequests, createDedupedAbortController, diagnosticPathShape, resolveApiUrl, resolveDefaultApiBaseUrl, settleDedupedAbortController } from "./api.js";

test("uses explicit API base URL before Render-generated hostnames", () => {
  assert.equal(
    resolveDefaultApiBaseUrl({
      VITE_API_BASE_URL: "https://api.example.com/v1/",
      VITE_API_EXTERNAL_HOSTNAME: "preview-api.onrender.com",
    }),
    "https://api.example.com/v1",
  );
});

test("derives the API base URL from Render preview hostnames", () => {
  assert.equal(
    resolveDefaultApiBaseUrl({
      VITE_API_EXTERNAL_HOSTNAME: "preview-api.onrender.com",
    }),
    "https://preview-api.onrender.com/v1",
  );
});

test("rejects an injective placeholder like $ {n} and falls back to external hostname", () => {
  assert.equal(
    resolveDefaultApiBaseUrl({
      VITE_API_BASE_URL: "${n}",
      VITE_API_EXTERNAL_HOSTNAME: "runr-api.onrender.com",
    }),
    "https://runr-api.onrender.com/v1",
  );
});

test("rejects a bare Vite placeholder like $ {VITE_API_BASE_URL} and falls back to /v1", () => {
  assert.equal(
    resolveDefaultApiBaseUrl({
      VITE_API_BASE_URL: "${VITE_API_BASE_URL}",
    }),
    "/v1",
  );
});

test("rejects an empty VITE_API_BASE_URL and uses external hostname", () => {
  assert.equal(
    resolveDefaultApiBaseUrl({
      VITE_API_BASE_URL: "",
      VITE_API_EXTERNAL_HOSTNAME: "prod-api.onrender.com",
    }),
    "https://prod-api.onrender.com/v1",
  );
});

test("rejects a whitespace-only VITE_API_BASE_URL as a placeholder", () => {
  assert.equal(
    resolveDefaultApiBaseUrl({
      VITE_API_BASE_URL: "   ",
    }),
    "/v1",
  );
});

test("preserves an absolute API base path for a leading-slash request path", () => {
  assert.equal(
    resolveApiUrl("https://api.example.com/v1", "/auth/me"),
    "https://api.example.com/v1/auth/me",
  );
});

test("normalizes repeated boundary slashes", () => {
  assert.equal(
    resolveApiUrl("https://api.example.com/v1///", "///workspaces"),
    "https://api.example.com/v1/workspaces",
  );
});

test("preserves a relative API base path", () => {
  assert.equal(resolveApiUrl("/v1", "/health"), "/v1/health");
});

test("allows a fully qualified request URL to override the configured base", () => {
  assert.equal(
    resolveApiUrl("https://api.example.com/v1", "https://downloads.example.com/file.pdf"),
    "https://downloads.example.com/file.pdf",
  );
});

test("does not attach the API bearer token to a signed object URL", async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url: String(url), options });
    return new Response("pdf", {
      status: 200,
      headers: { "Content-Type": "application/pdf" },
    });
  };

  try {
    const blob = await apiRequest(
      "https://api.example.com/v1",
      async () => "test-token",
      "https://downloads.example.com/private/cv.pdf?signature=test",
      { responseType: "blob" },
    );
    assert.equal(blob.size, 3);
    assert.equal(calls[0].url, "https://downloads.example.com/private/cv.pdf?signature=test");
    assert.equal(calls[0].options.headers.Authorization, undefined);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("redacts request diagnostics paths", () => {
  assert.equal(
    diagnosticPathShape("/runs/run_224f21ab5bc14f92/jobs/by-id/4431179712?debug=1"),
    "/runs/:run_id/jobs/by-id/:id",
  );
  assert.equal(
    diagnosticPathShape("/artifacts/2f8b5fa3d3e94ea8844a71b95b0d8d4f/download"),
    "/artifacts/:artifact_id/download",
  );
});

test("persists failed request diagnostics without using apiRequest recursively", async () => {
  const originalFetch = globalThis.fetch;
  const originalConsoleWarn = console.warn;
  const calls = [];
  console.warn = () => {};
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url: String(url), options });
    if (calls.length === 1) {
      return new Response(JSON.stringify({ error: { message: "Backend failed", code: "internal_error" } }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(JSON.stringify({ status: "ok" }), {
      status: 202,
      headers: { "Content-Type": "application/json" },
    });
  };

  try {
    await assert.rejects(
      apiRequest(
        "https://api.example.com/v1",
        async () => "test-token",
        "/runs/run_224f21ab5bc14f92/customer-view",
      ),
      /Backend failed/,
    );
    assert.equal(calls.length, 2);
    assert.equal(calls[1].url, "https://api.example.com/v1/analytics/events");
    assert.equal(calls[1].options.method, "POST");
    assert.equal(calls[1].options.headers.Authorization, "Bearer test-token");
    const diagnosticPayload = JSON.parse(calls[1].options.body);
    assert.equal(diagnosticPayload.event_name, "frontend_api_request_failed");
    assert.equal(diagnosticPayload.route, "/runs/:run_id/customer-view");
    assert.equal(diagnosticPayload.source, "frontend_api_request_diagnostic");
    assert.equal(diagnosticPayload.payload.status, 500);
    assert.equal(diagnosticPayload.payload.error_code, "internal_error");
  } finally {
    globalThis.fetch = originalFetch;
    console.warn = originalConsoleWarn;
  }
});

test("rejects placeholder API base URLs", () => {
  assert.equal(
    resolveDefaultApiBaseUrl({ VITE_API_BASE_URL: "${VITE_API_BASE_URL}" }),
    "/v1",
  );
  assert.equal(
    resolveDefaultApiBaseUrl({ VITE_API_BASE_URL: "  ${VITE_API_BASE_URL}  " }),
    "/v1",
  );
  assert.equal(
    resolveDefaultApiBaseUrl({ VITE_API_BASE_URL: "" }),
    "/v1",
  );
});

test("accepts a valid relative API base URL", () => {
  assert.equal(
    resolveDefaultApiBaseUrl({ VITE_API_BASE_URL: "/v1" }),
    "/v1",
  );
});

test("accepts a valid absolute API base URL", () => {
  assert.equal(
    resolveDefaultApiBaseUrl({ VITE_API_BASE_URL: "https://api.example.com/v1" }),
    "https://api.example.com/v1",
  );
});

test("deduped abort controller cancels previous in-flight request", () => {
  const controller1 = createDedupedAbortController("GET", "/tracker");
  assert.equal(controller1.signal.aborted, false);
  const controller2 = createDedupedAbortController("GET", "/tracker");
  assert.equal(controller1.signal.aborted, true);
  assert.equal(controller2.signal.aborted, false);
  settleDedupedAbortController(controller2);
});

test("settleDedupedAbortController removes from in-flight map", () => {
  const controller = createDedupedAbortController("POST", "/runs");
  settleDedupedAbortController(controller);
  const controller2 = createDedupedAbortController("POST", "/runs");
  assert.equal(controller2.signal.aborted, false);
  settleDedupedAbortController(controller2);
});

test("cancelAllDedupedRequests aborts all tracked controllers", () => {
  const c1 = createDedupedAbortController("GET", "/a");
  const c2 = createDedupedAbortController("GET", "/b");
  cancelAllDedupedRequests();
  assert.equal(c1.signal.aborted, true);
  assert.equal(c2.signal.aborted, true);
});

test("apiRequestWithRetry succeeds on first attempt", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  try {
    const result = await apiRequestWithRetry(
      "https://api.example.com/v1",
      "token",
      "/test",
    );
    assert.deepEqual(result, { ok: true });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("apiRequestWithRetry retries on 503 and succeeds", async () => {
  const originalFetch = globalThis.fetch;
  let callCount = 0;
  globalThis.fetch = async () => {
    callCount++;
    if (callCount === 1) {
      return new Response(JSON.stringify({ error: "unavailable" }), {
        status: 503,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  try {
    const result = await apiRequestWithRetry(
      "https://api.example.com/v1",
      "token",
      "/test",
      { retryDelayMs: 10 },
    );
    assert.ok(callCount >= 2, `expected callCount >= 2, got ${callCount}`);
    assert.deepEqual(result, { ok: true });
  } finally {
    globalThis.fetch = originalFetch;
  }
});
