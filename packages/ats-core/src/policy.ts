/**
 * AA-06: Policy decision engine (TypeScript).
 *
 * Must produce **identical** results to ``backend/domain/application_policy.py``
 * for identical ``ProfileValue`` + policy inputs.
 *
 * Shared test fixtures in ``../../tests/fixtures/policy_fixtures.json`` verify
 * cross-language parity.
 */

// ---------------------------------------------------------------------------
// Constants — MUST match Python
// ---------------------------------------------------------------------------

export const SOURCE_PROFILE_VERIFIED = "profile_verified";
export const SOURCE_SCOPED_PREFERENCE = "scoped_preference";
export const SOURCE_AI_SUGGESTION = "ai_suggestion";
export const SOURCE_CONTEXT_DEPENDENT = "context_dependent";

export const ALLOWED_SOURCES = [
  SOURCE_PROFILE_VERIFIED,
  SOURCE_SCOPED_PREFERENCE,
  SOURCE_AI_SUGGESTION,
  SOURCE_CONTEXT_DEPENDENT,
] as const;

export type ProfileSource = (typeof ALLOWED_SOURCES)[number];

export const SENSITIVITY_STANDARD = "standard";
export const SENSITIVITY_PERSONAL = "personal";
export const SENSITIVITY_LEGAL = "legal";
export const SENSITIVITY_DEMOGRAPHIC = "demographic";

export const ALLOWED_SENSITIVITIES = [
  SENSITIVITY_STANDARD,
  SENSITIVITY_PERSONAL,
  SENSITIVITY_LEGAL,
  SENSITIVITY_DEMOGRAPHIC,
] as const;

export type Sensitivity = (typeof ALLOWED_SENSITIVITIES)[number];

export const SCOPE_APPLICATION = "application";
export const SCOPE_COUNTRY = "country";
export const SCOPE_ROLE = "role";
export const SCOPE_COMPANY = "company";
export const SCOPE_GLOBAL = "global";

export const ALLOWED_SCOPES = [
  SCOPE_APPLICATION,
  SCOPE_COUNTRY,
  SCOPE_ROLE,
  SCOPE_COMPANY,
  SCOPE_GLOBAL,
] as const;

export type ProfileScope = (typeof ALLOWED_SCOPES)[number];

export type FieldAction = "fill" | "review" | "manual";

// ---------------------------------------------------------------------------
// ProfileValue — full provenance model
// ---------------------------------------------------------------------------

export interface ProfileValue {
  fieldIntent: string;
  label: string;
  value: string;
  source: ProfileSource;
  sensitivity: Sensitivity;
  scope: ProfileScope;

  /** ISO-8601 or empty. */
  confirmedAt: string;
  /** User ID or "system"; empty if unconfirmed. */
  confirmedBy: string;
  /** ISO-8601 or empty. */
  expiresAt: string;
  freshnessThresholdDays: number;

  /** Empty means "unknown / no constraint". */
  jurisdiction: string;

  /** Human-readable explanation of how this value was obtained. */
  provenance: string;
}

/**
 * Validate a ProfileValue's source/sensitivity pair at runtime.
 *
 * Throws `Error` for invalid combinations (e.g., demographic + ai_suggestion)
 * to match Python's ``ProfileValue._validate_source_sensitivity_pair()``.
 */
export function validateProfileValue(value: ProfileValue): void {
  if (
    value.sensitivity === SENSITIVITY_DEMOGRAPHIC &&
    value.source === SOURCE_AI_SUGGESTION
  ) {
    throw new Error(
      "Demographic answers cannot be sourced from AI suggestions.",
    );
  }
}


// ---------------------------------------------------------------------------
// Policy interface — mirrors ApplicationPackagePolicy fields used by engine
// ---------------------------------------------------------------------------

export interface PolicySettings {
  permitSensitiveAutofill: boolean;
  permitDemographicAutofill: boolean;
  requireLegalAnswerConfirmation: boolean;
  jurisdiction?: string;
}

// ---------------------------------------------------------------------------
// FieldDecision
// ---------------------------------------------------------------------------

export interface FieldDecision {
  action: FieldAction;
  reasons: string[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function parseIsoOrNull(value: string): Date | null {
  if (!value) return null;
  const d = new Date(value);
  return Number.isFinite(d.getTime()) ? d : null;
}

function valueIsExpired(value: ProfileValue, now: Date): boolean {
  const expires = parseIsoOrNull(value.expiresAt);
  if (!expires) return false;
  return now >= expires;
}

function valueIsStale(value: ProfileValue, now: Date): boolean {
  const confirmed = parseIsoOrNull(value.confirmedAt);
  if (!confirmed) return true; // never confirmed → stale
  const ageDays = Math.floor((now.getTime() - confirmed.getTime()) / 86_400_000);
  return ageDays > Math.max(1, value.freshnessThresholdDays);
}

function jurisdictionMismatch(
  value: ProfileValue,
  policy: PolicySettings,
): boolean {
  if (!value.jurisdiction || !policy.jurisdiction) return false;
  return value.jurisdiction.toLowerCase() !== policy.jurisdiction.toLowerCase();
}

// ---------------------------------------------------------------------------
// Scope ranking
// ---------------------------------------------------------------------------

const SCOPE_RANK: Record<string, number> = {
  application: 0,
  country: 1,
  role: 2,
  company: 3,
  global: 4,
};

function scopeInsufficient(value: ProfileValue, requiredScope: string): boolean {
  if (!requiredScope || requiredScope === SCOPE_APPLICATION) return false;
  const vRank = SCOPE_RANK[value.scope] ?? -1;
  const rRank = SCOPE_RANK[requiredScope] ?? -1;
  return vRank < rRank;
}

// ---------------------------------------------------------------------------
// Decision engine — MUST match Python decide_field_action() exactly
// ---------------------------------------------------------------------------

export function decideFieldAction(
  value: ProfileValue,
  policy: PolicySettings,
  now?: Date,
): FieldDecision {
  const reasons: string[] = [];
  const current = now ?? new Date();

  // --- Freshness: explicit expiry ---
  if (valueIsExpired(value, current)) {
    reasons.push(`The value expired at ${value.expiresAt} and cannot be used.`);
    return { action: "manual", reasons };
  }

  // --- Freshness: staleness ---
  if (valueIsStale(value, current)) {
    reasons.push(
      "The value has not been confirmed recently enough for safe auto-fill.",
    );
  }

  // --- Jurisdiction mismatch ---
  if (jurisdictionMismatch(value, policy)) {
    reasons.push(
      `The value jurisdiction '${value.jurisdiction}' differs from the ` +
        `policy jurisdiction '${policy.jurisdiction}'.`,
    );
  }

  // ==========================================================================
  // Decision matrix — source × sensitivity
  // ==========================================================================

  const src = value.source;
  const sens = value.sensitivity;

  // ---- DEMOGRAPHIC ---------------------------------------------------------
  if (sens === SENSITIVITY_DEMOGRAPHIC) {
    if (!policy.permitDemographicAutofill) {
      reasons.push(
        "Demographic answers are not permitted for auto-fill. " +
          "Enable 'permit_demographic_autofill' in settings.",
      );
      return { action: "manual", reasons };
    }
    // When opted in, treat demographic as standard (fall through)
  }

  // ---- LEGAL ---------------------------------------------------------------
  if (sens === SENSITIVITY_LEGAL) {
    if (policy.requireLegalAnswerConfirmation) {
      reasons.push(
        "Legal answers require explicit user confirmation before fill.",
      );
      if (value.confirmedBy) {
        reasons.push(
          `The value was confirmed by ${value.confirmedBy} ` +
            `on ${value.confirmedAt || "an unknown date"}.`,
        );
      }
      return { action: "review", reasons };
    }
  }

  // ---- PERSONAL ------------------------------------------------------------
  if (sens === SENSITIVITY_PERSONAL) {
    if (src === SOURCE_AI_SUGGESTION) {
      reasons.push(
        "Personal info from AI suggestions cannot be auto-filled.",
      );
      return { action: "manual", reasons };
    }

    if (src === SOURCE_SCOPED_PREFERENCE && !policy.permitSensitiveAutofill) {
      reasons.push(
        "Scoped preferences for personal data require " +
          "'permit_sensitive_autofill' to be enabled.",
      );
      return { action: "review", reasons };
    }

    // profile_verified + personal → may fill if fresh
    if (src === SOURCE_PROFILE_VERIFIED) {
      if (valueIsStale(value, current)) {
        reasons.push(
          "Confirmed personal data has aged past the freshness threshold.",
        );
        return { action: "review", reasons };
      }
      if (jurisdictionMismatch(value, policy)) {
        return { action: "review", reasons };
      }
      reasons.push("Verified personal data is fresh and permissible.");
      return { action: "fill", reasons };
    }

    // scoped_preference + personal (with permit_sensitive_autofill) → fill if fresh
    if (src === SOURCE_SCOPED_PREFERENCE && policy.permitSensitiveAutofill) {
      if (valueIsStale(value, current)) {
        reasons.push(
          "Scoped personal preference has aged past the freshness threshold.",
        );
        return { action: "review", reasons };
      }
      if (jurisdictionMismatch(value, policy)) {
        return { action: "review", reasons };
      }
      reasons.push("Scoped personal preference is permitted and fresh.");
      return { action: "fill", reasons };
    }

    // fallback
    reasons.push("Personal data requires review.");
    return { action: "review", reasons };
  }

  // ---- STANDARD (and demographic with opt-in) ------------------------------
  if (sens === SENSITIVITY_STANDARD || sens === SENSITIVITY_DEMOGRAPHIC) {
    if (src === SOURCE_AI_SUGGESTION) {
      reasons.push(
        "AI-suggested values require human review before filling.",
      );
      return { action: "review", reasons };
    }

    if (src === SOURCE_CONTEXT_DEPENDENT) {
      reasons.push(
        "Context-dependent values require human review to confirm " +
          "the appropriate answer for this specific application.",
      );
      return { action: "review", reasons };
    }

    // profile_verified or scoped_preference → may fill
    if (src === SOURCE_PROFILE_VERIFIED || src === SOURCE_SCOPED_PREFERENCE) {
      if (valueIsStale(value, current)) {
        reasons.push(
          "The value has not been confirmed recently. " +
            "Review to verify it is still current.",
        );
        return { action: "review", reasons };
      }
      if (jurisdictionMismatch(value, policy)) {
        return { action: "review", reasons };
      }
      reasons.push(`Verified ${sens} data is current and permissible.`);
      return { action: "fill", reasons };
    }
  }

  // ---- UNKNOWN-REQUIRED (fallback) -----------------------------------------
  reasons.push(
    "The value has an unrecognised source/sensitivity combination and requires manual review.",
  );
  return { action: "manual", reasons };
}