import assert from "node:assert/strict";
import test from "node:test";

import {
  configureFirstPartyEventSink,
  logEvent,
  sanitizeFirstPartyProperties,
} from "./analytics.js";

test("first-party analytics allowlists bounded non-sensitive properties", () => {
  const properties = sanitizeFirstPartyProperties({
    route: "/jobs",
    job_id: "canonical_job_1",
    duration_ms: 1250,
    user_id: "must-not-leave-the-browser",
    email: "candidate@example.com",
    description: "candidate-entered text",
    nested: { secret: "no" },
  });

  assert.deepEqual(properties, {
    route: "/jobs",
    job_id: "canonical_job_1",
    duration_ms: 1250,
  });
});

test("logEvent sends one authenticated first-party event and cleanup detaches it", () => {
  const calls = [];
  const cleanup = configureFirstPartyEventSink((path, options) => {
    calls.push({ path, options });
    return Promise.resolve({ status: "ok" });
  });

  logEvent("job_relevant_viewed", {
    route: "/jobs",
    job_id: "canonical_job_1",
    user_id: "auth-derived",
    data_mode: "real",
  });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].path, "/analytics/events");
  assert.equal(calls[0].options.method, "POST");
  assert.deepEqual(calls[0].options.body, {
    event_name: "job_relevant_viewed",
    source: "frontend_first_party",
    route: "/jobs",
    payload: { route: "/jobs", job_id: "canonical_job_1", data_mode: "real" },
  });

  cleanup();
  logEvent("page_view", { route: "/jobs" });
  assert.equal(calls.length, 1);
});
