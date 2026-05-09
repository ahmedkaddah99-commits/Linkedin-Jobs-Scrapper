import re
from typing import Dict, List, Optional

from .common import compact_whitespace
from .generation import split_bullets
from .modes import CV_GENERATION_MODE_AGGRESSIVE, normalize_cv_generation_mode


def split_paragraphs(text: str) -> List[str]:
    parts = [item.strip() for item in re.split(r"\n\s*\n", text or "") if item.strip()]
    if parts:
        return parts
    one_block = (text or "").strip()
    return [one_block] if one_block else []


def parse_cv_role_header(role_line: str, fallback_company: str = "") -> Dict:
    cleaned = compact_whitespace(role_line)
    if not cleaned:
        return {"role_title": "", "company": fallback_company, "period": ""}

    parts = [part.strip() for part in cleaned.split("|") if part.strip()]
    role_company_part = parts[0] if parts else cleaned
    period = parts[-1] if len(parts) > 1 else ""

    role_title = ""
    company = fallback_company

    if len(parts) >= 3:
        role_title = parts[0]
        company = parts[1]
        return {
            "role_title": role_title,
            "company": company,
            "period": period,
        }
    if len(parts) == 2:
        role_title = parts[0]
        company = parts[1]
        return {
            "role_title": role_title,
            "company": company,
            "period": "",
        }

    at_match = re.match(r"^(.*?)\s+at\s+(.+)$", role_company_part, flags=re.IGNORECASE)
    if at_match:
        role_title = at_match.group(1).strip(" -")
        company = at_match.group(2).strip()
    else:
        dash_parts = [part.strip() for part in role_company_part.split(" - ", 1)]
        if len(dash_parts) == 2:
            role_title, company = dash_parts[0], dash_parts[1]
        else:
            role_title = role_company_part

    return {
        "role_title": role_title,
        "company": company,
        "period": period,
    }


def normalize_compare_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def looks_like_location_value(value: str) -> bool:
    token = normalize_compare_token(value)
    return token in {
        "germany",
        "munich",
        "frankfurt",
        "berlin",
        "hamburg",
        "stuttgart",
        "cologne",
        "dusseldorf",
        "freiburg",
    }


def extract_cv_professional_experiences(cv_text: str) -> List[Dict]:
    lines = [line.rstrip() for line in (cv_text or "").splitlines()]
    if not lines:
        return []

    start_index = None
    for index, line in enumerate(lines):
        if normalize_compare_token(line) == "professional experience":
            start_index = index + 1
            break
    if start_index is None:
        return []

    end_markers = {
        "skills",
        "education",
        "languages",
        "projects",
        "project",
        "strategic technology initiatives",
        "strategic and technology initiatives",
    }
    end_index = len(lines)
    for index in range(start_index, len(lines)):
        marker = normalize_compare_token(lines[index])
        if marker in end_markers:
            end_index = index
            break

    experiences: List[Dict] = []
    cursor = start_index
    while cursor < end_index:
        current = lines[cursor].strip()
        if not current:
            cursor += 1
            continue

        is_header = "|" in current and not re.match(r"^[\-\*\u2022]\s*", current)
        if not is_header:
            cursor += 1
            continue

        header = parse_cv_role_header(current)
        bullets: List[str] = []
        cursor += 1
        while cursor < end_index:
            raw = lines[cursor].strip()
            if not raw:
                if bullets:
                    break
                cursor += 1
                continue
            if "|" in raw and not re.match(r"^[\-\*\u2022]\s*", raw):
                break
            if re.match(r"^[\-\*\u2022]\s*", raw):
                bullets.append(re.sub(r"^[\-\*\u2022]+\s*", "", raw))
            elif bullets:
                bullets[-1] = f"{bullets[-1]} {compact_whitespace(raw)}"
            cursor += 1

        experiences.append(
            {
                "role_title": header["role_title"],
                "company": header["company"],
                "period": header["period"],
                "bullets": bullets,
            }
        )

    return experiences


def match_to_cv_experience(item: Dict, cv_experiences: List[Dict]) -> Optional[Dict]:
    role = str(item.get("role_title") or "").strip()
    company = str(item.get("company") or "").strip()
    period = str(item.get("period") or "").strip()

    if role and " at " in role.lower():
        parsed = parse_cv_role_header(role, fallback_company=company)
        role = parsed.get("role_title", role).strip()
        parsed_company = parsed.get("company", "").strip()
        if parsed_company:
            company = parsed_company
        if not period:
            period = parsed.get("period", "").strip()

    role_key = normalize_compare_token(role)
    company_key = normalize_compare_token(company)
    period_key = normalize_compare_token(period)

    best_score = 0
    best_match = None

    for candidate in cv_experiences:
        candidate_role_key = normalize_compare_token(str(candidate.get("role_title") or ""))
        candidate_company_key = normalize_compare_token(str(candidate.get("company") or ""))
        candidate_period_key = normalize_compare_token(str(candidate.get("period") or ""))
        score = 0

        if role_key and candidate_role_key and (role_key == candidate_role_key or role_key in candidate_role_key or candidate_role_key in role_key):
            score += 5
        if company_key and candidate_company_key and (
            company_key == candidate_company_key or company_key in candidate_company_key or candidate_company_key in company_key
        ):
            score += 4
        if period_key and candidate_period_key and (
            period_key == candidate_period_key or period_key in candidate_period_key or candidate_period_key in period_key
        ):
            score += 3

        if score > best_score:
            best_score = score
            best_match = candidate

    return best_match if best_score >= 5 else None


def dedupe_experiences(experiences: List[Dict]) -> List[Dict]:
    seen = {}
    ordered: List[Dict] = []
    for item in experiences:
        key = (
            normalize_compare_token(str(item.get("role_title") or "")),
            normalize_compare_token(str(item.get("company") or "")),
            normalize_compare_token(str(item.get("period") or "")),
        )
        if key in seen:
            existing = seen[key]
            existing_bullets = [str(b).strip() for b in existing.get("bullets", []) if str(b).strip()]
            existing_keys = {normalize_compare_token(text) for text in existing_bullets}
            for bullet in item.get("bullets", []):
                cleaned = str(bullet).strip()
                if not cleaned:
                    continue
                bullet_key = normalize_compare_token(cleaned)
                if bullet_key and bullet_key not in existing_keys:
                    existing_bullets.append(cleaned)
                    existing_keys.add(bullet_key)
            existing["bullets"] = existing_bullets
            continue

        clone = {
            "role_title": str(item.get("role_title") or "").strip(),
            "company": str(item.get("company") or "").strip(),
            "period": str(item.get("period") or "").strip(),
            "bullets": [str(b).strip() for b in item.get("bullets", []) if str(b).strip()],
        }
        seen[key] = clone
        ordered.append(clone)

    return ordered


def extract_cv_strategic_initiatives(cv_text: str) -> List[Dict]:
    lines = [line.rstrip() for line in (cv_text or "").splitlines()]
    if not lines:
        return []

    start_index = None
    for index, line in enumerate(lines):
        marker = normalize_compare_token(line)
        if marker in {"projects", "project", "strategic technology initiatives", "strategic and technology initiatives"}:
            start_index = index + 1
            break
    if start_index is None:
        return []

    initiatives: List[Dict] = []
    current = None

    for raw in lines[start_index:]:
        line = raw.strip()
        if not line:
            continue
        if normalize_compare_token(line) in {"skills", "education", "professional experience", "languages"}:
            break

        if re.match(r"^[\-\*\u2022]+\s*", line):
            bullet = re.sub(r"^[\-\*\u2022]+\s*", "", line).strip()
            if bullet and current is not None:
                current["bullets"].append(bullet)
            continue

        if current is not None:
            initiatives.append(current)
        current = {"title": compact_whitespace(line), "bullets": []}

    if current is not None:
        initiatives.append(current)

    return [item for item in initiatives if item.get("title")]


def merge_unique_bullets(existing: List[str], additions: List[str]) -> List[str]:
    merged = [str(item).strip() for item in (existing or []) if str(item).strip()]
    seen = {normalize_compare_token(item) for item in merged}
    for bullet in additions or []:
        cleaned = str(bullet).strip()
        if not cleaned:
            continue
        key = normalize_compare_token(cleaned)
        if key and key not in seen:
            merged.append(cleaned)
            seen.add(key)
    return merged


def extract_cv_education(cv_text: str) -> List[Dict]:
    lines = [line.rstrip() for line in (cv_text or "").splitlines()]
    if not lines:
        return []

    start_index = None
    for index, line in enumerate(lines):
        if normalize_compare_token(line) == "education":
            start_index = index + 1
            break
    if start_index is None:
        return []

    end_markers = {
        "projects",
        "project",
        "strategic technology initiatives",
        "strategic and technology initiatives",
        "professional experience",
        "skills",
        "languages",
    }
    end_index = len(lines)
    for index in range(start_index, len(lines)):
        marker = normalize_compare_token(lines[index])
        if marker in end_markers:
            end_index = index
            break

    education_items: List[Dict] = []
    current_item = None
    in_thesis = False

    for cursor in range(start_index, end_index):
        line = lines[cursor].strip()
        if not line:
            continue

        is_degree_line = (
            not line.lower().startswith("master thesis")
            and re.match(
                r"(?i)^(m\.a\.|m\.sc\.|msc\b|b\.sc\.|bsc\b|b\.a\.|mba\b|master\b|bachelor\b|ph\.d\b|phd\b)",
                line,
            )
        )
        if is_degree_line:
            if current_item is not None:
                education_items.append(current_item)
            current_item = {
                "degree_title": compact_whitespace(line),
                "thesis_title": "",
                "thesis_bullets": [],
            }
            in_thesis = False
            continue

        if line.lower().startswith("master thesis"):
            if current_item is None:
                current_item = {"degree_title": "", "thesis_title": "", "thesis_bullets": []}
            current_item["thesis_title"] = compact_whitespace(line)
            in_thesis = True
            continue

        if re.match(r"^(?:[\-\*\u2022]+|--)\s*", line):
            bullet = re.sub(r"^(?:[\-\*\u2022]+|--)\s*", "", line).strip()
            if bullet and current_item is not None:
                current_item["thesis_bullets"] = merge_unique_bullets(current_item.get("thesis_bullets", []), [bullet])
            continue

        if line.lower().startswith("github:"):
            if current_item is not None and in_thesis:
                current_item["thesis_bullets"] = merge_unique_bullets(current_item.get("thesis_bullets", []), [line])
            continue

        if in_thesis and current_item is not None and current_item.get("thesis_bullets"):
            current_item["thesis_bullets"][-1] = compact_whitespace(
                f"{current_item['thesis_bullets'][-1]} {line}"
            )
            continue

        if current_item is not None:
            education_items.append(current_item)
        current_item = {
            "degree_title": compact_whitespace(line),
            "thesis_title": "",
            "thesis_bullets": [],
        }
        in_thesis = False

    if current_item is not None:
        education_items.append(current_item)

    return [item for item in education_items if item.get("degree_title") or item.get("thesis_title")]


def extract_role_from_cv_text(cv_text: str, company_keyword: str):
    lines = [line.rstrip() for line in (cv_text or "").splitlines()]
    keyword = company_keyword.lower()
    for index, line in enumerate(lines):
        if keyword not in line.lower():
            continue

        header = parse_cv_role_header(line, fallback_company=company_keyword)
        bullets = []
        cursor = index + 1
        while cursor < len(lines):
            raw = lines[cursor].strip()
            if not raw:
                if bullets:
                    break
                cursor += 1
                continue

            if re.match(r"^[\-\*\u2022]\s*", raw):
                bullets.append(re.sub(r"^[\-\*\u2022]\s*", "", raw))
                cursor += 1
                continue

            if "|" in raw and not re.match(r"^[\-\*\u2022]\s*", raw):
                break

            if bullets:
                bullets[-1] = f"{bullets[-1]} {compact_whitespace(raw)}"
            cursor += 1

        if bullets:
            return {
                "role_title": header["role_title"],
                "company": header["company"],
                "period": header["period"],
                "bullets": bullets,
            }
    return None


def _clamp_rewritten_bullets(generated_bullets: List[str], baseline_bullets: List[str]) -> List[str]:
    normalized_generated = [str(item).strip() for item in (generated_bullets or []) if str(item).strip()]
    normalized_baseline = [str(item).strip() for item in (baseline_bullets or []) if str(item).strip()]
    if not normalized_baseline:
        return normalized_generated
    if not normalized_generated:
        return normalized_baseline
    clamped: List[str] = []
    for index, baseline_bullet in enumerate(normalized_baseline):
        if index < len(normalized_generated):
            clamped.append(normalized_generated[index])
        else:
            clamped.append(baseline_bullet)
    return clamped


def ensure_structured_cv_fields(
    record: Dict,
    candidate_name: str,
    cv_text: str,
    *,
    cv_generation_mode: str = CV_GENERATION_MODE_AGGRESSIVE,
) -> None:
    normalized_mode = normalize_cv_generation_mode(cv_generation_mode)
    title = str(record.get("title") or "").strip()
    company = str(record.get("company") or "").strip()

    if not record.get("cv_professional_summary"):
        record["cv_professional_summary"] = (
            f"{candidate_name} applying to {title} at {company}, with focus on business transformation, "
            "AI implementation, and measurable delivery impact."
        ).strip()

    skills = record.get("cv_skills", [])
    if isinstance(skills, list):
        normalized_skills = [str(item).strip() for item in skills if str(item).strip()]
    else:
        normalized_skills = split_bullets(str(skills))
    record["cv_skills"] = normalized_skills

    cv_experiences = extract_cv_professional_experiences(cv_text)
    experience_bullets_by_key: Dict[tuple, List[str]] = {}
    experiences = record.get("cv_professional_experience", [])
    if isinstance(experiences, list):
        for item in experiences:
            if not isinstance(item, dict):
                continue
            matched_cv_experience = match_to_cv_experience(item, cv_experiences)
            if not matched_cv_experience:
                continue
            bullets_raw = item.get("bullets", [])
            if isinstance(bullets_raw, list):
                bullets = [str(b).strip() for b in bullets_raw if str(b).strip()]
            else:
                bullets = split_bullets(str(bullets_raw))
            key = (
                normalize_compare_token(str(matched_cv_experience.get("role_title", ""))),
                normalize_compare_token(str(matched_cv_experience.get("company", ""))),
                normalize_compare_token(str(matched_cv_experience.get("period", ""))),
            )
            if key not in experience_bullets_by_key:
                experience_bullets_by_key[key] = []
            experience_bullets_by_key[key] = merge_unique_bullets(experience_bullets_by_key[key], bullets)

    normalized_experiences = []
    if cv_experiences:
        for base_item in cv_experiences:
            key = (
                normalize_compare_token(str(base_item.get("role_title", ""))),
                normalize_compare_token(str(base_item.get("company", ""))),
                normalize_compare_token(str(base_item.get("period", ""))),
            )
            base_bullets = [str(b).strip() for b in base_item.get("bullets", []) if str(b).strip()]
            if normalized_mode == CV_GENERATION_MODE_AGGRESSIVE:
                selected_bullets = _clamp_rewritten_bullets(experience_bullets_by_key.get(key) or [], base_bullets)
            else:
                selected_bullets = base_bullets
            normalized_experiences.append(
                {
                    "role_title": str(base_item.get("role_title", "")).strip(),
                    "company": str(base_item.get("company", "")).strip(),
                    "period": str(base_item.get("period", "")).strip(),
                    "bullets": selected_bullets,
                }
            )
    else:
        normalized_experiences = dedupe_experiences(
            [
                {
                    "role_title": str(item.get("role_title", "")).strip(),
                    "company": str(item.get("company", "")).strip(),
                    "period": str(item.get("period", "")).strip(),
                    "bullets": [str(b).strip() for b in item.get("bullets", []) if str(b).strip()],
                }
                for item in experiences
                if isinstance(item, dict)
            ]
        )

    record["cv_professional_experience"] = normalized_experiences

    baseline_education = extract_cv_education(cv_text)
    generated_education = record.get("cv_education", [])
    normalized_generated_education = []
    if isinstance(generated_education, list):
        for item in generated_education:
            if not isinstance(item, dict):
                continue
            degree_title = compact_whitespace(str(item.get("degree_title", "")).strip())
            thesis_title = compact_whitespace(str(item.get("thesis_title", "")).strip())
            thesis_raw = item.get("thesis_bullets", [])
            if isinstance(thesis_raw, list):
                thesis_bullets = [str(b).strip() for b in thesis_raw if str(b).strip()]
            else:
                thesis_bullets = split_bullets(str(thesis_raw))
            if degree_title or thesis_title or thesis_bullets:
                normalized_generated_education.append(
                    {
                        "degree_title": degree_title,
                        "thesis_title": thesis_title,
                        "thesis_bullets": thesis_bullets,
                    }
                )

    if baseline_education:
        final_education = []
        for base_item in baseline_education:
            base_degree = compact_whitespace(str(base_item.get("degree_title", "")).strip())
            base_thesis_title = compact_whitespace(str(base_item.get("thesis_title", "")).strip())
            base_thesis_bullets = [str(b).strip() for b in base_item.get("thesis_bullets", []) if str(b).strip()]
            final_education.append(
                {
                    "degree_title": base_degree,
                    "thesis_title": base_thesis_title,
                    "thesis_bullets": base_thesis_bullets,
                }
            )
        record["cv_education"] = final_education
    else:
        record["cv_education"] = normalized_generated_education

    baseline_initiatives = extract_cv_strategic_initiatives(cv_text)
    generated_initiatives = record.get("cv_strategic_initiatives", [])
    normalized_generated_initiatives: List[Dict] = []
    if isinstance(generated_initiatives, list):
        for item in generated_initiatives:
            if isinstance(item, dict):
                item_title = compact_whitespace(str(item.get("title", "")).strip())
                bullets_raw = item.get("bullets", [])
                if isinstance(bullets_raw, list):
                    item_bullets = [str(b).strip() for b in bullets_raw if str(b).strip()]
                else:
                    item_bullets = split_bullets(str(bullets_raw))
                if item_title:
                    normalized_generated_initiatives.append({"title": item_title, "bullets": item_bullets})
            elif isinstance(item, str):
                item_title = compact_whitespace(item)
                if item_title:
                    normalized_generated_initiatives.append({"title": item_title, "bullets": []})

    if baseline_initiatives:
        final_initiatives = []
        for base_item in baseline_initiatives:
            base_title = compact_whitespace(str(base_item.get("title", "")))
            base_bullets = [str(b).strip() for b in base_item.get("bullets", []) if str(b).strip()]
            final_initiatives.append({"title": base_title, "bullets": base_bullets})
        record["cv_strategic_initiatives"] = final_initiatives
    else:
        deduped_initiatives = []
        seen_initiatives = set()
        for item in normalized_generated_initiatives:
            title_key = normalize_compare_token(str(item.get("title", "")))
            if not title_key or title_key in seen_initiatives:
                continue
            seen_initiatives.add(title_key)
            deduped_initiatives.append(
                {
                    "title": compact_whitespace(str(item.get("title", ""))),
                    "bullets": [str(b).strip() for b in item.get("bullets", []) if str(b).strip()],
                }
            )
        record["cv_strategic_initiatives"] = deduped_initiatives
