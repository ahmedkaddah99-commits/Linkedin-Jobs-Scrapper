import json
import re
import time
from typing import Dict, Optional

from google import genai
import requests

from .common import compact_whitespace, strip_json_fences


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
        r"(?i)\blocation:\s*([A-Za-zÃ„Ã–ÃœÃ¤Ã¶Ã¼ÃŸ\- ]+),\s*(?:[A-Za-zÃ„Ã–ÃœÃ¤Ã¶Ã¼ÃŸ\- ]+\s*-\s*)?Germany\b",
        r"(?i)\bbased in\s+([A-Za-zÃ„Ã–ÃœÃ¤Ã¶Ã¼ÃŸ\- ]+)\b",
        r"(?i)\bin\s+([A-Za-zÃ„Ã–ÃœÃ¤Ã¶Ã¼ÃŸ\- ]+),\s*Germany\b",
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


def build_docs_prompt(
    cv_text: str,
    job: Dict,
    candidate_name: str,
    extra_instructions: str = "",
    prompt_override: str = "",
) -> str:
    description_excerpt = str(job.get("full_description") or "")[:6000]
    job_id = str(job.get("job_id", ""))
    title = str(job.get("title", ""))
    company = str(job.get("company", ""))
    job_city = extract_city_from_job(job)

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
        prompt = f"""
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
{{
  "professional_summary": "text",
  "professional_experience": [
    {{
      "role_title": "text",
      "company": "text",
      "period": "text",
      "bullets": ["text", "text"]
    }}
  ],
  "education": [
    {{
      "degree_title": "text",
      "thesis_title": "text",
      "thesis_bullets": ["text", "text"]
    }}
  ],
  "skills": ["text", "text"]
}}

Content rules:
- professional_summary:
  - detailed and substantial (about 70-140 words)
  - role-specific and company-specific
  - naturally professional, non-generic
  - clearly explain why the candidate is a strong fit
- professional_experience:
  - use only roles that exist in the candidate CV
  - keep role titles exactly as written in the candidate CV
  - preserve the same role order as in the candidate CV
  - 3 to 6 roles total
  - each role has 3 to 5 concise achievement-oriented bullets
  - tailor bullets to the target role and ATS keywords
  - do not fabricate companies or dates
  - if Allianz Technology appears in the CV, include it explicitly
  - never include projects/initiatives in this section
- skills:
  - 16 to 25 ATS-friendly skills relevant to the job description
  - include realistic adjacent skills when useful
- if referencing EDUCATION content from the candidate CV:
  - keep degree/thesis titles exactly as written in the CV
  - do not rename or paraphrase degree/thesis titles
  - preserve the same education item order as in the candidate CV
  - you may only reword thesis bullet wording to fit the target role
  - if referencing PROJECTS from the candidate CV:
  - keep project titles exactly as written in the CV
  - preserve the same project order as in the candidate CV
  - only reword supporting bullet wording to better match the target job
  - never include professional job roles in this section
Do not produce a motivation letter, cover letter, greeting, or signature.
""".strip()
    if extra_instructions:
        prompt = f"{prompt}\n\nAdditional user preferences:\n{extra_instructions.strip()}"
    return prompt


def call_deepseek_json(
    api_key: str,
    model: str,
    prompt: str,
    timeout_seconds: int = 180,
) -> Dict:
    endpoint = "https://api.deepseek.com/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are an expert career writing assistant."},
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
    content = message.get("content") or ""
    return json.loads(strip_json_fences(str(content)))


def generate_docs_for_job(
    deepseek_api_key: Optional[str],
    deepseek_model: str,
    gemini_client: Optional[genai.Client],
    gemini_model: str,
    cv_text: str,
    job: Dict,
    candidate_name: str,
    extra_instructions: str,
    prompt_override: str,
    retries: int,
    retry_sleep: float,
) -> Dict:
    prompt = build_docs_prompt(
        cv_text=cv_text,
        job=job,
        candidate_name=candidate_name,
        extra_instructions=extra_instructions,
        prompt_override=prompt_override,
    )
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            parsed = None
            deepseek_error = None
            gemini_error = None

            if deepseek_api_key:
                try:
                    parsed = call_deepseek_json(
                        api_key=deepseek_api_key,
                        model=deepseek_model,
                        prompt=prompt,
                    )
                except Exception as exc:
                    deepseek_error = exc
                    print(
                        f"DeepSeek failed for job {job.get('job_id')} (attempt {attempt}/{retries}): {exc}. "
                        "Trying Gemini fallback."
                    )

            if parsed is None and gemini_client is not None:
                try:
                    response = gemini_client.models.generate_content(
                        model=gemini_model,
                        contents=prompt,
                    )
                    text = getattr(response, "text", "") or ""
                    parsed = json.loads(strip_json_fences(text))
                except Exception as exc:
                    gemini_error = exc

            if parsed is None:
                if deepseek_error and gemini_error:
                    raise RuntimeError(
                        f"DeepSeek and Gemini fallback both failed. DeepSeek={deepseek_error} | Gemini={gemini_error}"
                    )
                if deepseek_error:
                    raise RuntimeError(f"DeepSeek failed and Gemini fallback is unavailable. DeepSeek={deepseek_error}")
                raise RuntimeError("No Stage 4 AI provider available (DeepSeek/Gemini).")

            professional_summary = str(parsed.get("professional_summary", "")).strip()
            skills_raw = parsed.get("skills", [])
            experiences_raw = parsed.get("professional_experience", [])
            education_raw = parsed.get("education", [])

            if isinstance(skills_raw, list):
                skills = [str(item).strip() for item in skills_raw if str(item).strip()]
            else:
                skills = split_bullets(str(skills_raw))

            experiences = []
            if isinstance(experiences_raw, list):
                for item in experiences_raw:
                    if not isinstance(item, dict):
                        continue
                    role_title = str(item.get("role_title", "")).strip()
                    company = str(item.get("company", "")).strip()
                    period = str(item.get("period", "")).strip()
                    bullets_raw = item.get("bullets", [])
                    if isinstance(bullets_raw, list):
                        bullets = [str(b).strip() for b in bullets_raw if str(b).strip()]
                    else:
                        bullets = split_bullets(str(bullets_raw))
                    if role_title or company or period or bullets:
                        experiences.append(
                            {
                                "role_title": role_title,
                                "company": company,
                                "period": period,
                                "bullets": bullets,
                            }
                        )

            education_entries = []
            if isinstance(education_raw, list):
                for item in education_raw:
                    if not isinstance(item, dict):
                        continue
                    degree_title = str(item.get("degree_title", "")).strip()
                    thesis_title = str(item.get("thesis_title", "")).strip()
                    thesis_bullets_raw = item.get("thesis_bullets", [])
                    if isinstance(thesis_bullets_raw, list):
                        thesis_bullets = [str(b).strip() for b in thesis_bullets_raw if str(b).strip()]
                    else:
                        thesis_bullets = split_bullets(str(thesis_bullets_raw))
                    if degree_title or thesis_title or thesis_bullets:
                        education_entries.append(
                            {
                                "degree_title": degree_title,
                                "thesis_title": thesis_title,
                                "thesis_bullets": thesis_bullets,
                            }
                        )

            if not professional_summary or not skills or not experiences:
                raise ValueError("AI response missing required structured CV fields.")

            tailored_cv_lines = [f"Professional Summary: {professional_summary}", "", "Professional Experience:"]
            for exp in experiences:
                header_parts = [exp.get("role_title", ""), exp.get("company", ""), exp.get("period", "")]
                line = " | ".join([part for part in header_parts if part])
                if line:
                    tailored_cv_lines.append(line)
                for bullet in exp.get("bullets", []):
                    tailored_cv_lines.append(f"- {bullet}")
            tailored_cv_lines.append("")
            tailored_cv_lines.append("Skills:")
            tailored_cv_lines.extend([f"- {skill}" for skill in skills])
            if education_entries:
                tailored_cv_lines.append("")
                tailored_cv_lines.append("Education:")
                for edu in education_entries:
                    if edu.get("degree_title"):
                        tailored_cv_lines.append(str(edu["degree_title"]))
                    if edu.get("thesis_title"):
                        tailored_cv_lines.append(str(edu["thesis_title"]))
                    for bullet in edu.get("thesis_bullets", []):
                        tailored_cv_lines.append(f"- {bullet}")

            return {
                "cv_professional_summary": professional_summary,
                "cv_professional_experience": experiences,
                "cv_education": education_entries,
                "cv_skills": skills,
                "tailored_cv": "\n".join(line for line in tailored_cv_lines if line is not None).strip(),
            }
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                wait_seconds = retry_sleep * attempt
                print(f"Retry {attempt}/{retries - 1} for job {job.get('job_id')} after error: {exc}")
                time.sleep(wait_seconds)

    raise RuntimeError(f"Document generation failed after {retries} attempts: {last_error}")
