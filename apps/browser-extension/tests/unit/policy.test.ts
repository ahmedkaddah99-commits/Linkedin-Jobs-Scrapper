/**
 * AA-06: Policy decision engine TypeScript tests.
 *
 * Must produce **identical** results to ``tests/test_application_policy.py``
 * for identical fixtures from ``tests/fixtures/policy_fixtures.json``.
 */

import { describe, expect, it } from "vitest";
import {
  decideFieldAction,
  type ProfileValue,
  type PolicySettings,
} from "@runr/ats-core/policy";

// Load fixtures — vitest resolves from project root
// The fixture path is relative to the repo root since vitest runs from apps/browser-extension.
// We read it via a raw fs import or inline the fixtures for portability.
// For maximum compatibility, we import the JSON directly.
// Vitest with node resolution can handle JSON imports directly.
import fixtures from "../../../../tests/fixtures/policy_fixtures.json";

interface FixtureExpected {
  action: string;
  reasons_contain?: string[];
  error_type?: string;
  error_message_contain?: string;
}

interface PolicyFixture {
  id: string;
  description?: string;
  value: Record<string, unknown>;
  policy: {
    permit_sensitive_autofill: boolean;
    permit_demographic_autofill: boolean;
    require_legal_answer_confirmation: boolean;
    jurisdiction?: string;
  };
  expected: FixtureExpected;
  now?: string;
}

function toPolicySettings(raw: PolicyFixture["policy"]): PolicySettings {
  return {
    permitSensitiveAutofill: raw.permit_sensitive_autofill,
    permitDemographicAutofill: raw.permit_demographic_autofill,
    requireLegalAnswerConfirmation: raw.require_legal_answer_confirmation,
    jurisdiction: raw.jurisdiction ?? "",
  };
}

function toProfileValue(raw: Record<string, unknown>): ProfileValue {
  return {
    fieldIntent: (raw.field_intent as string) ?? "",
    label: (raw.label as string) ?? "",
    value: (raw.value as string) ?? "",
    source: raw.source as ProfileValue["source"],
    sensitivity: raw.sensitivity as ProfileValue["sensitivity"],
    scope: raw.scope as ProfileValue["scope"],
    confirmedAt: (raw.confirmed_at as string) ?? "",
    confirmedBy: (raw.confirmed_by as string) ?? "",
    expiresAt: (raw.expires_at as string) ?? "",
    freshnessThresholdDays: (raw.freshness_threshold_days as number) ?? 90,
    jurisdiction: (raw.jurisdiction as string) ?? "",
    provenance: (raw.provenance as string) ?? "",
  };
}

const typedFixtures = fixtures as PolicyFixture[];

describe("AA-06 Policy decision engine — cross-language parity", () => {
  for (const fixture of typedFixtures) {
    const fixtureId = fixture.id;
    const description = fixture.description ?? fixtureId;

    it(`fixture: ${fixtureId} — ${description}`, () => {
      const expected = fixture.expected;

      // Handle validation error cases
      if (expected.action === "error" && expected.error_type === "validation") {
        expect(() => toProfileValue(fixture.value)).toThrow(
          expected.error_message_contain ?? "",
        );
        return;
      }

      const value = toProfileValue(fixture.value);
      const policy = toPolicySettings(fixture.policy);
      const now = fixture.now ? new Date(fixture.now) : undefined;

      const decision = decideFieldAction(value, policy, now);

      expect(decision.action).toBe(expected.action);

      // Check that expected reason fragments are present
      for (const fragment of expected.reasons_contain ?? []) {
        const found = decision.reasons.some((reason: string) => reason.includes(fragment));
        expect(found, `Expected reasons to contain '${fragment}', got: ${JSON.stringify(decision.reasons)}`).toBe(true);
      }
    });
  }
});