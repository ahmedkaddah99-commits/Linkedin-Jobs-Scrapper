import assert from "node:assert/strict";
import test from "node:test";
import {
  ASSISTED_APPLY_PREPARATION_EXTENSION_ID,
  isAssistedApplyPreparationEnabled,
  normalizePreparationStatus,
  preparationUiModel,
  sendAssistedApplyPreparationCommand,
} from "./assistedApplyPreparation.js";

const ids = { preparationId: "aaprep_12345678", packageId: "aapkg_12345678" };

test("feature flag is disabled by default and enabled explicitly", () => {
  assert.equal(isAssistedApplyPreparationEnabled({}), false);
  assert.equal(isAssistedApplyPreparationEnabled({ VITE_ENABLE_ASSISTED_APPLY_PREPARATION: "true" }), true);
  assert.equal(isAssistedApplyPreparationEnabled({ VITE_ENABLE_ASSISTED_APPLY_PREPARATION: "1" }), false);
});

test("sends validated start, review, cancel, and retry commands with identity only", async () => {
  const messages = [];
  const runtime = {
    sendMessage(extensionId, message, callback) {
      messages.push({ extensionId, message });
      callback({ ok: true, status: "accepted" });
    },
  };
  await sendAssistedApplyPreparationCommand({ ...ids, ats: "greenhouse", type: "start", runtime });
  await sendAssistedApplyPreparationCommand({ ...ids, ats: "greenhouse", type: "review_activate", runtime });
  await sendAssistedApplyPreparationCommand({ ...ids, ats: "greenhouse", type: "cancel", runtime });
  await sendAssistedApplyPreparationCommand({ ...ids, ats: "greenhouse", type: "retry", retryOf: ids.preparationId, runtime });
  assert.equal(messages.every((entry) => entry.extensionId === ASSISTED_APPLY_PREPARATION_EXTENSION_ID), true);
  assert.equal(messages.every((entry) => !("tabId" in entry.message) && !("windowId" in entry.message)), true);
  assert.deepEqual(messages[0].message.capabilities.adapters, ["greenhouse"]);
  assert.equal(messages[1].message.reviewId, ids.preparationId);
  assert.equal(messages[2].message.reason, "user_requested");
  assert.equal(messages[3].message.retryOf, ids.preparationId);
});

test("missing extension, permission denial, and expired state remain explicit", async () => {
  await assert.rejects(
    sendAssistedApplyPreparationCommand({ ...ids, type: "start", runtime: null }),
    /Install and connect/,
  );
  await assert.rejects(
    sendAssistedApplyPreparationCommand({ ...ids, type: "start", runtime: {
      sendMessage(_id, _message, callback) { callback({ ok: false, status: "permission_required", error: "permission required" }); },
    } }),
    (error) => error.status === "permission_required",
  );
  assert.equal(normalizePreparationStatus({ state: "expired", error_category: "expired" }).state, "expired");
  assert.equal(normalizePreparationStatus({ state: "future_state" }).state, "needs_attention");
});

test("rejects malformed preparation identity before contacting the extension", async () => {
  let called = false;
  await assert.rejects(
    sendAssistedApplyPreparationCommand({ preparationId: "short", packageId: ids.packageId, type: "start", runtime: {
      sendMessage() { called = true; },
    } }),
    /Preparation identity is invalid/,
  );
  assert.equal(called, false);
});

test("maps durable states to explicit component actions without a submission action", () => {
  const ready = preparationUiModel({ state: "ready_for_review", total_count: 4, completed_count: 3 });
  assert.deepEqual(ready, { state: "ready_for_review", filled: 3, unresolved: 1, permissionRequired: false, expired: false, canReview: true, canRetry: false, canCancel: true });
  const attention = preparationUiModel({ state: "needs_attention", total_count: 2, completed_count: 0 });
  assert.equal(attention.canRetry, true);
  assert.equal(attention.canCancel, true);
  assert.equal("submitted" in attention, false);
});
