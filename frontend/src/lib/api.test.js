import assert from "node:assert/strict";
import test from "node:test";

import { resolveApiUrl } from "./api.js";

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
