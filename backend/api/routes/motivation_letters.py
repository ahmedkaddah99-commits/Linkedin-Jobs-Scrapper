"""API routes for motivation letter generation (CP-037R).

REST endpoints for evidence-backed, anti-copying motivation letter generation.
"""

from __future__ import annotations

import os
from http import HTTPStatus

from backend.api.routes.registry import ApiRouteContext, RouteRegistry
from backend.capabilities.tailored_documents.motivation_letters import (
    MotivationEvidence,
    ExperienceEvidence,
    generate_motivation_letter,
)

_DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"


def _deepseek_api_key() -> str:
    return os.getenv("DEEPSEEK_API_KEY", "")


def register_routes(registry: RouteRegistry) -> None:
    registry.exact(
        "POST",
        ("motivation-letters",),
        _handle_generate,
        auth_required=True,
        name="motivation_letters.generate",
    )


def _handle_generate(context: ApiRouteContext) -> None:
    user, _ = context.require_identity()
    payload = context.read_json_body()

    job = payload.get("job") or {}
    if not isinstance(job, dict) or not job:
        context.send_error(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "validation_error",
            "job object is required.",
        )
        return

    cv_text = str(payload.get("cv_text") or "")
    if not cv_text.strip():
        context.send_error(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "validation_error",
            "cv_text is required.",
        )
        return

    candidate_name = str(
        payload.get("candidate_name")
        or user.full_name
        or ""
    ).strip()
    if not candidate_name:
        context.send_error(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "validation_error",
            "candidate_name is required.",
        )
        return

    api_key = _deepseek_api_key()

    raw_motivations = payload.get("verified_motivations") or []
    verified_motivations = [
        MotivationEvidence(
            evidence_id=str(m.get("evidence_id", "")),
            category=str(m.get("category", "")),
            statement=str(m.get("statement", "")),
            confidence=str(m.get("confidence", "medium")),
        )
        for m in raw_motivations
        if isinstance(m, dict)
    ]

    raw_experiences = payload.get("verified_experiences") or []
    verified_experiences = [
        ExperienceEvidence(
            experience_id=str(e.get("experience_id", "")),
            role_title=str(e.get("role_title", "")),
            company=str(e.get("company", "")),
            period=str(e.get("period", "")),
            key_bullets=[
                str(b) for b in (e.get("key_bullets") or [])
            ],
        )
        for e in raw_experiences
        if isinstance(e, dict)
    ]

    model = str(payload.get("model") or _DEFAULT_DEEPSEEK_MODEL).strip()
    company_context = str(payload.get("company_context") or "")
    role_requirements = [
        str(r) for r in (payload.get("role_requirements") or [])
        if str(r).strip()
    ]
    output_language = str(payload.get("output_language") or "English").strip()
    skip_api_call = bool(payload.get("skip_api_call", False))

    result = generate_motivation_letter(
        deepseek_api_key=api_key,
        deepseek_model=model,
        job=job,
        cv_text=cv_text,
        candidate_name=candidate_name,
        verified_motivations=verified_motivations,
        verified_experiences=verified_experiences,
        company_context=company_context,
        role_requirements=role_requirements,
        output_language=output_language,
        skip_api_call=skip_api_call,
    )

    response_payload = {
        "job_id": result.job_id,
        "candidate_name": result.candidate_name,
        "letter_text": result.letter_text,
        "sections": [s.to_dict() for s in result.sections],
        "motivation_evidence_count": result.motivation_evidence_count,
        "experience_evidence_count": result.experience_evidence_count,
        "evidence_insufficient": result.evidence_insufficient,
        "insufficient_warning": result.insufficient_warning,
        "output_language": result.output_language,
    }
    if result.error:
        response_payload["error"] = result.error

    context.send_json(response_payload, status=HTTPStatus.OK)
