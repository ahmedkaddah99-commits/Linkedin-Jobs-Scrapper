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
  assert.equal(getOfferEligibility({ onboardingState: { completed: false }, offerState, planId: "none" }), false);
  assert.equal(getOfferEligibility({ onboardingState: { completed: true }, offerState, planId: "none" }), true);
  assert.equal(getOfferEligibility({ onboardingState: { completed: true }, offerState: { ...offerState, offerShown: true }, planId: "none" }), false);
  assert.equal(getOfferEligibility({ onboardingState: { completed: true }, offerState, planId: "momentum" }), false);
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

test("paid plans and billing prices are never invented by the offer helpers", () => {
  assert.equal(isPaidPlan("none"), false);
  assert.equal(isPaidPlan("momentum"), true);
  assert.equal(getPlanPriceLabel({ price_eur: 25 }), "€25 / month");
  assert.equal(getPlanPriceLabel({}), "Price unavailable");
});
