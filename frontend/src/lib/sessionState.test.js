import assert from "node:assert/strict";
import test from "node:test";

import {
  getSessionRefreshErrorState,
  getSessionRefreshStartStatus,
  hasAuthenticatedSession,
} from "./sessionState.js";

test("keeps authenticated app mounted during a session refresh", () => {
  const user = { user_id: "user_123" };

  assert.equal(hasAuthenticatedSession("connecting", user), true);
  assert.equal(getSessionRefreshStartStatus("connected", user), "connected");
});

test("preserves the last authenticated session after a refresh failure", () => {
  const user = { user_id: "user_123" };
  const tokenInfo = { auth_method: "clerk_jwt" };

  assert.deepEqual(
    getSessionRefreshErrorState({
      errorMessage: "temporary auth check failure",
      previousTokenInfo: tokenInfo,
      previousUser: user,
    }),
    {
      error: "temporary auth check failure",
      status: "connected",
      tokenInfo,
      user,
    },
  );
});

test("shows the connection error when no authenticated session has succeeded", () => {
  assert.deepEqual(
    getSessionRefreshErrorState({
      errorMessage: "auth failed",
      previousTokenInfo: null,
      previousUser: null,
    }),
    {
      error: "auth failed",
      status: "error",
      tokenInfo: null,
      user: null,
    },
  );
});
