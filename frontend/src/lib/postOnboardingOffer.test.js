import assert from "node:assert/strict";
import test from "node:test";
import {
  getNotificationCopy,
  getOfferEligibility,
  getPersonalValueSummary,
  getPlanPriceLabel,
  isPaidPlan,
} from "./postOnboardingOffer.js";

test("the offer requires completed onboarding and an eligible unclaimed state", () => {
  const offerState = { eligible: true, offerShown: false, offerDismissed: false, upgradeCtaSelected: false };
  assert.equal(getOfferEligibility({ onboardingState: { completed: false }, offerState, planId: "free" }), false);
  assert.equal(getOfferEligibility({ onboardingState: { completed: true }, offerState, planId: "free" }), true);
  assert.equal(getOfferEligibility({ onboardingState: { completed: true }, offerState: { ...offerState, offerShown: true }, planId: "free" }), false);
  assert.equal(getOfferEligibility({ onboardingState: { completed: true }, offerState, planId: "runr_pro" }), false);
});

test("personal value copy is deterministic and labels preview data", () => {
  const summary = { totalFound: 1284, strongMatches: 6, hiddenJobs: 148 };
  assert.deepEqual(getNotificationCopy(summary, "synthetic"), {
    title: "Your personalized job search is ready",
    supporting: "1,284 jobs found · 148 unsuitable jobs separated",
    previewLabel: "Preview data",
    mode: "personal_value",
  });
  assert.equal(getPersonalValueSummary(summary, "real").isPreview, false);
});

test("paid plans and billing prices are canonical and provider-backed", () => {
  assert.equal(isPaidPlan("free"), false);
  assert.equal(isPaidPlan("runr_pro"), true);
  assert.equal(isPaidPlan("momentum"), true);
  assert.equal(
    getPlanPriceLabel({
      offers: [
        { display_name: "1 month", price: 39.99 },
        { display_name: "3 months", price: 89.99 },
      ],
    }),
    "USD 39.99 / 1 month · USD 89.99 / 3 months",
  );
  assert.equal(getPlanPriceLabel({}), "Price unavailable");
});
