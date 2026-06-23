from __future__ import annotations

import re
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Iterable, Mapping
from uuid import uuid4


FACT_TYPES = {"action", "tool", "stakeholder", "outcome", "metric"}
CERTAINTIES = {"confirmed", "estimated", "uncertain"}
_NUMBER_PATTERN = re.compile(
    r"(?<!\w)(?:[$€£]\s*)?\d+(?:[.,]\d+)?(?:\s*%|\s*(?:hours?|days?|weeks?|months?|years?))?",
    re.I,
)
_PROMPT_LEAKAGE = ("what did", "please describe", "tell me about", "estimated impact")
_TOOL_TERMS = ("python", "sql", "excel", "power bi", "tableau", "sap", "jira", "salesforce", "deepseek")
_OUTCOME_TERMS = ("improved", "reduced", "increased", "delivered", "achieved", "saved", "grew", "accelerated")
_STAKEHOLDER_TERMS = ("stakeholder", "customer", "client", "manager", "leadership", "team", "partner")
_GROUNDING_STOP_WORDS = {
    "a",
    "also",
    "an",
    "and",
    "as",
    "at",
    "by",
    "for",
    "i",
    "in",
    "my",
    "of",
    "on",
    "the",
    "this",
    "through",
    "to",
    "using",
    "with",
    "work",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _store(user) -> dict[str, Any]:
    metadata = dict(user.metadata or {})
    stored = dict(metadata.get("career_memory") or {})
    stored.setdefault("facts", [])
    stored.setdefault("outputs", [])
    stored.setdefault("source_signatures", {})
    return stored


def _persist(application, user, stored: Mapping[str, Any]) -> None:
    metadata = dict(user.metadata or {})
    metadata["career_memory"] = deepcopy(dict(stored))
    user.metadata = metadata
    user.updated_at = _now()
    application.repositories.auth_repository.upsert_user(user)


def _latest_versions(records: Iterable[Mapping[str, Any]], id_field: str) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for raw_record in records:
        record = dict(raw_record)
        record_id = str(record.get(id_field) or "")
        if not record_id:
            continue
        if int(record.get("version") or 0) >= int(latest.get(record_id, {}).get("version") or 0):
            latest[record_id] = record
    return sorted(latest.values(), key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)


def _active_facts(stored: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        fact
        for fact in _latest_versions(stored.get("facts") or [], "fact_id")
        if str(fact.get("status") or "active") == "active"
    ]


def _candidate_assets(user) -> dict[str, dict[str, Any]]:
    return {
        str(asset.get("asset_id") or ""): dict(asset)
        for asset in (user.metadata or {}).get("candidate_assets") or []
        if isinstance(asset, Mapping) and str(asset.get("asset_id") or "")
    }


def _asset_signature(asset: Mapping[str, Any]) -> str:
    metadata = dict(asset.get("metadata") or {})
    return str(metadata.get("content_sha256") or sha256(str(metadata.get("source_text") or "").encode("utf-8")).hexdigest())


def _source_sentences(text: str) -> list[str]:
    candidates = re.split(r"(?:\r?\n)+|(?<=[.!?])\s+", str(text or ""))
    cleaned: list[str] = []
    for candidate in candidates:
        sentence = re.sub(r"^\s*[-*•]\s*", "", candidate).strip()
        if 20 <= len(sentence) <= 320 and sentence.casefold() not in {item.casefold() for item in cleaned}:
            cleaned.append(sentence)
    return cleaned[:30]


def _fact_type(value: str) -> str:
    lowered = value.casefold()
    if _NUMBER_PATTERN.search(value):
        return "metric"
    if any(term in lowered for term in _TOOL_TERMS):
        return "tool"
    if any(term in lowered for term in _OUTCOME_TERMS):
        return "outcome"
    if any(term in lowered for term in _STAKEHOLDER_TERMS):
        return "stakeholder"
    return "action"


def _new_extracted_fact(asset: Mapping[str, Any], value: str, signature: str) -> dict[str, Any]:
    asset_id = str(asset.get("asset_id") or "")
    fact_id = f"fact_{sha256(f'{asset_id}:{value.casefold()}'.encode('utf-8')).hexdigest()[:16]}"
    fact_type = _fact_type(value)
    return {
        "fact_id": fact_id,
        "subject": {"company": "", "role": "", "project": ""},
        "type": fact_type,
        "value": value,
        "certainty": "uncertain" if fact_type == "metric" else "estimated",
        "sources": [{"asset_id": asset_id, "page": 1, "quote_hash": sha256(value.encode("utf-8")).hexdigest()}],
        "created_by": "extraction",
        "version": 1,
        "status": "active",
        "source_signature": signature,
        "created_at": _now(),
        "updated_at": _now(),
    }


def get_career_memory_state(user) -> dict[str, Any]:
    stored = _store(user)
    fact_history = sorted(
        [dict(item) for item in stored.get("facts") or [] if isinstance(item, Mapping)],
        key=lambda item: (str(item.get("fact_id") or ""), int(item.get("version") or 0)),
    )
    output_history = sorted(
        [dict(item) for item in stored.get("outputs") or [] if isinstance(item, Mapping)],
        key=lambda item: (str(item.get("output_id") or ""), int(item.get("version") or 0)),
    )
    return {
        "facts": _latest_versions(stored.get("facts") or [], "fact_id"),
        "active_facts": _active_facts(stored),
        "outputs": _latest_versions(stored.get("outputs") or [], "output_id"),
        "fact_history": fact_history,
        "output_history": output_history,
    }


def extract_facts(application, user, source_asset_ids: Iterable[str]) -> dict[str, Any]:
    selected_ids = [str(item).strip() for item in source_asset_ids if str(item).strip()]
    assets = _candidate_assets(user)
    missing_ids = [asset_id for asset_id in selected_ids if asset_id not in assets]
    if missing_ids:
        raise ValueError(f"Career Memory sources were not found: {', '.join(missing_ids)}")
    stored = _store(user)
    facts = list(stored.get("facts") or [])
    latest_by_id = {fact["fact_id"]: fact for fact in _latest_versions(facts, "fact_id")}
    version_by_id = {fact_id: int(fact.get("version") or 1) for fact_id, fact in latest_by_id.items()}
    current_signatures = {asset_id: _asset_signature(assets[asset_id]) for asset_id in selected_ids}

    for fact in list(latest_by_id.values()):
        source_ids = {str(source.get("asset_id") or "") for source in fact.get("sources") or []}
        if not source_ids or str(fact.get("status") or "active") != "active":
            continue
        expected_signature = str(fact.get("source_signature") or "")
        source_changed = any(
            source_id not in current_signatures or current_signatures[source_id] != expected_signature
            for source_id in source_ids
        )
        if source_changed:
            stale_version = {
                **fact,
                "version": int(fact.get("version") or 1) + 1,
                "status": "stale",
                "updated_at": _now(),
            }
            facts.append(stale_version)
            version_by_id[fact["fact_id"]] = stale_version["version"]

    existing_keys = {
        (str(fact.get("fact_id") or ""), str(fact.get("source_signature") or ""))
        for fact in facts
    }
    created: list[dict[str, Any]] = []
    for asset_id in selected_ids:
        asset = assets[asset_id]
        metadata = dict(asset.get("metadata") or {})
        signature = current_signatures[asset_id]
        for sentence in _source_sentences(str(metadata.get("source_text") or "")):
            fact = _new_extracted_fact(asset, sentence, signature)
            if (fact["fact_id"], signature) in existing_keys:
                continue
            fact["version"] = version_by_id.get(fact["fact_id"], 0) + 1
            facts.append(fact)
            created.append(fact)
            version_by_id[fact["fact_id"]] = fact["version"]
            existing_keys.add((fact["fact_id"], signature))
    stored["facts"] = facts
    stored["source_signatures"] = current_signatures
    _persist(application, user, stored)
    return {**get_career_memory_state(user), "created_count": len(created), "selected_source_ids": selected_ids}


def next_question(user) -> dict[str, Any]:
    facts = _active_facts(_store(user))
    uncertain_metric = next(
        (fact for fact in facts if fact.get("type") == "metric" and fact.get("certainty") != "confirmed"),
        None,
    )
    if uncertain_metric:
        return {
            "question_id": f"confirm-{uncertain_metric['fact_id']}",
            "fact_id": uncertain_metric["fact_id"],
            "question": f"Can you confirm this number and its context: “{uncertain_metric['value']}”?",
            "expected_type": "metric",
            "requires_confirmation": True,
        }
    if not any(fact.get("type") == "outcome" for fact in facts):
        return {
            "question_id": "missing-outcome",
            "fact_id": "",
            "question": "What concrete outcome resulted from this work?",
            "expected_type": "outcome",
            "requires_confirmation": False,
        }
    if not any(fact.get("type") == "tool" for fact in facts):
        return {
            "question_id": "missing-tool",
            "fact_id": "",
            "question": "Which tool, system, or method was central to this result?",
            "expected_type": "tool",
            "requires_confirmation": False,
        }
    return {
        "question_id": "facts-ready",
        "fact_id": "",
        "question": "The current facts are ready for grounded output generation.",
        "expected_type": "",
        "requires_confirmation": False,
    }


def confirm_fact(application, user, fact_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    stored = _store(user)
    latest = {fact["fact_id"]: fact for fact in _latest_versions(stored.get("facts") or [], "fact_id")}
    current = latest.get(str(fact_id or ""))
    value = str(payload.get("value") or "").strip()
    if current is None and not value:
        raise KeyError(f"Career Memory fact '{fact_id}' not found.")
    if current is None:
        current = {
            "fact_id": str(fact_id or f"fact_{uuid4().hex[:16]}"),
            "subject": {"company": "", "role": "", "project": ""},
            "type": str(payload.get("type") or "action"),
            "value": value,
            "certainty": "confirmed",
            "sources": [],
            "created_by": "user",
            "version": 0,
            "status": "active",
            "created_at": _now(),
        }
    fact_type = str(payload.get("type") or current.get("type") or "action")
    certainty = str(payload.get("certainty") or "confirmed")
    next_fact = {
        **current,
        "subject": {
            **dict(current.get("subject") or {}),
            **dict(payload.get("subject") or {}),
        },
        "type": fact_type if fact_type in FACT_TYPES else "action",
        "value": value or str(current.get("value") or ""),
        "certainty": certainty if certainty in CERTAINTIES else "confirmed",
        "created_by": "user",
        "version": int(current.get("version") or 0) + 1,
        "status": "active",
        "updated_at": _now(),
    }
    stored["facts"] = [*(stored.get("facts") or []), next_fact]
    _persist(application, user, stored)
    return {"fact": next_fact, **get_career_memory_state(user)}


def _confirmed_numeric_values(facts: Iterable[Mapping[str, Any]]) -> set[str]:
    values: set[str] = set()
    for fact in facts:
        if str(fact.get("certainty") or "") != "confirmed":
            continue
        values.update(match.group(0).strip() for match in _NUMBER_PATTERN.finditer(str(fact.get("value") or "")))
    return values


def _meaningful_tokens(value: str) -> list[str]:
    return [
        token
        for token in re.findall(
            r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ0-9+#-]*",
            str(value or "").casefold(),
        )
        if len(token) > 1 and token not in _GROUNDING_STOP_WORDS
    ]


def _has_repeated_phrase(value: str, *, phrase_size: int = 3) -> bool:
    tokens = _meaningful_tokens(value)
    if len(tokens) < phrase_size * 2:
        return False
    seen: set[tuple[str, ...]] = set()
    for index in range(len(tokens) - phrase_size + 1):
        phrase = tuple(tokens[index : index + phrase_size])
        if phrase in seen:
            return True
        seen.add(phrase)
    return False


def _unsupported_output_tokens(
    output: Mapping[str, Any],
    facts: Iterable[Mapping[str, Any]],
) -> list[str]:
    grounded_tokens: set[str] = set()
    for fact in facts:
        grounded_tokens.update(_meaningful_tokens(str(fact.get("value") or "")))
        subject = dict(fact.get("subject") or {})
        for value in subject.values():
            grounded_tokens.update(_meaningful_tokens(str(value or "")))
    output_tokens = set(
        _meaningful_tokens(
            f"{str(output.get('cv_bullet') or '')} {str(output.get('cover_letter') or '')}"
        )
    )
    return sorted(output_tokens - grounded_tokens)


def _quality(output: Mapping[str, Any], facts: list[dict[str, Any]]) -> dict[str, Any]:
    cv_bullet = str(output.get("cv_bullet") or "").strip()
    cover_letter = str(output.get("cover_letter") or "").strip()
    combined = f"{cv_bullet}\n{cover_letter}"
    issues: list[dict[str, str]] = []
    confirmed_numbers = _confirmed_numeric_values(facts)
    unsupported_numbers = {
        match.group(0).strip()
        for match in _NUMBER_PATTERN.finditer(combined)
        if match.group(0).strip() not in confirmed_numbers
    }
    if unsupported_numbers:
        issues.append({"code": "unconfirmed_metric", "message": f"Unconfirmed numbers: {', '.join(sorted(unsupported_numbers))}"})
    if any(fragment in combined.casefold() for fragment in _PROMPT_LEAKAGE):
        issues.append({"code": "prompt_leakage", "message": "Questionnaire wording leaked into generated output."})
    unsupported_tokens = _unsupported_output_tokens(output, facts)
    if unsupported_tokens:
        issues.append(
            {
                "code": "unsupported_phrase",
                "message": (
                    "Output wording is not grounded in the referenced facts: "
                    f"{', '.join(unsupported_tokens[:8])}"
                ),
            }
        )
    if len(cv_bullet) > 240:
        issues.append({"code": "bullet_too_long", "message": "The CV bullet exceeds 240 characters."})
    if cv_bullet.casefold().strip(" .") == cover_letter.casefold().strip(" ."):
        issues.append({"code": "duplicated_outputs", "message": "CV and cover-letter outputs must use different wording."})
    if _has_repeated_phrase(cv_bullet) or _has_repeated_phrase(cover_letter):
        issues.append({"code": "repeated_language", "message": "Generated wording repeats the same phrase."})
    malformed_subjects = [
        dict(fact.get("subject") or {})
        for fact in facts
        if bool(str(dict(fact.get("subject") or {}).get("company") or "").strip())
        != bool(str(dict(fact.get("subject") or {}).get("role") or "").strip())
    ]
    if malformed_subjects:
        issues.append(
            {
                "code": "malformed_context",
                "message": "Company and role context must be supplied together.",
            }
        )
    if not cv_bullet or not cover_letter:
        issues.append({"code": "missing_output", "message": "Both output formats are required."})
    elif not cover_letter.endswith((".", "!", "?")):
        issues.append(
            {
                "code": "grammar",
                "message": "The cover-letter narrative must end with sentence punctuation.",
            }
        )
    return {"status": "passed" if not issues else "flagged", "issues": issues}


def _compose_outputs(facts: list[dict[str, Any]], *, mode: str = "standard") -> tuple[str, str, list[str]]:
    eligible = [
        fact
        for fact in facts
        if not (_NUMBER_PATTERN.search(str(fact.get("value") or "")) and fact.get("certainty") != "confirmed")
    ]
    if not eligible:
        raise ValueError("Confirm at least one grounded fact before generating output.")
    by_type = {fact_type: [fact for fact in eligible if fact.get("type") == fact_type] for fact_type in FACT_TYPES}
    selected = (
        by_type["action"][:1]
        + by_type["tool"][:1]
        + by_type["outcome"][:1]
        + by_type["metric"][:1]
        + by_type["stakeholder"][:1]
    )
    if not selected:
        selected = eligible[:2]
    fact_ids = [str(fact.get("fact_id") or "") for fact in selected]
    values = [str(fact.get("value") or "").strip().rstrip(".") for fact in selected if str(fact.get("value") or "").strip()]
    if mode == "technical":
        tools = [str(fact.get("value") or "").strip().rstrip(".") for fact in by_type["tool"]]
        values = tools + [value for value in values if value not in tools]
    cv_bullet = "; ".join(values)
    if mode == "shorten" or len(cv_bullet) > 240:
        cv_bullet = cv_bullet[:237].rstrip(" ,;") + "..."
    cv_bullet = cv_bullet.rstrip(".") + "."
    subject = next((dict(fact.get("subject") or {}) for fact in selected if any(dict(fact.get("subject") or {}).values())), {})
    context = "In this work"
    if subject.get("company") and subject.get("role"):
        context = f"As {subject['role']} at {subject['company']}"
    cover_values = values[1:] + values[:1] if len(values) > 1 else values
    cover_letter = f"{context}, I {'. I also '.join(value[:1].lower() + value[1:] for value in cover_values)}."
    return cv_bullet, cover_letter, fact_ids


def generate_outputs(application, user, payload: Mapping[str, Any]) -> dict[str, Any]:
    stored = _store(user)
    facts = _active_facts(stored)
    cv_bullet, cover_letter, fact_ids = _compose_outputs(facts, mode=str(payload.get("mode") or "standard"))
    output = {
        "output_id": f"output_{uuid4().hex[:16]}",
        "version": 1,
        "fact_ids": fact_ids,
        "cv_bullet": cv_bullet,
        "cover_letter": cover_letter,
        "quality": {},
        "created_at": _now(),
        "updated_at": _now(),
    }
    referenced_facts = [fact for fact in facts if fact.get("fact_id") in fact_ids]
    output["quality"] = _quality(output, referenced_facts)
    stored["outputs"] = [*(stored.get("outputs") or []), output]
    _persist(application, user, stored)
    return {"output": output, **get_career_memory_state(user)}


def regenerate_output(application, user, output_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    stored = _store(user)
    latest_outputs = {output["output_id"]: output for output in _latest_versions(stored.get("outputs") or [], "output_id")}
    current = latest_outputs.get(str(output_id or ""))
    if current is None:
        raise KeyError(f"Career Memory output '{output_id}' not found.")
    facts_by_id = {fact["fact_id"]: fact for fact in _active_facts(stored)}
    facts = [facts_by_id[fact_id] for fact_id in current.get("fact_ids") or [] if fact_id in facts_by_id]
    action = str(payload.get("action") or "regenerate")
    if action == "edit":
        cv_bullet = str(payload.get("cv_bullet") or current.get("cv_bullet") or "").strip()
        cover_letter = str(payload.get("cover_letter") or current.get("cover_letter") or "").strip()
        fact_ids = list(current.get("fact_ids") or [])
    else:
        cv_bullet, cover_letter, fact_ids = _compose_outputs(facts, mode=action)
    next_output = {
        **current,
        "version": int(current.get("version") or 1) + 1,
        "fact_ids": fact_ids,
        "cv_bullet": cv_bullet,
        "cover_letter": cover_letter,
        "updated_at": _now(),
    }
    next_output["quality"] = _quality(next_output, facts)
    stored["outputs"] = [*(stored.get("outputs") or []), next_output]
    _persist(application, user, stored)
    return {"output": next_output, **get_career_memory_state(user)}
