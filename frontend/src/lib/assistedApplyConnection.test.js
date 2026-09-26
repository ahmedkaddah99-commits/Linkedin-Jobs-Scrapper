import assert from "node:assert/strict";
import test from "node:test";

import {
  assistedApplyConnectionPath,
  assistedApplyConnectionRequestActionPath,
  buildAssistedApplyPreferencesPayload,
  normalizeAssistedApplyConnectionPayload,
  normalizeBackendCompletionUrl,
  parseAssistedApplyConnectionSearch,
} from "./assistedApplyConnection.js";

test("connection search accepts only an opaque request_id and ignores callback inputs", () => {
  assert.deepEqual(
    parseAssistedApplyConnectionSearch(
      "?request_id=request_ABC-123&redirect_uri=https://evil.example&user_id=other&token=secret",
    ),
    { requestId: "request_ABC-123", invalidRequestId: false },
  );
  assert.deepEqual(parseAssistedApplyConnectionSearch("?request_id=https://evil.example/a"), {
    requestId: "",
    invalidRequestId: true,
  });
  assert.deepEqual(parseAssistedApplyConnectionSearch("?redirect_uri=https://evil.example"), {
    requestId: "",
    invalidRequestId: false,
  });
});

test("sensitive preferences default off and legal confirmation cannot be disabled", () => {
  assert.deepEqual(buildAssistedApplyPreferencesPayload({}), {
    permit_sensitive_autofill: false,
    permit_demographic_autofill: false,
    require_legal_answer_confirmation: true,
  });
  assert.deepEqual(
    buildAssistedApplyPreferencesPayload({
      permit_sensitive_autofill: true,
      permit_demographic_autofill: true,
      require_legal_answer_confirmation: false,
      password: "must-not-leak",
      token: "must-not-leak",
    }),
    {
      permit_sensitive_autofill: true,
      permit_demographic_autofill: true,
      require_legal_answer_confirmation: true,
    },
  );
});

test("connection state accepts the backend request record and terminal states", () => {
  const pending = normalizeAssistedApplyConnectionPayload(
    {
      request_id: "request_12345678",
      status: "pending",
      extension_version: "1.0.0",
      request_expires_at: "2026-07-17T12:10:00Z",
      preferences: {},
    },
    { requestId: "request_12345678" },
  );
  assert.equal(pending.state, "pending");
  assert.equal(pending.pending_request.client_label, "1.0.0");
  assert.equal(pending.pending_request.expires_at, "2026-07-17T12:10:00Z");
  assert.equal(pending.preferences.permit_sensitive_autofill, false);
  assert.equal(pending.preferences.permit_demographic_autofill, false);
  assert.equal(pending.preferences.require_legal_answer_confirmation, true);

  assert.equal(
    normalizeAssistedApplyConnectionPayload(
      { request_id: "request_12345678", status: "active" },
      { requestId: "request_12345678" },
    ).state,
    "connected",
  );

  assert.equal(
    normalizeAssistedApplyConnectionPayload(
      { request_state: "expired" },
      { requestId: "request_12345678" },
    ).state,
    "expired",
  );
  assert.equal(
    normalizeAssistedApplyConnectionPayload(
      { request_state: "revoked" },
      { requestId: "request_12345678" },
    ).state,
    "revoked",
  );
});

test("request paths accept only normalized backend identifiers", () => {
  assert.equal(
    assistedApplyConnectionPath("request_ABC-123"),
    "/assisted-apply/connection?request_id=request_ABC-123",
  );
  assert.equal(
    assistedApplyConnectionRequestActionPath("request_ABC-123", "approve"),
    "/assisted-apply/connection-requests/request_ABC-123/approve",
  );
  assert.throws(() =>
    assistedApplyConnectionRequestActionPath("request_ABC-123", "redirect"),
  );
});

test("completion redirects accept only the exact Chromium identity callback", () => {
  const extensionId = "abcdefghijklmnopabcdefghijklmnop";
  assert.equal(
    normalizeBackendCompletionUrl(
      `https://${extensionId}.chromiumapp.org/runr/connect?code=once&state=opaque`,
    ),
    `https://${extensionId}.chromiumapp.org/runr/connect?code=once&state=opaque`,
  );
  assert.equal(normalizeBackendCompletionUrl("javascript:alert(1)"), "");
  assert.equal(
    normalizeBackendCompletionUrl(`https://${extensionId}.chromiumapp.org.evil.example/runr/connect`),
    "",
  );
  assert.equal(
    normalizeBackendCompletionUrl(
      `https://${extensionId}.chromiumapp.org@evil.example/runr/connect`,
    ),
    "",
  );
  assert.equal(
    normalizeBackendCompletionUrl(`https://${extensionId}.chromiumapp.org:444/runr/connect`),
    "",
  );
  assert.equal(
    normalizeBackendCompletionUrl(`https://${extensionId}.chromiumapp.org:443/runr/connect`),
    "",
  );
  assert.equal(
    normalizeBackendCompletionUrl(`https://${extensionId}.chromiumapp.org/callback`),
    "",
  );
});
