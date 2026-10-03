"""Explicitly scoped Assisted Apply corrections (AA-10)."""

from __future__ import annotations

import json
import hashlib
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from typing import Callable

from backend.domain.application_correction import (
    CORRECTION_DURABLE_SCOPES,
    CORRECTION_SCOPE_APPLICATION,
    CORRECTION_SCOPE_COMPANY,
    CORRECTION_SCOPE_COUNTRY,
    CORRECTION_SCOPE_DO_NOT_SAVE,
    CORRECTION_SCOPE_GLOBAL,
    CORRECTION_SCOPE_PRECEDENCE,
    CORRECTION_SCOPE_ROLE,
    CORRECTION_SCOPES,
    ApplicationCorrection,
    normalize_correction_key,
)
from backend.domain.application_package import ApplicationPackage, ApplicationPackageAnswer
from backend.repositories.contracts import BackendRepositories

CORRECTION_TTL_DAYS = 365
EXACT_QUESTION_PREFIX = "question.exact."


def normalize_exact_question(value: object) -> str:
    return " ".join(re.sub(r"[✱*]+", " ", str(value or "")).strip().casefold().split())


def is_sensitive_exact_question(value: object) -> bool:
    normalized = normalize_exact_question(value)
    return bool(re.search(
        r"\b(?:work authorization|visa|sponsorship|citizen|citizenship|date of birth|age|gender|sex|race|"
        r"ethnicity|disability|veteran|religion|marital|salary|compensation|declaration|certify|signature|"
        r"terms|privacy consent|criminal|conviction)\b",
        normalized,
    ))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _scope_key(package: ApplicationPackage, scope: str) -> str:
    if scope == CORRECTION_SCOPE_COUNTRY:
        location = package.policy.jurisdiction or package.job.location
        # Package inputs currently expose a free-form location. The final comma-
        # separated segment is the stable country portion used across cities.
        return normalize_correction_key(str(location).rsplit(",", 1)[-1])
    if scope == CORRECTION_SCOPE_ROLE:
        seniority = {"assistant", "associate", "chief", "graduate", "head", "junior", "lead", "principal", "senior", "staff"}
        words = normalize_correction_key(package.job.title).replace("-", " ").split()
        return " ".join(word for word in words if word not in seniority)
    if scope == CORRECTION_SCOPE_COMPANY:
        return normalize_correction_key(package.job.company)
    if scope == CORRECTION_SCOPE_GLOBAL:
        return "*"
    return normalize_correction_key(package.package_id)


class ApplicationCorrectionStore:
    def __init__(self, repositories: BackendRepositories) -> None:
        self._auth_repo = repositories.auth_repository

    @contextmanager
    def connection(self):
        if not hasattr(self._auth_repo, "_connect"):
            raise RuntimeError("ApplicationCorrectionStore requires a SQLite backend.")
        with self._auth_repo._connect() as connection:
            yield connection

    def save(self, correction: ApplicationCorrection) -> None:
        # Corrections are append-only. Replacing one records both a supersession and
        # an audit event instead of overwriting its provenance.
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT correction_id FROM assisted_apply_corrections
                WHERE user_id = ? AND field_intent = ? AND scope = ? AND scope_key = ?
                  AND superseded_at = ''
                """,
                (correction.user_id, correction.field_intent, correction.scope, correction.scope_key),
            ).fetchall()
            for row in rows:
                old_id = str(row["correction_id"])
                connection.execute(
                    "UPDATE assisted_apply_corrections SET superseded_at = ?, superseded_by = ? WHERE correction_id = ?",
                    (correction.created_at, correction.correction_id, old_id),
                )
                self._audit(connection, old_id, correction.user_id, "superseded", correction.created_at, {"superseded_by": correction.correction_id})
            connection.execute(
            """
            INSERT INTO assisted_apply_corrections (
                correction_id, user_id, source_package_id, source_job_id,
                field_intent, corrected_value, scope, scope_key, provenance,
                created_at, expires_at, superseded_at, superseded_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', '')
            """,
            (
                correction.correction_id, correction.user_id, correction.source_package_id,
                correction.source_job_id, correction.field_intent, correction.corrected_value,
                correction.scope, correction.scope_key, correction.provenance,
                correction.created_at, correction.expires_at,
            ),
            )
            self._audit(connection, correction.correction_id, correction.user_id, "created", correction.created_at, correction.to_dict())

    def _audit(self, connection, correction_id: str, user_id: str, event_type: str, occurred_at: str, details: dict) -> None:
        connection.execute(
            "INSERT INTO assisted_apply_correction_audit (correction_id, user_id, event_type, occurred_at, details_json) VALUES (?, ?, ?, ?, ?)",
            (correction_id, user_id, event_type, occurred_at, json.dumps(details, ensure_ascii=False)),
        )

    def list_active(self, user_id: str, field_intents: list[str], now: datetime) -> list[ApplicationCorrection]:
        if not field_intents:
            return []
        placeholders = ",".join("?" for _ in field_intents)
        with self.connection() as connection:
            rows = connection.execute(
                f"""SELECT * FROM assisted_apply_corrections
                    WHERE user_id = ? AND field_intent IN ({placeholders})
                      AND superseded_at = '' AND expires_at > ?
                    ORDER BY created_at DESC""",
                (user_id, *field_intents, now.isoformat()),
            ).fetchall()
        return [ApplicationCorrection.from_payload(dict(row)) for row in rows]

    def list_active_exact_answers(self, user_id: str, now: datetime) -> list[ApplicationCorrection]:
        with self.connection() as connection:
            rows = connection.execute(
                """SELECT * FROM assisted_apply_corrections
                   WHERE user_id = ? AND field_intent LIKE ?
                     AND superseded_at = '' AND expires_at > ?
                   ORDER BY created_at DESC""",
                (user_id, f"{EXACT_QUESTION_PREFIX}%", now.isoformat()),
            ).fetchall()
        return [ApplicationCorrection.from_payload(dict(row)) for row in rows]

    def audit_events(self, user_id: str) -> list[dict]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM assisted_apply_correction_audit WHERE user_id = ? ORDER BY audit_id",
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]


@dataclass(slots=True)
class AssistedApplyCorrectionService:
    repositories: BackendRepositories
    now_provider: Callable[[], datetime] = field(default=_utc_now, repr=False)
    store: ApplicationCorrectionStore = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.store = ApplicationCorrectionStore(self.repositories)

    def _now(self) -> datetime:
        return _as_utc(self.now_provider())

    def save_correction(
        self,
        *,
        user_id: str,
        package: ApplicationPackage,
        field_intent: str,
        corrected_value: str,
        scope: str,
    ) -> dict:
        if package.user_id != str(user_id or "").strip():
            raise PermissionError("Application package belongs to another user.")
        normalized_scope = str(scope or "").strip()
        if normalized_scope not in CORRECTION_SCOPES:
            raise ValueError("Unsupported correction scope.")
        intent = str(field_intent or "").strip()
        value = str(corrected_value or "").strip()
        if not intent or not value:
            raise ValueError("field_intent and corrected_value are required.")
        if not any(answer.field_intent == intent for answer in package.answers):
            raise ValueError("The correction does not match an answer in this package.")

        if normalized_scope in {CORRECTION_SCOPE_APPLICATION, CORRECTION_SCOPE_DO_NOT_SAVE}:
            return {"persisted": False, "scope": normalized_scope, "correction_id": ""}

        key = _scope_key(package, normalized_scope)
        if not key:
            raise ValueError(f"This package has no value for the selected {normalized_scope} scope.")
        now = self._now()
        correction = ApplicationCorrection(
            correction_id=f"aacorr_{token_urlsafe(24)}",
            user_id=package.user_id,
            source_package_id=package.package_id,
            source_job_id=package.job_id,
            field_intent=intent,
            corrected_value=value,
            scope=normalized_scope,
            scope_key=key,
            provenance="explicit_user_correction",
            created_at=now.isoformat(),
            expires_at=(now + timedelta(days=CORRECTION_TTL_DAYS)).isoformat(),
        )
        self.store.save(correction)
        return {"persisted": True, "scope": normalized_scope, "correction_id": correction.correction_id}

    def apply_matching(self, package: ApplicationPackage, answers: list[ApplicationPackageAnswer]) -> list[ApplicationPackageAnswer]:
        corrections = self.store.list_active(package.user_id, [item.field_intent for item in answers], self._now())
        matches: dict[str, ApplicationCorrection] = {}
        for correction in corrections:
            if correction.scope not in CORRECTION_DURABLE_SCOPES:
                continue
            if correction.scope_key != _scope_key(package, correction.scope):
                continue
            current = matches.get(correction.field_intent)
            if current is None or CORRECTION_SCOPE_PRECEDENCE[correction.scope] > CORRECTION_SCOPE_PRECEDENCE[current.scope]:
                matches[correction.field_intent] = correction

        result: list[ApplicationPackageAnswer] = []
        for answer in answers:
            correction = matches.get(answer.field_intent)
            if correction is None:
                result.append(answer)
                continue
            result.append(ApplicationPackageAnswer(
                field_intent=answer.field_intent,
                label=answer.label,
                proposed_value=correction.corrected_value,
                source="scoped_preference",
                sensitivity=answer.sensitivity,
                scope=correction.scope,
                confidence=1.0,
                requires_review=answer.requires_review,
                reasons=[*answer.reasons, f"explicit_user_correction:{correction.scope}"],
            ))
        return result

    def save_exact_standard_answer(
        self,
        *,
        user_id: str,
        package: ApplicationPackage,
        question_label: str,
        answer_value: str,
    ) -> dict:
        if package.user_id != str(user_id or "").strip():
            raise PermissionError("Application package belongs to another user.")
        label = normalize_exact_question(question_label)
        value = str(answer_value or "").strip()
        if not label or len(label) > 300 or not value or len(value) > 5_000:
            raise ValueError("A bounded question label and answer are required.")
        if is_sensitive_exact_question(label):
            raise ValueError("Sensitive, legal, or demographic answers are never saved for automatic reuse.")
        known_labels = {normalize_exact_question(item.label) for item in [*package.answers, *package.standard_answers]}
        if label in known_labels:
            raise ValueError("This answer is already owned by the immutable application package.")
        digest = hashlib.sha256(label.encode("utf-8")).hexdigest()
        now = self._now()
        correction = ApplicationCorrection(
            correction_id=f"aacorr_{token_urlsafe(24)}",
            user_id=package.user_id,
            source_package_id=package.package_id,
            source_job_id=package.job_id,
            field_intent=f"{EXACT_QUESTION_PREFIX}{digest}",
            corrected_value=value,
            scope=CORRECTION_SCOPE_GLOBAL,
            scope_key="*",
            provenance=f"exact_question:{label}",
            created_at=now.isoformat(),
            expires_at=(now + timedelta(days=CORRECTION_TTL_DAYS)).isoformat(),
        )
        self.store.save(correction)
        return {"persisted": True, "scope": CORRECTION_SCOPE_GLOBAL, "correction_id": correction.correction_id}

    def saved_standard_answers(self, user_id: str) -> list[ApplicationPackageAnswer]:
        answers: list[ApplicationPackageAnswer] = []
        seen: set[str] = set()
        for correction in self.store.list_active_exact_answers(user_id, self._now()):
            label = correction.provenance.removeprefix("exact_question:")
            if not label or correction.field_intent in seen or is_sensitive_exact_question(label):
                continue
            seen.add(correction.field_intent)
            answers.append(ApplicationPackageAnswer.from_payload({
                "field_intent": correction.field_intent,
                "label": label,
                "proposed_value": correction.corrected_value,
                "source": "scoped_preference",
                "sensitivity": "standard",
                "scope": "global",
                "confidence": 1,
                "requires_review": False,
                "reasons": ["Exact non-sensitive question previously answered by the user."],
                "provenance": correction.provenance,
            }))
        return answers
