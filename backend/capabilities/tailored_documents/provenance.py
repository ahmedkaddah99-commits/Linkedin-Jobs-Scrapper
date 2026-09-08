"""Stable tailored-CV identity and provenance propagation helpers (AA-211)."""

from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any, Mapping


def source_experience_id(item: Mapping[str, Any]) -> str:
    return str(
        item.get("source_experience_id")
        or item.get("experience_id")
        or item.get("linked_experience_id")
        or ""
    ).strip()


def bullet_text(value: Any) -> str:
    if isinstance(value, Mapping):
        if "approved_text" in value:
            return str(value.get("approved_text") or "")
        return str(value.get("text") or value.get("value") or value.get("label") or "")
    return str(value or "")


def stable_bullet_id(source_id: str, index: int, text: str) -> str:
    digest = hashlib.sha256(f"{source_id}\0{index}\0{text}".encode("utf-8")).hexdigest()[:16]
    return f"{source_id}:bullet:{digest}"


def propagate_tailored_provenance(
    record: dict[str, Any],
    *,
    selected_cv_version: Mapping[str, Any] | None = None,
    generation_provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach stable identity metadata without changing visible CV text."""
    cv_version = deepcopy(dict(selected_cv_version or {}))
    generation = deepcopy(dict(generation_provenance or {}))
    experiences = record.get("cv_professional_experience")
    if not isinstance(experiences, list):
        experiences = []

    enriched: list[dict[str, Any]] = []
    all_experiences_identified = True
    for experience in experiences:
        if not isinstance(experience, Mapping):
            continue
        item = dict(experience)
        experience_id = source_experience_id(item)
        if experience_id:
            item["source_experience_id"] = experience_id
            item["provenance_confidence"] = "full"
        else:
            item["provenance_confidence"] = "reduced"
            all_experiences_identified = False
        if cv_version:
            item["selected_cv_version"] = deepcopy(cv_version)
        if generation:
            item["generation_provenance"] = deepcopy(generation)

        bullets: list[Any] = []
        for index, raw_bullet in enumerate(item.get("bullets") or []):
            text = bullet_text(raw_bullet)
            if not text:
                continue
            if isinstance(raw_bullet, Mapping):
                bullet = dict(raw_bullet)
            elif experience_id:
                bullet = {"text": text, "approved_text": text}
            else:
                bullets.append(raw_bullet)
                continue
            if "approved_text" in bullet:
                # Approved text is intentionally copied without normalization.
                bullet["text"] = bullet["approved_text"]
            else:
                bullet["text"] = text
                bullet["approved_text"] = text
            if experience_id:
                bullet["bullet_id"] = str(bullet.get("bullet_id") or stable_bullet_id(experience_id, index, text))
                bullet["source_experience_id"] = experience_id
                bullet["provenance_confidence"] = "full"
            else:
                bullet["provenance_confidence"] = "reduced"
            if generation:
                bullet["generation_provenance"] = deepcopy(generation)
            bullets.append(bullet)
        item["bullets"] = bullets
        enriched.append(item)

    record["cv_professional_experience"] = enriched
    record["provenance_confidence"] = "full" if all_experiences_identified else "reduced"
    record["provenance_status"] = "complete" if all_experiences_identified else "legacy_reduced_confidence"
    if cv_version:
        record["selected_cv_version"] = cv_version
    if generation:
        record["generation_provenance"] = generation
    package_version = record.get("application_package_version", record.get("package_version"))
    if package_version not in (None, ""):
        record["selected_package_version"] = package_version
    return record
