import test from "node:test";
import assert from "node:assert/strict";
import { billingMessage, billingFeatures } from "./billingPresentation.js";

test("provider and configuration errors never appear in billing UI", () => {
  for (const message of ["Creem API error: secret", "product_id not configured", "Missing API_KEY", "Invalid redirect signature", "provider returned https://example.com"])
    assert.equal(billingMessage(new Error(message)), "Payments are temporarily unavailable. Please try again later.");
  assert.equal(billingMessage(new Error("Checkout temporarily unavailable")), "Checkout temporarily unavailable");
});
test("comparison omits retired runs, credits and workspace concepts", () => {
  assert.deepEqual(billingFeatures([]).map(row => row.label), ["AI Resume Customization", "AI Cover Letter", "Application Autofill", "Referral Drafts"]);
});
