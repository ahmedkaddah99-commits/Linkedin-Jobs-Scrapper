import test from "node:test";
import assert from "node:assert/strict";
import { matchLabel, matchScore } from "./profileJobMatch.js";

test("unknown scores never render as zero or NaN", () => {
  for (const value of [null, undefined, NaN, "72"]) assert.equal(matchScore(value), "—");
  assert.equal(matchScore(0), "0%");
  assert.equal(matchScore(72), "72%");
});
test("profile setup and preprocessing have distinct states", () => {
  assert.equal(matchLabel({state: "needs_profile"}), "Complete your profile");
  assert.equal(matchLabel({state: "pending"}), "Match being prepared");
  assert.equal(matchLabel({score: null}), "Insufficient information");
});
