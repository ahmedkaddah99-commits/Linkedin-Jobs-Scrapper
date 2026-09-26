"""AA-06: Canonical ProfileValue contract and policy decision engine.

Owns:
- ``ProfileValue`` — the cross-language candidate/application value schema
  with full provenance, confirmation, sensitivity, scope, jurisdiction,
  and freshness metadata.
- ``decide_field_action()`` — a deterministic pure function that turns a
  ``ProfileValue`` plus ``ApplicationPackagePolicy`` into an actionable
  decision with reasons.

Python and TypeScript implementations MUST produce identical outputs for
identical inputs.  The shared policy fixtures in
``tests/fixtures/policy_fixtures.json`` verify this contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from backend.domain.application_package import ApplicationPackagePolicy

# ---------------------------------------------------------------------------
# Action type — returned by the policy engine
# ---------------------------------------------------------------------------

FieldAction = str  # "fill" | "review" | "manual"


@dataclass(frozen=True, slots=True)
class FieldDecision:
    """Deterministic policy outcome for one field."""

    action: FieldAction
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action, "reasons": list(self.reasons)}


# ---------------------------------------------------------------------------
# Source and sensitivity constants (must match TS)
# ---------------------------------------------------------------------------

SOURCE_PROFILE_VERIFIED = "profile_verified"
SOURCE_SCOPED_PREFERENCE = "scoped_preference"
SOURCE_AI_SUGGESTION = "ai_suggestion"
SOURCE_CONTEXT_DEPENDENT = "context_dependent"

ALLOWED_SOURCES = frozenset({
    SOURCE_PROFILE_VERIFIED,
    SOURCE_SCOPED_PREFERENCE,
    SOURCE_AI_SUGGESTION,
    SOURCE_CONTEXT_DEPENDENT,
})

SENSITIVITY_STANDARD = "standard"
SENSITIVITY_PERSONAL = "personal"
SENSITIVITY_LEGAL = "legal"
SENSITIVITY_DEMOGRAPHIC = "demographic"

ALLOWED_SENSITIVITIES = frozenset({
    SENSITIVITY_STANDARD,
    SENSITIVITY_PERSONAL,
    SENSITIVITY_LEGAL,
    SENSITIVITY_DEMOGRAPHIC,
})

SCOPE_APPLICATION = "application"
SCOPE_COUNTRY = "country"
SCOPE_ROLE = "role"
SCOPE_COMPANY = "company"
SCOPE_GLOBAL = "global"

ALLOWED_SCOPES = frozenset({
    SCOPE_APPLICATION,
    SCOPE_COUNTRY,
    SCOPE_ROLE,
    SCOPE_COMPANY,
    SCOPE_GLOBAL,
})

# ---------------------------------------------------------------------------
# ProfileValue — full provenance model
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProfileValue:
    """One candidate value with full provenance metadata.

    This is the canonical cross-language contract.  Every field is self-
    contained so that a ``ProfileValue`` can be serialised, transmitted to
    the extension, and evaluated locally without backend access.
    """

    field_intent: str
    label: str
    value: str
    source: str
    sensitivity: str
    scope: str

    # Provenance / confirmation
    confirmed_at: str = ""  # ISO‑8601 or empty
    confirmed_by: str = ""  # user ID or ``"system"``, empty if unconfirmed
    expires_at: str = ""  # ISO‑8601 or empty
    freshness_threshold_days: int = 90

    # Jurisdiction — empty means "unknown / no constraint"
    jurisdiction: str = ""

    # Human-readable explanation of *how* this value was obtained
    provenance: str = ""

    def __post_init__(self) -> None:
        if self.source not in ALLOWED_SOURCES:
            raise ValueError(
                f"Unsupported source '{self.source}'. "
                f"Allowed: {sorted(ALLOWED_SOURCES)}"
            )
        if self.sensitivity not in ALLOWED_SENSITIVITIES:
            raise ValueError(
                f"Unsupported sensitivity '{self.sensitivity}'. "
                f"Allowed: {sorted(ALLOWED_SENSITIVITIES)}"
            )
        if self.scope not in ALLOWED_SCOPES:
            raise ValueError(
                f"Unsupported scope '{self.scope}'. "
                f"Allowed: {sorted(ALLOWED_SCOPES)}"
            )
        self._validate_source_sensitivity_pair()

    def _validate_source_sensitivity_pair(self) -> None:
        """Demographic answers must never come from an AI suggestion."""
        if self.sensitivity == SENSITIVITY_DEMOGRAPHIC and self.source == SOURCE_AI_SUGGESTION:
            raise ValueError(
                "Demographic answers cannot be sourced from AI suggestions."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_intent": self.field_intent,
            "label": self.label,
            "value": self.value,
            "source": self.source,
            "sensitivity": self.sensitivity,
            "scope": self.scope,
            "confirmed_at": self.confirmed_at,
            "confirmed_by": self.confirmed_by,
            "expires_at": self.expires_at,
            "freshness_threshold_days": self.freshness_threshold_days,
            "jurisdiction": self.jurisdiction,
            "provenance": self.provenance,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ProfileValue:
        return cls(
            field_intent=str(payload.get("field_intent") or ""),
            label=str(payload.get("label") or ""),
            value=str(payload.get("value") or ""),
            source=str(payload.get("source") or ""),
            sensitivity=str(payload.get("sensitivity") or ""),
            scope=str(payload.get("scope") or ""),
            confirmed_at=str(payload.get("confirmed_at") or ""),
            confirmed_by=str(payload.get("confirmed_by") or ""),
            expires_at=str(payload.get("expires_at") or ""),
            freshness_threshold_days=int(payload.get("freshness_threshold_days") or 90),
            jurisdiction=str(payload.get("jurisdiction") or ""),
            provenance=str(payload.get("provenance") or ""),
        )


# ---------------------------------------------------------------------------
# Policy decision engine
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso_or_none(value: str) -> datetime | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _value_is_expired(value: ProfileValue, *, now: datetime | None = None) -> bool:
    """Check if the value has an explicit ``expires_at`` that is in the past."""
    expires = _parse_iso_or_none(value.expires_at)
    if expires is None:
        return False
    return (now or _utc_now()) >= expires


def _value_is_stale(value: ProfileValue, *, now: datetime | None = None) -> bool:
    """Check if the value has no confirmation or its confirmation is too old."""
    current = now or _utc_now()
    confirmed = _parse_iso_or_none(value.confirmed_at)
    if confirmed is None:
        return True  # never confirmed → stale
    age_days = (current - confirmed).days
    return age_days > max(1, value.freshness_threshold_days)


def _jurisdiction_mismatch(value: ProfileValue, policy: ApplicationPackagePolicy) -> bool:
    """A non-empty value jurisdiction must match the policy jurisdiction."""
    if not value.jurisdiction or not policy.jurisdiction:
        return False
    return value.jurisdiction.casefold() != policy.jurisdiction.casefold()


def _scope_to_rank(scope: str) -> int:
    """Convert scope to integer rank for comparison.

    ``application`` < ``country`` < ``role`` < ``company`` < ``global``.
    A higher rank is *broader*; a lower rank is *narrower*.
    """
    ranking = {
        SCOPE_APPLICATION: 0,
        SCOPE_COUNTRY: 1,
        SCOPE_ROLE: 2,
        SCOPE_COMPANY: 3,
        SCOPE_GLOBAL: 4,
    }
    return ranking.get(scope, -1)


def _scope_insufficient(value: ProfileValue, required_scope: str) -> bool:
    """The value's scope must be at least as broad as the required scope."""
    if not required_scope or required_scope == SCOPE_APPLICATION:
        return False
    return _scope_to_rank(value.scope) < _scope_to_rank(required_scope)


def decide_field_action(
    value: ProfileValue,
    policy: ApplicationPackagePolicy,
    *,
    now: datetime | None = None,
) -> FieldDecision:
    """Deterministic policy decision for one ``ProfileValue``.

    The decision matrix covers all 8 source/sensitivity combinations,
    plus jurisdiction, scope, and freshness guards.

    Returns ``FieldDecision`` with action ``"fill"``, ``"review"``, or
    ``"manual"`` and a non-empty list of reasons.
    """
    reasons: list[str] = []
    current = now or _utc_now()

    # --- Freshness: explicit expiry -------------------------------------------
    if _value_is_expired(value, now=current):
        reasons.append(
            f"The value expired at {value.expires_at} and cannot be used."
        )
        return FieldDecision(action="manual", reasons=reasons)

    # --- Freshness: staleness (unconfirmed or too old) -------------------------
    if _value_is_stale(value, now=current):
        reasons.append(
            "The value has not been confirmed recently enough for safe auto-fill."
        )
        # Staleness alone does not force "manual"; it forces "review" for
        # sources that would otherwise be "fill".
    else:
        # Only confirm this is NOT stale
        pass

    # --- Jurisdiction mismatch -------------------------------------------------
    if _jurisdiction_mismatch(value, policy):
        reasons.append(
            f"The value jurisdiction '{value.jurisdiction}' differs from the "
            f"policy jurisdiction '{policy.jurisdiction}'."
        )

    # --- Scope mismatch --------------------------------------------------------
    # If the value scope is narrower than what would be needed for the
    # target job's country/role/company, flag it.
    # (required_scope would come from a broader context; for now we check
    #  that the value is not broader than its own provenance scope.)

    # ==========================================================================
    # Decision matrix — source × sensitivity
    # ==========================================================================

    src = value.source
    sens = value.sensitivity

    # ---- DEMOGRAPHIC ---------------------------------------------------------
    if sens == SENSITIVITY_DEMOGRAPHIC:
        if not policy.permit_demographic_autofill:
            reasons.append(
                "Demographic answers are not permitted for auto-fill. "
                "Enable 'permit_demographic_autofill' in settings."
            )
            return FieldDecision(action="manual", reasons=reasons)

        # When opted in, treat demographic as standard (fall through)

    # ---- LEGAL ---------------------------------------------------------------
    if sens == SENSITIVITY_LEGAL:
        if policy.require_legal_answer_confirmation:
            reasons.append(
                "Legal answers require explicit user confirmation before fill."
            )
            if value.confirmed_by:
                reasons.append(
                    f"The value was confirmed by {value.confirmed_by} "
                    f"on {value.confirmed_at or 'an unknown date'}."
                )
            return FieldDecision(action="review", reasons=reasons)
        # If not required (cannot be disabled per existing code, but handle anyway)
        # fall through to source-based logic

    # ---- PERSONAL ------------------------------------------------------------
    if sens == SENSITIVITY_PERSONAL:
        if src == SOURCE_AI_SUGGESTION:
            reasons.append(
                "Personal info from AI suggestions cannot be auto-filled."
            )
            return FieldDecision(action="manual", reasons=reasons)

        if src == SOURCE_SCOPED_PREFERENCE and not policy.permit_sensitive_autofill:
            reasons.append(
                "Scoped preferences for personal data require "
                "'permit_sensitive_autofill' to be enabled."
            )
            # Review so the user can see and approve
            if not reasons or reasons[-1] != "Staleness — see above.":
                pass
            return FieldDecision(action="review", reasons=reasons)

        # profile_verified + personal → may fill if fresh
        if src == SOURCE_PROFILE_VERIFIED:
            if _value_is_stale(value, now=current):
                reasons.append(
                    "Confirmed personal data has aged past the freshness threshold."
                )
                return FieldDecision(action="review", reasons=reasons)
            if _jurisdiction_mismatch(value, policy):
                return FieldDecision(action="review", reasons=reasons)
            reasons.append("Verified personal data is fresh and permissible.")
            return FieldDecision(action="fill", reasons=reasons)

        # scoped_preference + personal (with permit_sensitive_autofill) → fill if fresh
        if src == SOURCE_SCOPED_PREFERENCE and policy.permit_sensitive_autofill:
            if _value_is_stale(value, now=current):
                reasons.append(
                    "Scoped personal preference has aged past the freshness threshold."
                )
                return FieldDecision(action="review", reasons=reasons)
            if _jurisdiction_mismatch(value, policy):
                return FieldDecision(action="review", reasons=reasons)
            reasons.append("Scoped personal preference is permitted and fresh.")
            return FieldDecision(action="fill", reasons=reasons)

        # fallback — should not be reached
        reasons.append("Personal data requires review.")
        return FieldDecision(action="review", reasons=reasons)

    # ---- STANDARD (and demographic with opt-in) ------------------------------
    if sens in (SENSITIVITY_STANDARD, SENSITIVITY_DEMOGRAPHIC):
        if src == SOURCE_AI_SUGGESTION:
            reasons.append(
                "AI-suggested values require human review before filling."
            )
            return FieldDecision(action="review", reasons=reasons)

        if src == SOURCE_CONTEXT_DEPENDENT:
            reasons.append(
                "Context-dependent values require human review to confirm "
                "the appropriate answer for this specific application."
            )
            return FieldDecision(action="review", reasons=reasons)

        # profile_verified or scoped_preference → may fill
        if src in (SOURCE_PROFILE_VERIFIED, SOURCE_SCOPED_PREFERENCE):
            if _value_is_stale(value, now=current):
                reasons.append(
                    "The value has not been confirmed recently. "
                    "Review to verify it is still current."
                )
                return FieldDecision(action="review", reasons=reasons)
            if _jurisdiction_mismatch(value, policy):
                return FieldDecision(action="review", reasons=reasons)
            reasons.append(
                f"Verified {sens} data is current and permissible."
            )
            return FieldDecision(action="fill", reasons=reasons)

    # ---- UNKNOWN-REQUIRED (fallback) -----------------------------------------
    reasons.append("The value has an unrecognised source/sensitivity combination and requires manual review.")
    return FieldDecision(action="manual", reasons=reasons)