from __future__ import annotations

import json
import os
import re
import time
from types import SimpleNamespace
from typing import Any, Dict, List, Mapping, Tuple

import requests
from dotenv import load_dotenv

from .support import (
    cfg_int,
    cfg_list,
    cfg_str,
    compact_whitespace,
    load_reusable_packages_config,
    load_json_file,
    resolve_path,
    save_json_file,
)


TITLE_NORMALIZATION_PATTERNS = [
    re.compile(r"\b(m/w/d|w/m/d|d/m/w|all genders)\b", re.IGNORECASE),
    re.compile(r"\([^)]*\)"),
    re.compile(r"[^a-zA-Z0-9\s]"),
    re.compile(r"\s+"),
]


def normalize_role_title(title: str) -> str:
    normalized = title or ""
    normalized = normalized.replace("Ã¤", "ae").replace("Ã¶", "oe").replace("Ã¼", "ue").replace("ÃŸ", "ss")
    for pattern in TITLE_NORMALIZATION_PATTERNS:
        normalized = pattern.sub(" ", normalized)
    return compact_whitespace(normalized.lower())


def cluster_jobs_by_role(jobs: List[Dict]) -> Tuple[List[Dict], Dict[str, List[Dict]]]:
    by_cluster: Dict[str, List[Dict]] = {}
    for job in jobs:
        normalized = normalize_role_title(str(job.get("title") or ""))
        cluster_id = normalized or f"cluster_{str(job.get('job_id') or '').strip()}"
        by_cluster.setdefault(cluster_id, []).append(job)

    clusters: List[Dict] = []
    for cluster_id, cluster_jobs in by_cluster.items():
        sample = cluster_jobs[0]
        combined = " ".join(
            compact_whitespace(
                " ".join(
                    [
                        str(item.get("title") or ""),
                        str(item.get("description") or ""),
                        str(item.get("snippet") or ""),
                    ]
                )
            )
            for item in cluster_jobs[:4]
        )
        clusters.append(
            {
                "cluster_id": cluster_id,
                "job_count": len(cluster_jobs),
                "sample_title": str(sample.get("title") or ""),
                "sample_company": str(sample.get("company") or ""),
                "sample_location": str(sample.get("location_raw") or ""),
                "sample_text": combined[:1500],
            }
        )

    clusters.sort(key=lambda item: (-int(item.get("job_count") or 0), str(item.get("cluster_id") or "")))
    return clusters, by_cluster


def strip_json_fences(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```").strip()
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()
    return cleaned


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


def parse_assignments_json(raw_content: str) -> Dict:
    cleaned = strip_json_fences(raw_content)
    candidates = [cleaned]
    extracted = extract_first_json_object(cleaned)
    if extracted and extracted != cleaned:
        candidates.append(extracted)

    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("Failed to parse AI classification JSON.")


def build_classification_prompt(
    categories: List[Dict],
    clusters: List[Dict],
    extra_instructions: str = "",
    prompt_override: str = "",
) -> str:
    categories_lines = [
        f"- id={item.get('id')} | name={item.get('name')} | description={item.get('description')} "
        f"| keywords={','.join(item.get('keywords') or [])}"
        for item in categories
    ]
    cluster_lines = [
        f"- cluster_id={cluster['cluster_id']} | title={cluster['sample_title']} | count={cluster['job_count']} "
        f"| sample_company={cluster['sample_company']} | sample_text={cluster['sample_text'][:240]}"
        for cluster in clusters
    ]

    if prompt_override.strip():
        prompt = (
            prompt_override.strip()
            .replace("{{CATEGORIES}}", "\n".join(categories_lines))
            .replace("{{CLUSTERS}}", "\n".join(cluster_lines))
        )
    else:
        prompt = f"""
You classify grouped operational job role clusters into a fixed category list.

Categories:
{chr(10).join(categories_lines)}

Role clusters:
{chr(10).join(cluster_lines)}

Rules:
- Use only category ids from the provided list.
- Exactly one category_id per cluster_id.
- Prefer "other_operational" only when none of the specific categories fit.

Return strict JSON only with this schema:
{{
  "assignments": [
    {{
      "cluster_id": "text",
      "category_id": "text",
      "confidence": "high|medium|low",
      "reason": "short reason"
    }}
  ]
}}
""".strip()

    if extra_instructions:
        prompt = f"{prompt}\n\nAdditional user preferences:\n{extra_instructions.strip()}"
    return prompt


def call_deepseek_classification(api_key: str, model: str, prompt: str) -> Dict:
    session = requests.Session()
    session.trust_env = False
    response = session.post(
        "https://api.deepseek.com/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": "You classify operational job role clusters."},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
        },
        timeout=120,
    )
    response.raise_for_status()
    body = response.json()
    choices = body.get("choices") or []
    if not choices:
        raise ValueError("DeepSeek response has no choices.")
    content = str((choices[0].get("message") or {}).get("content") or "")
    return parse_assignments_json(content)


def keyword_classify(cluster: Dict, categories: List[Dict]) -> Tuple[str, str]:
    text = normalize_role_title(" ".join([str(cluster.get("sample_title") or ""), str(cluster.get("sample_text") or "")]))
    best_category = "other_operational"
    best_score = 0
    for category in categories:
        category_id = str(category.get("id") or "").strip()
        keywords = [normalize_role_title(str(item)) for item in category.get("keywords") or [] if str(item).strip()]
        if not category_id or not keywords:
            continue
        score = sum(1 for keyword in keywords if keyword and keyword in text)
        if score > best_score:
            best_score = score
            best_category = category_id
    if best_score == 0:
        return "other_operational", "Keyword fallback: no strong keyword hit."
    return best_category, f"Keyword fallback matched {best_score} category keywords."


def classify_clusters_with_minimal_ai(
    clusters: List[Dict],
    categories: List[Dict],
    model: str,
    batch_size: int,
    retries: int,
    retry_sleep_seconds: float,
    extra_instructions: str = "",
    prompt_override: str = "",
) -> Dict[str, Dict]:
    load_dotenv()
    api_key = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
    valid_category_ids = {str(item.get("id") or "") for item in categories}
    assigned: Dict[str, Dict] = {}
    if not clusters:
        return assigned

    use_ai = bool(api_key)
    if not use_ai:
        print("[Stage3] DEEPSEEK_API_KEY missing, using keyword fallback classification only.")

    for start in range(0, len(clusters), max(1, int(batch_size))):
        batch = clusters[start : start + max(1, int(batch_size))]
        if use_ai:
            prompt = build_classification_prompt(categories, batch, extra_instructions, prompt_override)
            parsed = None
            for attempt in range(1, max(1, int(retries)) + 1):
                try:
                    parsed = call_deepseek_classification(api_key=api_key, model=model, prompt=prompt)
                    break
                except Exception as exc:
                    if attempt >= max(1, int(retries)):
                        print(f"[Stage3] AI classification batch failed after retries: {exc}")
                    else:
                        wait_seconds = max(0.0, float(retry_sleep_seconds)) * attempt
                        print(f"[Stage3] AI classification retry {attempt}: {exc}")
                        if wait_seconds > 0:
                            time.sleep(wait_seconds)

            if parsed and isinstance(parsed.get("assignments"), list):
                for item in parsed["assignments"]:
                    if not isinstance(item, dict):
                        continue
                    cluster_id = str(item.get("cluster_id") or "").strip()
                    category_id = str(item.get("category_id") or "").strip()
                    confidence = str(item.get("confidence") or "").strip().lower() or "medium"
                    reason = compact_whitespace(str(item.get("reason") or ""))
                    if not cluster_id:
                        continue
                    if category_id not in valid_category_ids:
                        category_id = "other_operational"
                        reason = f"{reason} Invalid category from AI; fallback to other_operational.".strip()
                    assigned[cluster_id] = {
                        "category_id": category_id,
                        "confidence": confidence,
                        "reason": reason,
                        "source": "ai_cluster",
                    }

        for cluster in batch:
            cluster_id = str(cluster.get("cluster_id") or "").strip()
            if not cluster_id or cluster_id in assigned:
                continue
            fallback_category, fallback_reason = keyword_classify(cluster=cluster, categories=categories)
            assigned[cluster_id] = {
                "category_id": fallback_category,
                "confidence": "medium",
                "reason": fallback_reason,
                "source": "keyword_fallback",
            }
    return assigned


def build_stage3_args(config: dict | None = None, overrides: Mapping[str, Any] | None = None) -> SimpleNamespace:
    config = config or load_reusable_packages_config()
    payload = {
        "input": cfg_str(config, ("runtime", "stage3", "input_json"), "outputs/stage2_filtered_jobs.json"),
        "output": cfg_str(config, ("runtime", "stage3", "output_json"), "outputs/stage3_classified_jobs.json"),
        "clusters_output": cfg_str(config, ("runtime", "stage3", "role_clusters_json"), "outputs/stage3_role_clusters.json"),
        "model": cfg_str(config, ("ai", "models", "role_classifier"), "deepseek-chat"),
        "batch_size": max(1, cfg_int(config, ("runtime", "stage3", "batch_size"), 50)),
        "retries": max(1, cfg_int(config, ("runtime", "stage3", "retries"), 3)),
        "retry_sleep_seconds": max(0.0, float(cfg_int(config, ("runtime", "stage3", "retry_sleep_seconds"), 2))),
        "extra_prompt": cfg_str(config, ("ai", "prompts", "role_classifier_extra_instructions"), ""),
        "prompt_override": cfg_str(config, ("ai", "prompts", "role_classifier_prompt_override"), ""),
        "categories": cfg_list(config, ("classification", "categories"), []),
    }
    if overrides:
        payload.update({key: value for key, value in overrides.items() if value is not None})
    return SimpleNamespace(**payload)


def run_stage3_pipeline(args, *, config: dict | None = None, jobs: List[Dict] | None = None) -> dict[str, Any]:
    _ = config
    input_path = resolve_path(args.input)
    if jobs is None:
        if not input_path.exists():
            raise FileNotFoundError(f"input file not found: {input_path}")
        jobs = load_json_file(input_path)
        if not isinstance(jobs, list):
            raise ValueError("input JSON must be a list of jobs.")

    categories = [item for item in (getattr(args, "categories", None) or []) if isinstance(item, dict) and item.get("id")]
    if not categories:
        raise ValueError("no classification categories configured.")

    categories_by_id = {str(item["id"]): item for item in categories}
    clusters, by_cluster = cluster_jobs_by_role(jobs)
    assignments = classify_clusters_with_minimal_ai(
        clusters=clusters,
        categories=categories,
        model=args.model,
        batch_size=max(1, int(args.batch_size)),
        retries=max(1, int(args.retries)),
        retry_sleep_seconds=max(0.0, float(args.retry_sleep_seconds)),
        extra_instructions=args.extra_prompt,
        prompt_override=args.prompt_override,
    )

    classified_jobs: List[Dict] = []
    cluster_records: List[Dict] = []
    for cluster in clusters:
        cluster_id = str(cluster.get("cluster_id") or "")
        assignment = assignments.get(cluster_id, {})
        category_id = str(assignment.get("category_id") or "other_operational")
        category = categories_by_id.get(category_id) or categories_by_id.get("other_operational", {})
        category_name = str(category.get("name") or "Other Operational")
        source = str(assignment.get("source") or "keyword_fallback")
        reason = str(assignment.get("reason") or "")
        confidence = str(assignment.get("confidence") or "medium")

        cluster_records.append(
            {
                **cluster,
                "category_id": category_id,
                "category_name": category_name,
                "classification_source": source,
                "classification_confidence": confidence,
                "classification_reason": reason,
            }
        )
        for job in by_cluster.get(cluster_id, []):
            classified_jobs.append(
                {
                    **job,
                    "role_cluster_id": cluster_id,
                    "role_category_id": category_id,
                    "role_category_name": category_name,
                    "classification_source": source,
                    "classification_confidence": confidence,
                    "classification_reason": reason,
                }
            )

    output_path = resolve_path(args.output)
    clusters_output_path = resolve_path(args.clusters_output)
    save_json_file(output_path, classified_jobs)
    save_json_file(clusters_output_path, cluster_records)

    print("Stage 3 complete.")
    print(f"Input jobs: {len(jobs)}")
    print(f"Role clusters: {len(clusters)}")
    print(f"Classified jobs: {len(classified_jobs)} -> {output_path}")
    print(f"Cluster mapping: {clusters_output_path}")
    return {
        "classified_jobs": classified_jobs,
        "cluster_records": cluster_records,
        "output_path": str(output_path),
        "clusters_output_path": str(clusters_output_path),
    }
