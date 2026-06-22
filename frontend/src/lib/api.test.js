import assert from "node:assert/strict";
import test from "node:test";

import { apiRequest, diagnosticPathShape, resolveApiUrl } from "./api.js";

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
