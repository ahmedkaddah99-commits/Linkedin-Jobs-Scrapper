import json
import re
import time
from typing import Any, Callable, Dict, Optional

from google import genai
import requests

from backend.domain.ats_export_gate import evaluate_ats_export_gate

from .common import compact_whitespace, strip_json_fences
from .modes import CV_GENERATION_MODE_LIGHT, normalize_cv_generation_mode


DEFAULT_SYSTEM_PROMPT = "You are an expert career writing assistant."
ATS_TARGET_SCORE = 90
ATS_MAX_ATTEMPTS = 3


def split_bullets(text: str) -> list[str]:
    lines = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^[\-\*\u2022]+\s*", "", line)
        lines.append(line)
    return lines


def extract_city_from_job(job: Dict) -> str:
    location_raw = compact_whitespace(str(job.get("location_raw") or ""))
    if location_raw:
        first_chunk = location_raw.split(",")[0].strip()
        if first_chunk:
            return first_chunk

    description = str(job.get("full_description") or "")
    patterns = [
        r"(?i)\blocation:\s*([A-Za-zÃƒâ€žÃƒâ€“ÃƒÅ“ÃƒÂ¤ÃƒÂ¶ÃƒÂ¼ÃƒÅ¸\- ]+),\s*(?:[A-Za-zÃƒâ€žÃƒâ€“ÃƒÅ“ÃƒÂ¤ÃƒÂ¶ÃƒÂ¼ÃƒÅ¸\- ]+\s*-\s*)?Germany\b",
        r"(?i)\bbased in\s+([A-Za-zÃƒâ€žÃƒâ€“ÃƒÅ“ÃƒÂ¤ÃƒÂ¶ÃƒÂ¼ÃƒÅ¸\- ]+)\b",
        r"(?i)\bin\s+([A-Za-zÃƒâ€žÃƒâ€“ÃƒÅ“ÃƒÂ¤ÃƒÂ¶ÃƒÂ¼ÃƒÅ¸\- ]+),\s*Germany\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, description)
        if match:
            city = compact_whitespace(match.group(1))
            if city:
                return city

    return "Germany"


def format_header_location(job: Dict) -> str:
    city = extract_city_from_job(job)
    if not city or city.strip().lower() == "germany":
        return "Germany"
    city_clean = city.strip()
    if city_clean.lower().endswith(", germany"):
        return city_clean
    return f"{city_clean}, Germany"


def _structured_cv_json_schema() -> str:
    return """{
  "professional_summary": "text",
  "professional_experience": [
    {
      "role_title": "text",
      "company": "text",
      "period": "text",
      "bullets": ["text", "text"]
    }
  ],
  "education": [
    {
      "degree_title": "text",
      "thesis_title": "text",
      "thesis_bullets": ["text", "text"]
    }
  ],
  "skills": ["text", "text"]
}"""


def build_docs_prompt(
    cv_text: str,
    job: Dict,
    candidate_name: str,
    cv_generation_mode: str,
    extra_instructions: str = "",
    prompt_override: str = "",
) -> str:
    description_excerpt = str(job.get("full_description") or "")[:6000]
    job_id = str(job.get("job_id", ""))
    title = str(job.get("title", ""))
    company = str(job.get("company", ""))
    job_city = extract_city_from_job(job)
    normalized_mode = normalize_cv_generation_mode(cv_generation_mode)

    if prompt_override.strip():
        prompt = (
            prompt_override.strip()
            .replace("{{CV_TEXT}}", cv_text)
            .replace("{{JOB_ID}}", job_id)
            .replace("{{JOB_TITLE}}", title)
            .replace("{{JOB_COMPANY}}", company)
            .replace("{{JOB_CITY}}", job_city)
            .replace("{{JOB_DESCRIPTION}}", description_excerpt)
            .replace("{{CANDIDATE_NAME}}", candidate_name)
        )
    else:
        base_prompt = f"""
You are an expert career writing assistant.

Candidate full CV:
{cv_text}

Job:
- id: {job_id}
- title: {title}
- company: {company}
- city: {job_city}
- description: {description_excerpt}

Write tailored CV content in English.

Output requirements:
- Return only raw JSON (no markdown)
- Keep schema exactly:
{_structured_cv_json_schema()}
""".strip()
        if normalized_mode == CV_GENERATION_MODE_LIGHT:
            prompt = f"""{base_prompt}

Light Customization rules:
- Only professional_summary and skills may change.
- professional_summary:
  - write a targeted, credible summary in about 70-120 words
  - explain the fit for this exact role and company without inventing facts
- skills:
  - return 14 to 22 ATS-friendly skills grounded in the source CV and target role
- professional_experience:
  - copy only roles that already exist in the candidate CV
  - keep role titles, companies, periods, bullet wording, bullet ordering, and role ordering unchanged
- education:
  - keep degree titles, thesis titles, thesis bullets, and item ordering unchanged
- do not invent companies, dates, projects, certifications, or achievements
- do not produce a motivation letter, cover letter, greeting, or signature
""".strip()
        else:
            prompt = f"""{base_prompt}

Aggressive Customization rules:
- professional_summary:
  - detailed and substantial (about 70-140 words)
  - role-specific and company-specific
  - naturally professional, non-generic
  - clearly explain why the candidate is a strong fit
- professional_experience:
  - use only roles that exist in the candidate CV
  - keep role titles, companies, periods, and role order exactly as written in the candidate CV
  - you may rewrite bullet wording only
  - keep the evidence truthful to the source CV and do not invent tools, scope, or outcomes
  - if Allianz Technology appears in the CV, include it explicitly
  - never include projects/initiatives in this section
- skills:
  - 16 to 25 ATS-friendly skills relevant to the job description
  - include realistic adjacent skills when useful
- education:
  - keep degree titles, thesis titles, thesis bullets, and item ordering unchanged
- do not fabricate companies, dates, certifications, projects, or achievements
- do not produce a motivation letter, cover letter, greeting, or signature
""".strip()
    if extra_instructions:
        prompt = f"{prompt}\n\nAdditional user preferences:\n{extra_instructions.strip()}"
    return prompt


def build_ats_score_prompt(cv_text: str, job: Dict, structured_cv: Dict[str, Any]) -> str:
    description_excerpt = str(job.get("full_description") or "")[:6000]
    return f"""
You are an ATS resume reviewer.

Candidate source CV:
{cv_text}

Target job:
- id: {job.get('job_id', '')}
- title: {job.get('title', '')}
- company: {job.get('company', '')}
- description: {description_excerpt}

Current tailored CV draft:
{json.dumps(structured_cv, indent=2, ensure_ascii=False)}

Evaluate how well this tailored CV would perform in an ATS screen for the target job.

Return only raw JSON:
{{
  "score": 0,
  "missing_requirements": ["text"],
  "improvement_actions": ["text"],
  "rationale": "text"
}}

Rules:
- score must be an integer from 0 to 100
- missing_requirements must contain concise, ATS-relevant gaps grounded in the job description
- improvement_actions must be concise, actionable changes that stay truthful to the source CV
- if the CV already strongly covers a requirement, do not list it as missing
- keep lists short and specific
""".strip()


def build_ats_improvement_prompt(
    cv_text: str,
    job: Dict,
    structured_cv: Dict[str, Any],
    score_payload: Dict[str, Any],
    cv_generation_mode: str,
) -> str:
    description_excerpt = str(job.get("full_description") or "")[:6000]
    normalized_mode = normalize_cv_generation_mode(cv_generation_mode)
    base_prompt = f"""
You are improving a tailored CV for ATS matching while staying strictly truthful to the source CV.

Candidate source CV:
{cv_text}

Target job:
- id: {job.get('job_id', '')}
- title: {job.get('title', '')}
- company: {job.get('company', '')}
- description: {description_excerpt}

Current tailored CV draft:
{json.dumps(structured_cv, indent=2, ensure_ascii=False)}

Current ATS assessment:
{json.dumps(score_payload, indent=2, ensure_ascii=False)}

Rewrite the tailored CV to address the missing requirements where the source CV supports them.

Return only raw JSON (no markdown) using exactly this schema:
{_structured_cv_json_schema()}
""".strip()

    if normalized_mode == CV_GENERATION_MODE_LIGHT:
        rules = """
Rules:
- stay truthful to the source CV
- only improve professional_summary and skills
- keep professional_experience, education, titles, companies, dates, bullet wording, and ordering unchanged
- if a missing requirement is not supported by the source CV, do not fabricate it
- keep the result concise, ATS-friendly, and role-specific
""".strip()
    else:
        rules = """
Rules:
- stay truthful to the source CV
- never invent experience, tools, certifications, companies, dates, titles, or achievements
- keep role titles, companies, periods, education titles, and ordering exactly as written in the source CV
- you may improve professional_summary, skills, and professional_experience bullet wording only
- keep education bullet wording unchanged
- improve keyword coverage, evidence wording, and prioritization when the source CV supports it
- if a missing requirement is not supported by the source CV, do not fabricate it
- keep 16 to 25 skills
""".strip()
    return f"{base_prompt}\n\n{rules}"


def _load_json_object(text: str) -> Dict[str, Any]:
    parsed = json.loads(strip_json_fences(str(text)))
    if not isinstance(parsed, dict):
        raise ValueError("AI response must be a JSON object.")
    return parsed


def call_deepseek_json(
    api_key: str,
    model: str,
    prompt: str,
    *,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    timeout_seconds: int = 180,
) -> Dict[str, Any]:
    endpoint = "https://api.deepseek.com/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }

    response = requests.post(endpoint, headers=headers, json=payload, timeout=timeout_seconds)
    response.raise_for_status()
    body = response.json()
    choices = body.get("choices") or []
    if not choices:
        raise ValueError("DeepSeek response missing choices.")
    message = choices[0].get("message") or {}
    return _load_json_object(message.get("content") or "")


def call_ai_json(
    deepseek_api_key: Optional[str],
    deepseek_model: str,
    gemini_client: Optional[genai.Client],
    gemini_model: str,
    prompt: str,
    *,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
) -> Dict[str, Any]:
    parsed = None
    deepseek_error = None
    gemini_error = None

    if deepseek_api_key:
        try:
            parsed = call_deepseek_json(
                api_key=deepseek_api_key,
                model=deepseek_model,
                prompt=prompt,
                system_prompt=system_prompt,
            )
        except Exception as exc:
            deepseek_error = exc

    if parsed is None and gemini_client is not None:
        try:
            response = gemini_client.models.generate_content(
                model=gemini_model,
                contents=prompt,
            )
            parsed = _load_json_object(getattr(response, "text", "") or "")
        except Exception as exc:
            gemini_error = exc

    if parsed is not None:
        return parsed
    if deepseek_error and gemini_error:
        raise RuntimeError(f"DeepSeek and Gemini fallback both failed. DeepSeek={deepseek_error} | Gemini={gemini_error}")
    if deepseek_error:
        raise RuntimeError(f"DeepSeek failed and Gemini fallback is unavailable. DeepSeek={deepseek_error}")
    raise RuntimeError("No Stage 4 AI provider available (DeepSeek/Gemini).")


def _normalize_skills(skills_raw: Any) -> list[str]:
    if isinstance(skills_raw, list):
        return [str(item).strip() for item in skills_raw if str(item).strip()]
    return split_bullets(str(skills_raw))


def _normalize_experiences(experiences_raw: Any) -> list[dict[str, Any]]:
    experiences = []
    if not isinstance(experiences_raw, list):
        return experiences
    for item in experiences_raw:
        if not isinstance(item, dict):
            continue
        role_title = str(item.get("role_title", "")).strip()
        company = str(item.get("company", "")).strip()
        period = str(item.get("period", "")).strip()
        bullets_raw = item.get("bullets", [])
        bullets = [str(b).strip() for b in bullets_raw if str(b).strip()] if isinstance(bullets_raw, list) else split_bullets(str(bullets_raw))
        if role_title or company or period or bullets:
            experiences.append(
                {
                    "role_title": role_title,
                    "company": company,
                    "period": period,
                    "bullets": bullets,
                }
            )
    return experiences


def _normalize_education(education_raw: Any) -> list[dict[str, Any]]:
    education_entries = []
    if not isinstance(education_raw, list):
        return education_entries
    for item in education_raw:
        if not isinstance(item, dict):
            continue
        degree_title = str(item.get("degree_title", "")).strip()
        thesis_title = str(item.get("thesis_title", "")).strip()
        thesis_bullets_raw = item.get("thesis_bullets", [])
        thesis_bullets = (
            [str(b).strip() for b in thesis_bullets_raw if str(b).strip()]
            if isinstance(thesis_bullets_raw, list)
            else split_bullets(str(thesis_bullets_raw))
        )
        if degree_title or thesis_title or thesis_bullets:
            education_entries.append(
                {
                    "degree_title": degree_title,
                    "thesis_title": thesis_title,
                    "thesis_bullets": thesis_bullets,
                }
            )
    return education_entries


def _render_tailored_cv_text(payload: Dict[str, Any]) -> str:
    tailored_cv_lines = [f"Professional Summary: {payload['cv_professional_summary']}", "", "Professional Experience:"]
    for exp in payload["cv_professional_experience"]:
        header_parts = [exp.get("role_title", ""), exp.get("company", ""), exp.get("period", "")]
        line = " | ".join([part for part in header_parts if part])
        if line:
            tailored_cv_lines.append(line)
        for bullet in exp.get("bullets", []):
            tailored_cv_lines.append(f"- {bullet}")
    tailored_cv_lines.append("")
    tailored_cv_lines.append("Skills:")
    tailored_cv_lines.extend([f"- {skill}" for skill in payload["cv_skills"]])
    if payload["cv_education"]:
        tailored_cv_lines.append("")
        tailored_cv_lines.append("Education:")
        for edu in payload["cv_education"]:
            if edu.get("degree_title"):
                tailored_cv_lines.append(str(edu["degree_title"]))
            if edu.get("thesis_title"):
                tailored_cv_lines.append(str(edu["thesis_title"]))
            for bullet in edu.get("thesis_bullets", []):
                tailored_cv_lines.append(f"- {bullet}")
    return "\n".join(line for line in tailored_cv_lines if line is not None).strip()


def _parse_structured_cv_payload(parsed: Dict[str, Any]) -> Dict[str, Any]:
    professional_summary = str(parsed.get("professional_summary", "")).strip()
    skills = _normalize_skills(parsed.get("skills", []))
    experiences = _normalize_experiences(parsed.get("professional_experience", []))
    education_entries = _normalize_education(parsed.get("education", []))

    if not professional_summary or not skills:
        raise ValueError("AI response missing required structured CV fields.")

    payload = {
        "cv_professional_summary": professional_summary,
        "cv_professional_experience": experiences,
        "cv_education": education_entries,
        "cv_skills": skills,
    }
    payload["tailored_cv"] = _render_tailored_cv_text(payload)
    return payload


def _normalize_score_payload(parsed: Dict[str, Any]) -> Dict[str, Any]:
    try:
        score = max(0, min(100, int(parsed.get("score") or 0)))
    except (TypeError, ValueError):
        score = 0
    missing_requirements = _normalize_skills(parsed.get("missing_requirements", []))
    improvement_actions = _normalize_skills(parsed.get("improvement_actions", []))
    rationale = str(parsed.get("rationale", "")).strip()
    return {
        "score": score,
        "missing_requirements": missing_requirements,
        "improvement_actions": improvement_actions,
        "rationale": rationale,
    }


def _structured_cv_for_prompt(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "professional_summary": payload.get("cv_professional_summary", ""),
        "professional_experience": payload.get("cv_professional_experience", []),
        "education": payload.get("cv_education", []),
        "skills": payload.get("cv_skills", []),
    }


def _generate_structured_cv_once(
    deepseek_api_key: Optional[str],
    deepseek_model: str,
    gemini_client: Optional[genai.Client],
    gemini_model: str,
    cv_text: str,
    job: Dict,
    candidate_name: str,
    cv_generation_mode: str,
    extra_instructions: str,
    prompt_override: str,
) -> Dict[str, Any]:
    prompt = build_docs_prompt(
        cv_text=cv_text,
        job=job,
        candidate_name=candidate_name,
        cv_generation_mode=cv_generation_mode,
        extra_instructions=extra_instructions,
        prompt_override=prompt_override,
    )
    parsed = call_ai_json(
        deepseek_api_key,
        deepseek_model,
        gemini_client,
        gemini_model,
        prompt,
    )
    return _parse_structured_cv_payload(parsed)


def _score_structured_cv_once(
    deepseek_api_key: Optional[str],
    deepseek_model: str,
    gemini_client: Optional[genai.Client],
    gemini_model: str,
    cv_text: str,
    job: Dict,
    structured_cv: Dict[str, Any],
) -> Dict[str, Any]:
    prompt = build_ats_score_prompt(cv_text, job, _structured_cv_for_prompt(structured_cv))
    parsed = call_ai_json(
        deepseek_api_key,
        deepseek_model,
        gemini_client,
        gemini_model,
        prompt,
        system_prompt="You are a precise ATS resume reviewer.",
    )
    return _normalize_score_payload(parsed)


def _improve_structured_cv_once(
    deepseek_api_key: Optional[str],
    deepseek_model: str,
    gemini_client: Optional[genai.Client],
    gemini_model: str,
    cv_text: str,
    job: Dict,
    structured_cv: Dict[str, Any],
    score_payload: Dict[str, Any],
    cv_generation_mode: str,
) -> Dict[str, Any]:
    prompt = build_ats_improvement_prompt(
        cv_text=cv_text,
        job=job,
        structured_cv=_structured_cv_for_prompt(structured_cv),
        score_payload=score_payload,
        cv_generation_mode=cv_generation_mode,
    )
    parsed = call_ai_json(
        deepseek_api_key,
        deepseek_model,
        gemini_client,
        gemini_model,
        prompt,
    )
    return _parse_structured_cv_payload(parsed)


def _attempt_history_entry(attempt_number: int, score_payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "attempt": attempt_number,
        "score": int(score_payload.get("score") or 0),
        "missing_requirements": list(score_payload.get("missing_requirements") or []),
        "improvement_actions": list(score_payload.get("improvement_actions") or []),
        "rationale": str(score_payload.get("rationale") or ""),
    }


def _attach_ats_metadata(
    payload: Dict[str, Any],
    *,
    best_score: int,
    best_missing_requirements: list[str],
    attempt_count: int,
    stop_reason: str,
    attempt_history: list[Dict[str, Any]],
    best_attempt_index: int,
) -> Dict[str, Any]:
    gate = evaluate_ats_export_gate(
        {
            "target_score": ATS_TARGET_SCORE,
            "best_score": best_score,
            "attempt_count": attempt_count,
            "max_attempts": ATS_MAX_ATTEMPTS,
            "missing_requirements": best_missing_requirements,
            "metadata": {
                "stop_reason": stop_reason,
                "attempt_history": attempt_history,
                "best_attempt_index": best_attempt_index,
            },
        }
    )
    return {
        **payload,
        "ats_score": best_score,
        "ats_best_score": best_score,
        "ats_target_score": gate["target_score"],
        "ats_attempt_count": gate["attempt_count"],
        "ats_max_attempts": gate["max_attempts"],
        "ats_missing_requirements": list(gate["missing_requirements"]),
        "missing_requirements": list(gate["missing_requirements"]),
        "ats_gate_state": gate["gate_state"],
        "ats_can_export_final": gate["can_export_final"],
        "ats_export_anyway_allowed": gate["export_anyway_allowed"],
        "ats_last_warning": gate["last_warning"],
        "ats_stop_reason": stop_reason,
        "ats_attempt_history": attempt_history,
        "ats_export_gate": gate,
    }


def _generate_docs_for_job_once(
    deepseek_api_key: Optional[str],
    deepseek_model: str,
    gemini_client: Optional[genai.Client],
    gemini_model: str,
    cv_text: str,
    job: Dict,
    candidate_name: str,
    cv_generation_mode: str,
    extra_instructions: str,
    prompt_override: str,
    payload_postprocessor: Callable[[Dict[str, Any]], Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    current_payload = _generate_structured_cv_once(
        deepseek_api_key,
        deepseek_model,
        gemini_client,
        gemini_model,
        cv_text,
        job,
        candidate_name,
        cv_generation_mode,
        extra_instructions,
        prompt_override,
    )
    if callable(payload_postprocessor):
        current_payload = payload_postprocessor(current_payload)
    best_payload = current_payload
    best_score = -1
    best_missing_requirements: list[str] = []
    best_attempt_index = 0
    attempt_history: list[Dict[str, Any]] = []
    previous_score: Optional[int] = None
    stop_reason = "max_attempts_reached"

    for attempt_number in range(1, ATS_MAX_ATTEMPTS + 1):
        score_payload = _score_structured_cv_once(
            deepseek_api_key,
            deepseek_model,
            gemini_client,
            gemini_model,
            cv_text,
            job,
            current_payload,
        )
        attempt_history.append(_attempt_history_entry(attempt_number, score_payload))
        current_score = int(score_payload["score"])

        if current_score > best_score:
            best_score = current_score
            best_payload = current_payload
            best_missing_requirements = list(score_payload["missing_requirements"])
            best_attempt_index = attempt_number

        if current_score >= ATS_TARGET_SCORE:
            stop_reason = "target_reached"
            break
        if attempt_number >= ATS_MAX_ATTEMPTS:
            stop_reason = "max_attempts_reached"
            break
        if previous_score is not None and current_score <= previous_score:
            stop_reason = "score_stalled"
            break

        previous_score = current_score
        current_payload = _improve_structured_cv_once(
            deepseek_api_key,
            deepseek_model,
            gemini_client,
            gemini_model,
            cv_text,
            job,
            current_payload,
            score_payload,
            cv_generation_mode,
        )
        if callable(payload_postprocessor):
            current_payload = payload_postprocessor(current_payload)

    return _attach_ats_metadata(
        best_payload,
        best_score=max(0, best_score),
        best_missing_requirements=best_missing_requirements,
        attempt_count=len(attempt_history),
        stop_reason=stop_reason,
        attempt_history=attempt_history,
        best_attempt_index=best_attempt_index,
    )


def generate_docs_for_job(
    deepseek_api_key: Optional[str],
    deepseek_model: str,
    gemini_client: Optional[genai.Client],
    gemini_model: str,
    cv_text: str,
    job: Dict,
    candidate_name: str,
    cv_generation_mode: str,
    extra_instructions: str,
    prompt_override: str,
    retries: int,
    retry_sleep: float,
    payload_postprocessor: Callable[[Dict[str, Any]], Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            return _generate_docs_for_job_once(
                deepseek_api_key=deepseek_api_key,
                deepseek_model=deepseek_model,
                gemini_client=gemini_client,
                gemini_model=gemini_model,
                cv_text=cv_text,
                job=job,
                candidate_name=candidate_name,
                cv_generation_mode=cv_generation_mode,
                extra_instructions=extra_instructions,
                prompt_override=prompt_override,
                payload_postprocessor=payload_postprocessor,
            )
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                wait_seconds = retry_sleep * attempt
                print(f"Retry {attempt}/{retries - 1} for job {job.get('job_id')} after error: {exc}")
                time.sleep(wait_seconds)

    raise RuntimeError(f"Document generation failed after {retries} attempts: {last_error}")
