import test from "node:test";
import assert from "node:assert/strict";

import { isSupportedAssistedApplyUrl } from "./supportedAssistedApplyUrl.js";

test("only exposes Assisted Apply for HTTPS hosts covered by extension permissions", () => {
  assert.equal(isSupportedAssistedApplyUrl("https://boards.greenhouse.io/acme/jobs/123"), true);
  assert.equal(isSupportedAssistedApplyUrl("https://jobs.lever.co/acme/123"), true);
  assert.equal(isSupportedAssistedApplyUrl("https://hiring.lever.co/acme/123"), true);
  assert.equal(isSupportedAssistedApplyUrl("https://jobs.greenhouse.io/acme/123"), false);
  assert.equal(isSupportedAssistedApplyUrl("http://boards.greenhouse.io/acme/jobs/123"), false);
  assert.equal(isSupportedAssistedApplyUrl("https://example.com/acme/123"), false);
});
