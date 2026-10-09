import assert from "node:assert/strict";
import test from "node:test";
import {
  RUNR_ASSISTED_APPLY_EXTENSION_ID,
  bindRunrApplicationPackage,
} from "./assistedApplyLaunch.js";

test("binds an opaque launch envelope through only the reserved Runr extension", async () => {
  let captured = null;
  const runtime = {
    sendMessage(extensionId, message, callback) {
      captured = { extensionId, message };
      callback({ ok: true, packageId: "aapkg_test_1" });
    },
  };
  await assert.doesNotReject(() => bindRunrApplicationPackage({
    bindingId: "aapkg_bind_abcdefghijklmnopqrstuvwxyz",
    applicationUrl: "https://boards.greenhouse.io/acme/jobs/1",
    runtime,
  }));
  assert.equal(captured.extensionId, RUNR_ASSISTED_APPLY_EXTENSION_ID);
  assert.deepEqual(captured.message, {
    type: "RUNR_WEB_BIND_APPLICATION_PACKAGE",
    bindingId: "aapkg_bind_abcdefghijklmnopqrstuvwxyz",
    applicationUrl: "https://boards.greenhouse.io/acme/jobs/1",
  });
});

test("does not treat a missing extension or rejected bridge as a successful launch", async () => {
  await assert.rejects(
    bindRunrApplicationPackage({ bindingId: "binding", applicationUrl: "https://jobs.lever.co/acme/1", runtime: null }),
    /Install and connect/,
  );
  const runtime = {
    sendMessage(_extensionId, _message, callback) {
      callback({ ok: false, error: "The application tab was not found." });
    },
  };
  await assert.rejects(
    bindRunrApplicationPackage({ bindingId: "binding", applicationUrl: "https://jobs.lever.co/acme/1", runtime }),
    /application tab was not found/,
  );
});
