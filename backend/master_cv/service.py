"""A persisted, user-owned Master CV.

The Master CV is intentionally independent from the legacy evidence and career
memory models. It is an editable career record: imported CV bullets are
ordinary starting content, while manually added bullets are marked as extra
evidence for tailoring. Nothing in this module is fed through the old evidence
review lifecycle.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from backend.capabilities.tailored_documents.cv_structuring import (
    extract_cv_professional_experiences,
    extract_cv_strategic_initiatives,
)
from backend.domain.models import UserRecord, utc_now_iso

MASTER_CV_METADATA_KEY = "master_cv"
MASTER_CV_SCHEMA_VERSION = 1
MAX_TEXT_LENGTH = 4000
MAX_BULLETS_PER_ENTRY = 100
MAX_ENTRIES_PER_SECTION = 100

_SECTION_LABELS = {
    "experience": "Experience",
    "projects": "Projects",
}
_ACTION_VERBS = {
    "accelerated",
    "built",
    "created",
    "delivered",
    "designed",
    "developed",
    "drove",
    "established",
    "facilitated",
    "generated",
    "identified",
    "implemented",
    "improved",
    "increased",
    "launched",
    "led",
    "managed",
    "mentored",
    "negotiated",
    "optimised",
    "optimized",
    "reduced",
    "shaped",
    "spearheaded",
    "streamlined",
    "supported",
}
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "into",
    "of",
    "on",
    "the",
    "this",
    "to",
    "with",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any, *, limit: int = MAX_TEXT_LENGTH) -> str:
    return str(value or "").strip()[:limit]


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def _normalise_profile(value: Mapping[str, Any] | None, user: UserRecord | None = None) -> dict[str, str]:
    raw = dict(value or {})
    fallback_name = _text(getattr(user, "display_name", ""))
    fallback_email = _text(getattr(user, "email", ""))
    return {
        "name": _text(raw.get("name")) or fallback_name or fallback_email.split("@", 1)[0],
        "headline": _text(raw.get("headline"), limit=240),
        "location": _text(raw.get("location"), limit=240),
        "email": _text(raw.get("email"), limit=320) or fallback_email,
        "linkedin": _text(raw.get("linkedin"), limit=500),
    }


def _score_bullet(text: str) -> int:
    words = re.findall(r"[A-Za-z][A-Za-z0-9+#-]*", text.casefold())
    score = 48
    if words and words[0] in _ACTION_VERBS:
        score += 18
    if len(words) >= 8:
        score += 10
    if any(char.isdigit() for char in text) or "%" in text:
        score += 18
    if re.search(r"\b(customer|client|team|stakeholder|leadership|partner|product|engineering)\b", text, re.I):
        score += 6
    return max(0, min(100, score))


def _meaningful_tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[A-Za-z][A-Za-z0-9+#-]*", value.casefold())
        if len(token) > 2 and token not in _STOP_WORDS
    }


def _guidance(bullet: Mapping[str, Any]) -> dict[str, Any]:
    text = _text(bullet.get("text"))
    score = int(bullet.get("score") or _score_bullet(text))
    words = re.findall(r"[A-Za-z][A-Za-z0-9+#-]*", text.casefold())
    has_action = bool(words and words[0] in _ACTION_VERBS)
    has_context = bool(re.search(r"\b(customer|client|team|stakeholder|leadership|partner|product|engineering)\b", text, re.I))
    has_impact = bool(bullet.get("metric")) or bool(re.search(r"\b\d+(?:\.\d+)?%?\b|\b(reduced|increased|improved|saved|grew|accelerated)\b", text, re.I))
    checks = [
        {
            "label": "Clear action",
            "detail": "Starts with a decisive action verb." if has_action else "Start with the action you personally took.",
            "state": "pass" if has_action else "warn",
        },
        {
            "label": "Useful context",
            "detail": "Shows your scope and collaborators." if has_context else "Name the team, customer, product, or scope involved.",
            "state": "pass" if has_context else "warn",
        },
        {
            "label": "Demonstrated impact",
            "detail": "Includes a measurable or credible outcome." if has_impact else "Add what changed because of your work.",
            "state": "pass" if has_impact else "warn",
        },
    ]
    if score >= 85:
        title = "Strong evidence"
        summary = "This achievement is specific, easy to scan, and clearly connected to your contribution."
    elif score >= 72:
        title = "Good foundation"
        summary = "This is useful career material. A little more detail would make your contribution easier to understand."
    else:
        title = "Worth developing"
        summary = "The idea is useful, but the action, context, or outcome needs more detail."
    suggestion = (
        "Already strong. Add the size of the customer group if it strengthens the story."
        if score >= 85
        else "Connect the work to a decision, deliverable, customer outcome, or other change."
    )
    return {
        "score": score,
        "title": title,
        "summary": summary,
        "checks": checks,
        "suggestion": suggestion,
        "use": "Runr can select this as source material when a target opportunity needs the skills or outcomes it demonstrates.",
    }


def _normalise_bullet(value: Mapping[str, Any], *, imported: bool = False) -> dict[str, Any]:
    text = _text(value.get("text"))
    if not text:
        raise ValueError("Bullet text is required.")
    score = int(value.get("score") or _score_bullet(text))
    bullet = {
        "id": _text(value.get("id"), limit=120) or _new_id("bullet"),
        "text": text,
        "score": max(0, min(100, score)),
        "metric": _text(value.get("metric"), limit=240),
        "extra": bool(value.get("extra", not imported)),
        "draft": bool(value.get("draft", not imported)),
        "source": _text(value.get("source"), limit=80) or ("cv_import" if imported else "manual"),
    }
    return bullet


def _normalise_entry(value: Mapping[str, Any], *, section_id: str, imported: bool = False) -> dict[str, Any]:
    title = _text(value.get("title"), limit=320)
    if not title:
        raise ValueError("Entry title is required.")
    raw_bullets = value.get("bullets") or []
    if not isinstance(raw_bullets, list):
        raise ValueError("Entry bullets must be a list.")
    bullets = [
        _normalise_bullet(item, imported=imported)
        for item in raw_bullets[:MAX_BULLETS_PER_ENTRY]
        if isinstance(item, Mapping) and _text(item.get("text"))
    ]
    return {
        "id": _text(value.get("id"), limit=120) or _new_id("entry"),
        "kind": "project" if section_id == "projects" or value.get("kind") == "project" else "work",
        "title": title,
        "organisation": _text(value.get("organisation"), limit=320),
        "dates": _text(value.get("dates"), limit=160),
        "location": _text(value.get("location"), limit=240),
        "collapsed": bool(value.get("collapsed", False)),
        "bullets": bullets,
    }


def _normalise_document(value: Mapping[str, Any], user: UserRecord | None = None) -> dict[str, Any]:
    raw = dict(value or {})
    raw_sections = raw.get("sections") or []
    sections: list[dict[str, Any]] = []
    if isinstance(raw_sections, list):
        for raw_section in raw_sections:
            if not isinstance(raw_section, Mapping):
                continue
            section_id = _text(raw_section.get("id"), limit=80).lower().replace(" ", "-")
            if not section_id:
                continue
            entries = []
            for raw_entry in (raw_section.get("entries") or [])[:MAX_ENTRIES_PER_SECTION]:
                if not isinstance(raw_entry, Mapping):
                    continue
                try:
                    entries.append(_normalise_entry(raw_entry, section_id=section_id))
                except ValueError:
                    continue
            sections.append({
                "id": section_id,
                "label": _text(raw_section.get("label"), limit=120) or _SECTION_LABELS.get(section_id, section_id.title()),
                "entries": entries,
            })
    if not sections:
        sections = [{"id": section_id, "label": label, "entries": []} for section_id, label in _SECTION_LABELS.items()]
    now = _now()
    return {
        "schema_version": MASTER_CV_SCHEMA_VERSION,
        "revision": max(1, int(raw.get("revision") or 1)),
        "profile": _normalise_profile(raw.get("profile"), user),
        "sections": sections,
        "created_at": _text(raw.get("created_at"), limit=80) or now,
        "updated_at": _text(raw.get("updated_at"), limit=80) or now,
    }


def _candidate_cv_text(user: UserRecord) -> str:
    metadata = dict(user.metadata or {})
    direct_text = _text(metadata.get("cv_text"), limit=100000)
    if direct_text:
        return direct_text
    assets = metadata.get("candidate_assets") or []
    if not isinstance(assets, list):
        return ""
    ranked: list[tuple[int, str]] = []
    for asset in assets:
        if not isinstance(asset, Mapping):
            continue
        source_text = _text(dict(asset.get("metadata") or {}).get("source_text"), limit=100000)
        if not source_text:
            continue
        kind = _text(asset.get("asset_kind"), limit=80).lower()
        ranked.append((2 if kind == "workspace_cv" else 1, source_text))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1] if ranked else ""


def build_initial_document(user: UserRecord) -> dict[str, Any]:
    """Build a real, editable document from identity and uploaded CV text."""
    document = _normalise_document({"profile": {}}, user)
    cv_text = _candidate_cv_text(user)
    if cv_text:
        experience_section = next(section for section in document["sections"] if section["id"] == "experience")
        for item in extract_cv_professional_experiences(cv_text):
            bullets = [{"text": text, "extra": False, "draft": False} for text in item.get("bullets") or [] if _text(text)]
            try:
                experience_section["entries"].append(_normalise_entry({
                    "kind": "work",
                    "title": item.get("role_title"),
                    "organisation": item.get("company"),
                    "location": item.get("location"),
                    "dates": item.get("period"),
                    "bullets": bullets,
                }, section_id="experience", imported=True))
            except ValueError:
                continue
        project_section = next(section for section in document["sections"] if section["id"] == "projects")
        for item in extract_cv_strategic_initiatives(cv_text):
            bullets = [{"text": text, "extra": False, "draft": False} for text in item.get("bullets") or [] if _text(text)]
            try:
                project_section["entries"].append(_normalise_entry({
                    "kind": "project",
                    "title": item.get("title"),
                    "bullets": bullets,
                }, section_id="projects", imported=True))
            except ValueError:
                continue
    return _normalise_document(document, user)


def get_document(user: UserRecord) -> tuple[dict[str, Any], bool]:
    stored = (user.metadata or {}).get(MASTER_CV_METADATA_KEY)
    if isinstance(stored, Mapping):
        return _normalise_document(stored, user), False
    return build_initial_document(user), True


def _touch(document: dict[str, Any]) -> dict[str, Any]:
    updated = deepcopy(document)
    updated["revision"] = int(updated.get("revision") or 0) + 1
    updated["updated_at"] = _now()
    return updated


def _find_entry(document: Mapping[str, Any], entry_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    for section in document.get("sections") or []:
        for entry in section.get("entries") or []:
            if entry.get("id") == entry_id:
                return section, entry
    return None


def _find_bullet(document: Mapping[str, Any], bullet_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]] | None:
    for section in document.get("sections") or []:
        for entry in section.get("entries") or []:
            for bullet in entry.get("bullets") or []:
                if bullet.get("id") == bullet_id:
                    return section, entry, bullet
    return None


def update_document(document: Mapping[str, Any], payload: Mapping[str, Any], user: UserRecord | None = None) -> dict[str, Any]:
    updated = _normalise_document(document, user)
    profile_payload = dict(updated["profile"])
    incoming_profile = payload.get("profile") if isinstance(payload.get("profile"), Mapping) else payload
    profile_fields = {"name", "headline", "location", "email", "linkedin"}
    profile_payload.update({key: incoming_profile.get(key) for key in profile_fields if key in incoming_profile})
    updated["profile"] = _normalise_profile(profile_payload, user)
    return _touch(updated)


def add_entry(document: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any]:
    updated = _normalise_document(document)
    requested_section = _text(payload.get("section_id"), limit=80).lower() or ("projects" if payload.get("kind") == "project" else "experience")
    section = next((item for item in updated["sections"] if item["id"] == requested_section), None)
    if section is None:
        raise ValueError(f"Unknown Master CV section '{requested_section}'.")
    if len(section["entries"]) >= MAX_ENTRIES_PER_SECTION:
        raise ValueError("This Master CV section has reached its entry limit.")
    section["entries"].append(_normalise_entry(payload, section_id=requested_section))
    return _touch(updated)


def update_entry(document: Mapping[str, Any], entry_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    updated = _normalise_document(document)
    found = _find_entry(updated, entry_id)
    if found is None:
        raise KeyError(f"Master CV entry '{entry_id}' was not found.")
    _, entry = found
    for field in ("title", "organisation", "dates", "location"):
        if field in payload:
            value = _text(payload.get(field), limit=320 if field in {"title", "organisation"} else 240)
            if field == "title" and not value:
                raise ValueError("Entry title is required.")
            entry[field] = value
    if "collapsed" in payload:
        entry["collapsed"] = bool(payload.get("collapsed"))
    return _touch(updated)


def delete_entry(document: Mapping[str, Any], entry_id: str) -> dict[str, Any]:
    updated = _normalise_document(document)
    found = _find_entry(updated, entry_id)
    if found is None:
        raise KeyError(f"Master CV entry '{entry_id}' was not found.")
    section, _ = found
    section["entries"] = [entry for entry in section["entries"] if entry.get("id") != entry_id]
    return _touch(updated)


def add_bullet(document: Mapping[str, Any], entry_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    updated = _normalise_document(document)
    found = _find_entry(updated, entry_id)
    if found is None:
        raise KeyError(f"Master CV entry '{entry_id}' was not found.")
    _, entry = found
    if len(entry["bullets"]) >= MAX_BULLETS_PER_ENTRY:
        raise ValueError("This entry has reached its bullet limit.")
    entry["bullets"].append(_normalise_bullet({
        "text": payload.get("text"),
        "metric": payload.get("metric"),
        "extra": True,
        "draft": True,
        "source": "manual",
    }))
    return _touch(updated)


def update_bullet(document: Mapping[str, Any], bullet_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    updated = _normalise_document(document)
    found = _find_bullet(updated, bullet_id)
    if found is None:
        raise KeyError(f"Master CV bullet '{bullet_id}' was not found.")
    _, _, bullet = found
    if "text" in payload:
        text = _text(payload.get("text"))
        if not text:
            raise ValueError("Bullet text is required.")
        bullet["text"] = text
        bullet["score"] = _score_bullet(text)
    if "metric" in payload:
        bullet["metric"] = _text(payload.get("metric"), limit=240)
    if "extra" in payload:
        bullet["extra"] = bool(payload.get("extra"))
    return _touch(updated)


def delete_bullet(document: Mapping[str, Any], bullet_id: str) -> dict[str, Any]:
    updated = _normalise_document(document)
    found = _find_bullet(updated, bullet_id)
    if found is None:
        raise KeyError(f"Master CV bullet '{bullet_id}' was not found.")
    _, entry, _ = found
    entry["bullets"] = [bullet for bullet in entry["bullets"] if bullet.get("id") != bullet_id]
    return _touch(updated)


def get_bullet_guidance(document: Mapping[str, Any], bullet_id: str) -> dict[str, Any]:
    found = _find_bullet(_normalise_document(document), bullet_id)
    if found is None:
        raise KeyError(f"Master CV bullet '{bullet_id}' was not found.")
    _, _, bullet = found
    return {"bullet_id": bullet_id, "guidance": _guidance(bullet)}


def improve_bullet(document: Mapping[str, Any], bullet_id: str) -> dict[str, Any]:
    found = _find_bullet(_normalise_document(document), bullet_id)
    if found is None:
        raise KeyError(f"Master CV bullet '{bullet_id}' was not found.")
    _, _, bullet = found
    guidance = _guidance(bullet)
    return {
        "bullet_id": bullet_id,
        "suggested_text": f"{bullet['text'].rstrip('.')} — add the measurable result or change this work created.",
        "guidance": guidance,
        "persisted": False,
    }


def select_relevant_bullets(document: Mapping[str, Any], target_text: str, *, limit: int = 5) -> dict[str, Any]:
    """Rank Master CV bullets against an opportunity without generating claims."""
    query = _text(target_text, limit=20000)
    if not query:
        raise ValueError("target_text is required.")
    query_tokens = _meaningful_tokens(query)
    matches: list[dict[str, Any]] = []
    for section in public_document(document)["sections"]:
        for entry in section["entries"]:
            for bullet in entry["bullets"]:
                bullet_tokens = _meaningful_tokens(bullet["text"])
                matched_terms = sorted(query_tokens & bullet_tokens)
                if not matched_terms:
                    continue
                score = min(100, round(len(matched_terms) / max(1, min(len(query_tokens), 12)) * 75 + bullet["score"] * 0.25))
                matches.append({
                    "bullet": bullet,
                    "section_id": section["id"],
                    "section_label": section["label"],
                    "entry_id": entry["id"],
                    "entry_title": entry["title"],
                    "matched_terms": matched_terms,
                    "relevance_score": score,
                })
    matches.sort(key=lambda item: (-int(item["relevance_score"]), -int(item["bullet"]["score"]), item["bullet"]["id"]))
    return {
        "query": query,
        "matches": matches[: max(1, min(20, int(limit or 5)))],
        "total_matches": len(matches),
        "grounding": "master_cv",
        "generated_claims": False,
    }


def _status(document: Mapping[str, Any]) -> dict[str, Any]:
    profile = document.get("profile") or {}
    entries = [entry for section in document.get("sections") or [] for entry in section.get("entries") or []]
    bullets = [bullet for entry in entries for bullet in entry.get("bullets") or []]
    extra_count = sum(1 for bullet in bullets if bullet.get("extra"))
    populated_profile = sum(bool(_text(profile.get(field))) for field in ("name", "headline", "location", "email", "linkedin"))
    depth = round(min(100, populated_profile / 5 * 25 + min(len(entries), 4) / 4 * 30 + min(len(bullets), 10) / 10 * 35 + (10 if any(_guidance(bullet)["checks"][2]["state"] == "pass" for bullet in bullets) else 0)))
    return {
        "ready": bool(entries or bullets),
        "label": "Master CV is ready" if entries or bullets else "Start your Master CV",
        "extraEvidenceCount": extra_count,
        "experienceCount": len(entries),
        "depth": depth,
    }


def public_document(document: Mapping[str, Any]) -> dict[str, Any]:
    result = _normalise_document(document)
    for section in result["sections"]:
        for entry in section["entries"]:
            for bullet in entry["bullets"]:
                bullet["guidance"] = _guidance(bullet)
    result["status"] = _status(result)
    return result


def export_document(document: Mapping[str, Any], format_name: str) -> dict[str, str]:
    public = public_document(document)
    normalized_format = _text(format_name, limit=20).lower() or "json"
    if normalized_format == "json":
        return {
            "format": "json",
            "filename": "master-cv.json",
            "content": json.dumps(public, indent=2, ensure_ascii=False),
        }
    if normalized_format == "text":
        lines = [public["profile"].get("name") or "Master CV", public["profile"].get("headline") or ""]
        for section in public["sections"]:
            lines.extend(["", section["label"].upper()])
            for entry in section["entries"]:
                lines.append(f"{entry['title']} | {entry['organisation']} | {entry['dates']}".strip(" |"))
                lines.extend(f"- {bullet['text']}" for bullet in entry["bullets"])
        return {"format": "text", "filename": "master-cv.txt", "content": "\n".join(lines).strip() + "\n"}
    raise ValueError("format must be json or text.")


def persist_document(application: Any, user: UserRecord, document: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _normalise_document(document, user)
    metadata = dict(user.metadata or {})
    metadata[MASTER_CV_METADATA_KEY] = normalized
    user.metadata = metadata
    user.updated_at = utc_now_iso()
    application.repositories.auth_repository.upsert_user(user)
    return public_document(normalized)
