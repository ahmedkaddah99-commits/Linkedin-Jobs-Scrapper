from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


PUBLICATION_ORIGINS = frozenset({"administrator", "scheduled", "system", "restored"})
DEFAULT_PUBLICATION_POLICY_VERSION = "publication_policy_v1"
RESTORE_CONFIRMATION_TOKEN = "restore_publication"

PublicationOrigin = Literal["administrator", "scheduled", "system", "restored"]


class StalePublicationHeadError(ValueError):
    """The caller confirmed a head that is no longer current."""


class PublicationPolicyError(ValueError):
    """The requested publication policy is not registered."""


@dataclass(frozen=True)
class PublicationPolicy:
    version: str
    completeness_mode: Literal["report_only"] = "report_only"
    missing_apply_is_blocker: bool = False


PUBLICATION_POLICIES = {
    DEFAULT_PUBLICATION_POLICY_VERSION: PublicationPolicy(
        version=DEFAULT_PUBLICATION_POLICY_VERSION,
        completeness_mode="report_only",
        missing_apply_is_blocker=False,
    )
}


def get_publication_policy(version: str = "") -> PublicationPolicy:
    normalized = str(version or DEFAULT_PUBLICATION_POLICY_VERSION).strip()
    try:
        return PUBLICATION_POLICIES[normalized]
    except KeyError as exc:
        raise PublicationPolicyError(
            f"Publication policy '{normalized}' is not registered; no new blocker may be activated implicitly."
        ) from exc


@dataclass(frozen=True)
class RestorePublicationConfirmation:
    """Typed, explicit confirmation required before creating a restore publication."""

    target_publication_id: str
    expected_head_publication_id: str
    actor_user_id: str
    confirmation: Literal["restore_publication"] = RESTORE_CONFIRMATION_TOKEN

    @classmethod
    def from_values(
        cls,
        *,
        target_publication_id: str,
        expected_head_publication_id: str,
        actor_user_id: str,
        confirmation: str,
    ) -> "RestorePublicationConfirmation":
        target = str(target_publication_id or "").strip()
        expected = str(expected_head_publication_id or "").strip()
        actor = str(actor_user_id or "").strip()
        token = str(confirmation or "").strip()
        if not target:
            raise ValueError("target_publication_id is required.")
        if not actor:
            raise PermissionError("Publication restore requires an authorized administrator identity.")
        if token != RESTORE_CONFIRMATION_TOKEN:
            raise ValueError(f"Typed restore confirmation must be '{RESTORE_CONFIRMATION_TOKEN}'.")
        return cls(
            target_publication_id=target,
            expected_head_publication_id=expected,
            actor_user_id=actor,
            confirmation=RESTORE_CONFIRMATION_TOKEN,
        )
