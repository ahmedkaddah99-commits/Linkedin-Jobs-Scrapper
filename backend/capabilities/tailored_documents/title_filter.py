import json
import re

import requests as std_requests

from backend.domain.phase0_contracts import (
    JOB_FILTERING_MODE_BROADER,
    JOB_FILTERING_MODE_STRICT,
    normalize_job_filtering_mode,
)


_NON_ALPHANUMERIC_PATTERN = re.compile(r"[^a-z0-9]+")


def extract_first_json_object(text: str) -> str:
    payload = text or ""
    start = payload.find("{")
    if start < 0:
        return ""

    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(payload[start:], start=start):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
            continue
        if char == "}":
            depth -= 1
            if depth == 0:
                return payload[start : index + 1]

    return ""


def parse_ai_filter_payload(raw_content: str) -> dict:
    content = (raw_content or "").strip()
    cleaned = content.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    candidates = [cleaned]

    extracted = extract_first_json_object(cleaned)
    if extracted and extracted != cleaned:
        candidates.append(extracted)

    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            continue

    approved_ids: list[str] = []
    approved_match = re.search(r'"approved_ids"\s*:\s*\[(.*?)\]', cleaned, re.DOTALL)
    if approved_match:
        approved_ids = re.findall(r'"(\d+)"|\b(\d+)\b', approved_match.group(1))
        approved_ids = [left or right for left, right in approved_ids if (left or right)]

    excluded_items = []
    excluded_match = re.search(r'"excluded"\s*:\s*\[(.*?)\]', cleaned, re.DOTALL)
    if excluded_match:
        for item_id, reason in re.findall(
            r'"id"\s*:\s*"?(.*?)"?\s*,\s*"reason"\s*:\s*"(.*?)"',
            excluded_match.group(1),
            re.DOTALL,
        ):
            excluded_items.append({"id": str(item_id).strip(), "reason": str(reason).strip()})

    if approved_ids or excluded_items:
        print("[Stage1] warning: recovered partial AI JSON using fallback parser.")
        return {"approved_ids": approved_ids, "excluded": excluded_items}

    preview = cleaned[:280].replace("\n", "\\n")
    raise ValueError(f"Unable to parse AI JSON payload. Preview={preview}")


def call_deepseek_title_filter(api_key: str, model: str, prompt: str):
    endpoint = "https://api.deepseek.com/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are an expert career assistant."},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }
    response = std_requests.post(endpoint, headers=headers, json=payload, timeout=120)
    response.raise_for_status()
    body = response.json()
    choices = body.get("choices") or []
    if not choices:
        raise ValueError("DeepSeek response missing choices")
    message = choices[0].get("message") or {}
    content = (message.get("content") or "").strip()
    return parse_ai_filter_payload(content)


def _normalize_phrase(text: str) -> str:
    tokens = [token for token in _NON_ALPHANUMERIC_PATTERN.split(str(text or "").casefold()) if token]
    return " ".join(tokens)


def _dedupe_phrases(phrases) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for phrase in phrases or []:
        normalized = _normalize_phrase(str(phrase or ""))
        if not normalized or normalized in seen:
            continue
        deduped.append(str(phrase).strip())
        seen.add(normalized)
    return deduped


def _title_contains_phrase(title: str, phrase: str) -> bool:
    normalized_title = _normalize_phrase(title)
    normalized_phrase = _normalize_phrase(phrase)
    if not normalized_title or not normalized_phrase:
        return False
    return f" {normalized_phrase} " in f" {normalized_title} "


def _prefilter_jobs_by_title_connection(
    jobs_list,
    *,
    job_filtering_mode: str,
    job_filtering_target_phrases,
    broader_keywords,
):
    normalized_mode = normalize_job_filtering_mode(job_filtering_mode)
    strict_phrases = _dedupe_phrases(job_filtering_target_phrases)
    if not strict_phrases:
        strict_phrases = _dedupe_phrases(broader_keywords)
    broader_phrases = _dedupe_phrases([*strict_phrases, *(broader_keywords or [])])
    active_phrases = strict_phrases if normalized_mode == JOB_FILTERING_MODE_STRICT else broader_phrases
    if not active_phrases:
        return {
            "mode": normalized_mode,
            "matching_jobs": list(jobs_list),
            "excluded_jobs": [],
            "strict_phrases": strict_phrases,
            "broader_phrases": broader_phrases,
        }

    matching_jobs = []
    excluded_jobs = []
    excluded_reason = (
        "Title does not match saved target roles or keywords."
        if normalized_mode == JOB_FILTERING_MODE_STRICT
        else "Title has no clear connection to saved target roles or keywords."
    )
    for job in jobs_list:
        title = str(job.get("title") or "")
        if any(_title_contains_phrase(title, phrase) for phrase in active_phrases):
            matching_jobs.append(job)
            continue
        excluded_jobs.append({**job, "reason": excluded_reason})
    return {
        "mode": normalized_mode,
        "matching_jobs": matching_jobs,
        "excluded_jobs": excluded_jobs,
        "strict_phrases": strict_phrases,
        "broader_phrases": broader_phrases,
    }


def _filter_with_ai_batches(
    jobs_list,
    *,
    deepseek_api_key: str,
    cv_summary: str,
    model: str,
    extra_instructions: str = "",
    prompt_override: str = "",
    ai_batch_size: int = 30,
    prompt_context: str = "",
):
    if not jobs_list:
        return [], []

    safe_batch_size = max(1, int(ai_batch_size))
    total_jobs = len(jobs_list)
    total_batches = (total_jobs + safe_batch_size - 1) // safe_batch_size
    print(
        f"[Stage1] sending job titles to AI filter in batches "
        f"(batch_size={safe_batch_size}, total_jobs={total_jobs}, batches={total_batches})"
    )

    all_approved_ids: set[str] = set()
    excluded_map: dict[str, str] = {}

    for batch_index in range(total_batches):
        start = batch_index * safe_batch_size
        end = min(start + safe_batch_size, total_jobs)
        batch_jobs = jobs_list[start:end]
        print(f"[Stage1] AI title filter batch {batch_index + 1}/{total_batches}: jobs {start + 1}-{end}")

        job_inventory = "\n".join(
            [f"ID: {job['job_id']} | Title: {job['title']} | Company: {job['company']}" for job in batch_jobs]
        )

        if prompt_override.strip():
            prompt = (
                prompt_override.strip()
                .replace("{{CV_SUMMARY}}", cv_summary)
                .replace("{{JOB_LIST}}", job_inventory)
            )
        else:
            prompt = f"""
You are an expert career assistant. I will give you my CV summary and a list of job titles.

MY CV SUMMARY:
{cv_summary}

JOB LIST:
{job_inventory}

{prompt_context}

YOUR TASK:
Evaluate every job in the list.

Rules:
- APPROVE a job ONLY IF:
  1) The title is written in English
  2) The title is relevant to my CV (Business Transformation, AI, Project/Product Management, Consulting, Data/Business Analysis)

OUTPUT FORMAT (IMPORTANT):
Return ONLY raw JSON (no markdown, no extra text), shaped EXACTLY like this:

{{
  "approved_ids": ["123", "456"],
  "excluded": [
    {{
      "id": "789",
      "reason": "German title"
    }},
    {{
      "id": "1011",
      "reason": "Not relevant"
    }},
    {{
      "id": "1213",
      "reason": "German title + Not relevant"
    }}
  ]
}}
""".strip()
        if extra_instructions:
            prompt = f"{prompt}\n\nAdditional user preferences:\n{extra_instructions.strip()}"

        parsed = None
        attempts = [
            prompt,
            (
                f"{prompt}\n\n"
                "Return strict JSON only. Ensure valid escaping for all strings. "
                "Do not include markdown fences or commentary."
            ),
        ]
        for attempt_index, attempt_prompt in enumerate(attempts, start=1):
            try:
                parsed = call_deepseek_title_filter(
                    api_key=deepseek_api_key,
                    model=model,
                    prompt=attempt_prompt,
                )
                break
            except Exception as exc:
                if attempt_index == len(attempts):
                    print(
                        f"[Stage1] AI filtering failed for batch {batch_index + 1}/{total_batches}: {exc}. "
                        "Marking this batch as excluded."
                    )
                    parsed = {
                        "approved_ids": [],
                        "excluded": [
                            {
                                "id": str(job["job_id"]),
                                "reason": "AI filter failed (invalid/truncated response)",
                            }
                            for job in batch_jobs
                        ],
                    }
                else:
                    print(
                        f"[Stage1] AI JSON parse failed in batch {batch_index + 1}/{total_batches} "
                        f"(attempt {attempt_index}/{len(attempts)}): {exc}. Retrying..."
                    )

        batch_approved_ids = {str(item) for item in parsed.get("approved_ids", [])}
        all_approved_ids.update(batch_approved_ids)
        for item in parsed.get("excluded", []):
            if isinstance(item, dict) and item.get("id") is not None:
                excluded_map[str(item.get("id"))] = item.get("reason", "Excluded")

    approved_jobs = [job for job in jobs_list if str(job["job_id"]) in all_approved_ids]
    excluded_jobs = []
    for job in jobs_list:
        if str(job["job_id"]) not in all_approved_ids:
            excluded_jobs.append({**job, "reason": excluded_map.get(str(job["job_id"]), "Excluded by DeepSeek")})
    return approved_jobs, excluded_jobs


def filter_with_ai(
    jobs_list,
    deepseek_api_key: str,
    cv_summary: str,
    model: str,
    excluded_output: str,
    extra_instructions: str = "",
    prompt_override: str = "",
    ai_batch_size: int = 30,
    job_filtering_mode: str = JOB_FILTERING_MODE_BROADER,
    job_filtering_target_phrases=None,
    broader_keywords=None,
):
    if not jobs_list:
        return [], []

    prefilter_result = _prefilter_jobs_by_title_connection(
        jobs_list,
        job_filtering_mode=job_filtering_mode,
        job_filtering_target_phrases=job_filtering_target_phrases,
        broader_keywords=broader_keywords,
    )
    filtered_jobs = prefilter_result["matching_jobs"]
    prefiltered_excluded_jobs = prefilter_result["excluded_jobs"]
    normalized_mode = prefilter_result["mode"]
    if prefiltered_excluded_jobs:
        print(
            f"[Stage1] {normalized_mode} prefilter excluded {len(prefiltered_excluded_jobs)} / {len(jobs_list)} jobs "
            "before AI screening."
        )

    if normalized_mode == JOB_FILTERING_MODE_STRICT:
        with open(excluded_output, "w", encoding="utf-8") as file:
            json.dump(prefiltered_excluded_jobs, file, indent=4, ensure_ascii=False)
        print(f"[Stage1] strict title filter approved {len(filtered_jobs)} / {len(jobs_list)}")
        print(f"[Stage1] wrote strict-match excluded jobs to {excluded_output}")
        return filtered_jobs, prefiltered_excluded_jobs

    explicit_targets = prefilter_result["strict_phrases"]
    broader_targets = prefilter_result["broader_phrases"]
    if explicit_targets:
        explicit_targets_block = "\n".join(f"- {phrase}" for phrase in explicit_targets)
    else:
        explicit_targets_block = "- None supplied"
    broader_targets_block = "\n".join(f"- {phrase}" for phrase in broader_targets) if broader_targets else "- None supplied"
    prompt_context = f"""
SAVED TARGET ROLES AND KEYWORDS:
{explicit_targets_block}

CONNECTED TITLE PHRASES:
{broader_targets_block}

TITLE MATCH RULES:
- APPROVE only if the title stays concretely connected to the saved targets or connected title phrases above.
- Adjacent roles are allowed when the title still stays clearly connected to those saved targets.
- Broad CV relevance alone is not enough.
""".strip()

    ai_approved_jobs, ai_excluded_jobs = _filter_with_ai_batches(
        filtered_jobs,
        deepseek_api_key=deepseek_api_key,
        cv_summary=cv_summary,
        model=model,
        extra_instructions=extra_instructions,
        prompt_override=prompt_override,
        ai_batch_size=ai_batch_size,
        prompt_context=prompt_context,
    )
    excluded_jobs = [*prefiltered_excluded_jobs, *ai_excluded_jobs]

    with open(excluded_output, "w", encoding="utf-8") as file:
        json.dump(excluded_jobs, file, indent=4, ensure_ascii=False)

    print(f"[Stage1] AI approved {len(ai_approved_jobs)} / {len(jobs_list)}")
    print(f"[Stage1] wrote AI excluded jobs to {excluded_output}")
    return ai_approved_jobs, excluded_jobs
