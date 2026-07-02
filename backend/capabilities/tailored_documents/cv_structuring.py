import re
from typing import Any, Dict, List, Optional

from .common import compact_whitespace
from .generation import split_bullets
from .modes import CV_GENERATION_MODE_AGGRESSIVE, normalize_cv_generation_mode

_BULLET_PREFIX_RE = re.compile(r"^\s*(?:[-*]|\u2022|\u2023|\u25e6|\u2022)+\s*")
_DATE_TOKEN_RE = re.compile(
    r"\b("
    r"(?:19|20)\d{2}|present|current|"
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
    r")\b",
    flags=re.IGNORECASE,
)
_EXPERIENCE_SECTION_MARKERS = {
    "experience",
    "work experience",
    "professional experience",
    "employment",
    "employment history",
    "career history",
}
_EXPERIENCE_END_MARKERS = {
    "professional summary",
    "summary",
    "profile",
    "skills",
    "core competencies",
    "competencies",
    "technical skills",
    "key skills",
    "education",
    "education and training",
    "certification",
    "certifications",
    "training",
    "languages",
    "language skills",
    "projects",
    "project",
    "publications",
    "strategic technology initiatives",
    "strategic and technology initiatives",
}
_PROMOTED_BULLET_TITLE_RE = re.compile(
    r"^(achieved|built|contributed|created|delivered|designed|developed|drove|established|"
    r"facilitated|generated|identified|implemented|improved|increased|led|managed|negotiated|"
    r"optimized|produced|reduced|supported)\b",
    flags=re.IGNORECASE,
)
_ROLE_TITLE_HINT_RE = re.compile(
    r"\b(analyst|associate|consultant|contractor|co-?founder|developer|director|engineer|founder|"
    r"intern|internship|lead|manager|scientist|specialist|strategist|advisor|coordinator|owner)\b",
    flags=re.IGNORECASE,
)


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

    if len(parts) >= 4:
        role_title = parts[0]
        company = parts[1]
        return {
            "role_title": role_title,
            "company": company,
            "location": " | ".join(parts[2:-1]),
            "period": period,
        }
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


def _looks_like_date_line(value: str) -> bool:
    return bool(_DATE_TOKEN_RE.search(compact_whitespace(value)))


def _strip_bullet_prefix(value: str) -> str:
    return _BULLET_PREFIX_RE.sub("", str(value or "")).strip()


def _is_bullet_line(value: str) -> bool:
    return bool(_BULLET_PREFIX_RE.match(str(value or "")))


def _looks_like_experience_header(line: str, following_lines: List[str]) -> bool:
    text = compact_whitespace(line)
    if not text or _is_bullet_line(text):
        return False
    if normalize_compare_token(text) in _EXPERIENCE_END_MARKERS:
        return False
    if "|" in text or " at " in text.lower():
        return True
    if len(text) > 120:
        return False
    next_line = compact_whitespace(following_lines[0]) if following_lines else ""
    second_line = compact_whitespace(following_lines[1]) if len(following_lines) > 1 else ""
    return bool(
        (next_line and _looks_like_date_line(next_line))
        or (
            next_line
            and second_line
            and not _is_bullet_line(next_line)
            and normalize_compare_token(next_line) not in _EXPERIENCE_END_MARKERS
            and _looks_like_date_line(second_line)
        )
    )


def _parse_experience_header_at(lines: List[str], cursor: int, end_index: int) -> tuple[Dict, int]:
    current = compact_whitespace(lines[cursor])
    following = [compact_whitespace(lines[index]) for index in range(cursor + 1, min(cursor + 3, end_index))]

    if "|" in current or " at " in current.lower():
        header = parse_cv_role_header(current)
        next_cursor = cursor + 1
        if not header.get("period") and next_cursor < end_index:
            next_line = compact_whitespace(lines[next_cursor])
            if _looks_like_date_line(next_line) and len(next_line) <= 60:
                header["period"] = next_line
                next_cursor += 1
        return header, next_cursor

    if following and "|" in following[0] and _looks_like_date_line(following[0]):
        parsed_detail = parse_cv_role_header(following[0])
        return {
            "role_title": current,
            "company": str(parsed_detail.get("role_title") or parsed_detail.get("company") or "").strip(),
            "location": str(parsed_detail.get("company") or parsed_detail.get("location") or "").strip(),
            "period": str(parsed_detail.get("period") or "").strip() or following[0],
        }, cursor + 2

    if following and _looks_like_date_line(following[0]):
        return {"role_title": current, "company": "", "period": following[0]}, cursor + 2

    if len(following) > 1 and _looks_like_date_line(following[1]):
        return {"role_title": current, "company": following[0], "period": following[1]}, cursor + 3

    return parse_cv_role_header(current), cursor + 1


def _experience_key(item: Dict) -> tuple:
    return (
        normalize_compare_token(str(item.get("role_title") or "")),
        normalize_compare_token(str(item.get("company") or "")),
        normalize_compare_token(str(item.get("period") or "")),
    )


def _looks_like_promoted_bullet_title(value: str) -> bool:
    text = compact_whitespace(value)
    if not text:
        return False
    words = [word for word in re.split(r"\s+", text) if word]
    if _is_bullet_line(text) or text.endswith((".", ";")):
        return True
    if len(words) >= 5 and _PROMOTED_BULLET_TITLE_RE.match(text) and not _ROLE_TITLE_HINT_RE.search(text):
        return True
    return len(words) > 12 and not _ROLE_TITLE_HINT_RE.search(text)


def _is_trustworthy_generated_display(item: Dict) -> bool:
    role_title = str(item.get("role_title") or item.get("title") or "").strip()
    if not role_title or _looks_like_promoted_bullet_title(role_title):
        return False
    return bool(str(item.get("company") or "").strip() or _ROLE_TITLE_HINT_RE.search(role_title))


def _normalize_bullet_value(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("text") or value.get("value") or value.get("label") or "").strip()
    return str(value or "").strip()


def _normalize_bullet_item(value: Any) -> Any:
    text = _normalize_bullet_value(value)
    if not text:
        return ""
    if isinstance(value, dict):
        clone = dict(value)
        clone["text"] = text
        return clone
    return text


def _repair_generated_experience_item(item: Dict) -> Dict:
    clone = {
        "role_title": str(item.get("role_title") or item.get("title") or "").strip(),
        "company": str(item.get("company") or "").strip(),
        "location": str(item.get("location") or "").strip(),
        "period": str(item.get("period") or "").strip(),
        "bullets": [normalized for bullet in item.get("bullets", []) if (normalized := _normalize_bullet_item(bullet))],
    }
    period_header = clone["period"]
    if "|" not in period_header:
        return clone

    promoted_bullets = []
    for field_name in ("role_title", "company"):
        value = clone[field_name]
        if value and _looks_like_promoted_bullet_title(value):
            promoted_bullets.append(value)

    if not promoted_bullets:
        return clone

    parsed_header = parse_cv_role_header(period_header)
    if not str(parsed_header.get("role_title") or "").strip():
        return clone

    return {
        "role_title": str(parsed_header.get("role_title") or "").strip(),
        "company": str(parsed_header.get("company") or clone.get("company") or "").strip(),
        "location": str(parsed_header.get("location") or clone.get("location") or "").strip(),
        "period": str(parsed_header.get("period") or "").strip(),
        "bullets": merge_unique_bullets(promoted_bullets, [_normalize_bullet_value(bullet) for bullet in clone["bullets"]]),
    }


def _tokens_overlap(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return left == right or left in right or right in left


def extract_cv_professional_experiences(cv_text: str) -> List[Dict]:
    lines = [compact_whitespace(line) for line in (cv_text or "").splitlines()]
    if not lines:
        return []

    start_index = None
    for index, line in enumerate(lines):
        if normalize_compare_token(line) in _EXPERIENCE_SECTION_MARKERS:
            start_index = index + 1
            break
    if start_index is None:
        return []

    end_index = len(lines)
    for index in range(start_index, len(lines)):
        marker = normalize_compare_token(lines[index])
        if marker in _EXPERIENCE_END_MARKERS:
            end_index = index
            break

    experiences: List[Dict] = []
    cursor = start_index
    while cursor < end_index:
        current = lines[cursor].strip()
        if not current:
            cursor += 1
            continue

        following_lines = [lines[index] for index in range(cursor + 1, min(cursor + 3, end_index))]
        if not _looks_like_experience_header(current, following_lines):
            cursor += 1
            continue

        header, cursor = _parse_experience_header_at(lines, cursor, end_index)
        bullets: List[str] = []
        while cursor < end_index:
            raw = lines[cursor].strip()
            if not raw:
                if bullets:
                    break
                cursor += 1
                continue
            if normalize_compare_token(raw) in _EXPERIENCE_END_MARKERS:
                cursor = end_index
                break
            following_lines = [lines[index] for index in range(cursor + 1, min(cursor + 3, end_index))]
            if _looks_like_experience_header(raw, following_lines):
                break
            if not header.get("period") and _looks_like_date_line(raw) and len(raw) <= 60:
                header["period"] = raw
                cursor += 1
                continue
            if _is_bullet_line(raw):
                cleaned = _strip_bullet_prefix(raw)
                if cleaned:
                    bullets.append(cleaned)
            else:
                bullets.append(compact_whitespace(raw))
            cursor += 1

        experiences.append(
            {
                "role_title": header["role_title"],
                "company": header["company"],
                "location": str(header.get("location") or "").strip(),
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

        if _tokens_overlap(role_key, candidate_role_key):
            score += 5
        if _tokens_overlap(company_key, candidate_company_key):
            score += 4
        if _tokens_overlap(company_key, candidate_role_key):
            score += 4
        if _tokens_overlap(role_key, candidate_company_key):
            score += 2
        if _tokens_overlap(period_key, candidate_period_key):
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
            existing_bullets = [
                bullet for bullet in existing.get("bullets", []) if _normalize_bullet_value(bullet)
            ]
            existing_keys = {normalize_compare_token(_normalize_bullet_value(bullet)) for bullet in existing_bullets}
            for bullet in item.get("bullets", []):
                cleaned = _normalize_bullet_item(bullet)
                if not cleaned:
                    continue
                bullet_key = normalize_compare_token(_normalize_bullet_value(cleaned))
                if bullet_key and bullet_key not in existing_keys:
                    existing_bullets.append(cleaned)
                    existing_keys.add(bullet_key)
            existing["bullets"] = existing_bullets
            continue

        clone = {
            "role_title": str(item.get("role_title") or "").strip(),
            "company": str(item.get("company") or "").strip(),
            "location": str(item.get("location") or "").strip(),
            "period": str(item.get("period") or "").strip(),
            "bullets": [normalized for bullet in item.get("bullets", []) if (normalized := _normalize_bullet_item(bullet))],
        }
        seen[key] = clone
        ordered.append(clone)

    return ordered


def normalize_cv_experience_items(items: Any) -> List[Dict]:
    if not isinstance(items, list):
        return []

    normalized_items: List[Dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        repaired = _repair_generated_experience_item(item)
        if not any(
            str(repaired.get(field) or "").strip()
            for field in ("role_title", "company", "location", "period")
        ) and not repaired.get("bullets"):
            continue
        normalized_items.append(repaired)
    return dedupe_experiences(normalized_items)


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

        if current is not None and "|" in line:
            initiatives.append(current)
            current = {"title": compact_whitespace(line), "bullets": []}
            continue

        if current is None:
            current = {"title": compact_whitespace(line), "bullets": []}
            continue

        current["bullets"].append(compact_whitespace(line))

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


def match_to_cv_initiative(item: Dict, cv_initiatives: List[Dict]) -> Optional[Dict]:
    title_key = normalize_compare_token(str(item.get("title") or ""))
    if not title_key:
        return None

    best_score = 0
    best_match = None
    for candidate in cv_initiatives:
        candidate_key = normalize_compare_token(str(candidate.get("title") or ""))
        score = 0
        if _tokens_overlap(title_key, candidate_key):
            score += 5
        if score > best_score:
            best_score = score
            best_match = candidate
    return best_match if best_score >= 5 else None


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

        if in_thesis and current_item is not None:
            current_item["thesis_bullets"] = merge_unique_bullets(current_item.get("thesis_bullets", []), [line])
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


def _render_structured_cv_text(record: Dict) -> str:
    lines: List[str] = []
    summary = str(record.get("cv_professional_summary") or "").strip()
    if summary:
        lines.extend([f"Professional Summary: {summary}", ""])

    experiences = [item for item in record.get("cv_professional_experience", []) if isinstance(item, dict)]
    if experiences:
        lines.append("Professional Experience:")
        for item in experiences:
            header = " | ".join(
                [
                    part
                    for part in [
                        str(item.get("role_title") or "").strip(),
                        str(item.get("company") or "").strip(),
                        str(item.get("period") or "").strip(),
                    ]
                    if part
                ]
            )
            if header:
                lines.append(header)
            for bullet in item.get("bullets", []):
                bullet_text = str(bullet).strip()
                if bullet_text:
                    lines.append(f"- {bullet_text}")
        lines.append("")

    skills = [str(skill).strip() for skill in record.get("cv_skills", []) if str(skill).strip()]
    if skills:
        lines.append("Skills:")
        lines.extend([f"- {skill}" for skill in skills])
        lines.append("")

    education = [item for item in record.get("cv_education", []) if isinstance(item, dict)]
    if education:
        lines.append("Education:")
        for item in education:
            degree_title = str(item.get("degree_title") or "").strip()
            thesis_title = str(item.get("thesis_title") or "").strip()
            if degree_title:
                lines.append(degree_title)
            if thesis_title:
                lines.append(thesis_title)
            for bullet in item.get("thesis_bullets", []):
                bullet_text = str(bullet).strip()
                if bullet_text:
                    lines.append(f"- {bullet_text}")

    return "\n".join(line for line in lines if line is not None).strip()


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
    language_requirements = dict(
        dict(dict(record.get("application_requirements") or {}).get("cv_requirements") or {}).get("language") or {}
    )
    cv_output_language = str(record.get("cv_output_language") or language_requirements.get("output_language") or "").strip()
    source_language = str(language_requirements.get("source_language") or "").strip()
    use_generated_language_content = bool(language_requirements.get("will_translate")) or bool(
        cv_output_language and source_language and cv_output_language != source_language
    )

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
    experience_display_by_key: Dict[tuple, Dict] = {}
    experiences = record.get("cv_professional_experience", [])
    generated_experiences: List[Dict] = []
    generated_experiences.extend(normalize_cv_experience_items(experiences))
    generated_experiences.extend(normalize_cv_experience_items(extract_cv_professional_experiences(str(record.get("tailored_cv") or ""))))
    generated_bullets_by_index: List[List[str]] = []
    for generated_item in generated_experiences:
        generated_bullets_by_index.append(
            [
                _normalize_bullet_value(bullet)
                for bullet in generated_item.get("bullets", [])
                if _normalize_bullet_value(bullet)
            ]
        )

    if generated_experiences:
        for item in generated_experiences:
            if not isinstance(item, dict):
                continue
            matched_cv_experience = match_to_cv_experience(item, cv_experiences)
            if not matched_cv_experience:
                continue
            bullets_raw = item.get("bullets", [])
            if isinstance(bullets_raw, list):
                bullets = [_normalize_bullet_value(b) for b in bullets_raw if _normalize_bullet_value(b)]
            else:
                bullets = split_bullets(str(bullets_raw))
            key = _experience_key(matched_cv_experience)
            if key not in experience_bullets_by_key:
                experience_bullets_by_key[key] = []
            experience_bullets_by_key[key] = merge_unique_bullets(experience_bullets_by_key[key], bullets)
            if bullets and key not in experience_display_by_key:
                experience_display_by_key[key] = item

    normalized_experiences = []
    if cv_experiences:
        for index, base_item in enumerate(cv_experiences):
            key = _experience_key(base_item)
            base_bullets = [str(b).strip() for b in base_item.get("bullets", []) if str(b).strip()]
            generated_bullets = experience_bullets_by_key.get(key) or []
            generated_display = experience_display_by_key.get(key)
            if not generated_bullets and index < len(generated_bullets_by_index):
                generated_bullets = generated_bullets_by_index[index]
                if index < len(generated_experiences):
                    index_display = generated_experiences[index]
                    if _is_trustworthy_generated_display(index_display):
                        generated_display = index_display
            if normalized_mode == CV_GENERATION_MODE_AGGRESSIVE:
                selected_bullets = _clamp_rewritten_bullets(generated_bullets, base_bullets)
            elif use_generated_language_content and generated_bullets:
                selected_bullets = _clamp_rewritten_bullets(generated_bullets, base_bullets)
            else:
                selected_bullets = base_bullets or generated_bullets
            display_item = base_item
            if (
                normalized_mode == CV_GENERATION_MODE_AGGRESSIVE
                and generated_display
                and generated_bullets
                and _is_trustworthy_generated_display(generated_display)
                and (not base_bullets or looks_like_location_value(str(base_item.get("company") or "")))
            ):
                display_item = generated_display
            normalized_experiences.append(
                {
                    "role_title": str(display_item.get("role_title") or base_item.get("role_title", "")).strip(),
                    "company": str(display_item.get("company") or base_item.get("company", "")).strip(),
                    "location": str(display_item.get("location") or base_item.get("location", "")).strip(),
                    "period": str(display_item.get("period") or base_item.get("period", "")).strip(),
                    "bullets": selected_bullets,
                }
            )
    else:
        normalized_experiences = normalize_cv_experience_items(generated_experiences)

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

    if baseline_education and not (use_generated_language_content and normalized_generated_education):
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

    if baseline_initiatives and normalized_mode == CV_GENERATION_MODE_AGGRESSIVE:
        final_initiatives = []
        for index, base_item in enumerate(baseline_initiatives):
            base_title = compact_whitespace(str(base_item.get("title", "")))
            base_bullets = [str(b).strip() for b in base_item.get("bullets", []) if str(b).strip()]
            generated_match = match_to_cv_initiative(base_item, normalized_generated_initiatives)
            if not generated_match and index < len(normalized_generated_initiatives):
                generated_match = normalized_generated_initiatives[index]
            generated_bullets = (
                [str(b).strip() for b in generated_match.get("bullets", []) if str(b).strip()]
                if generated_match
                else []
            )
            final_initiatives.append(
                {
                    "title": base_title,
                    "bullets": _clamp_rewritten_bullets(generated_bullets, base_bullets),
                }
            )
        record["cv_strategic_initiatives"] = final_initiatives
    elif baseline_initiatives and not (use_generated_language_content and normalized_generated_initiatives):
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

    record["tailored_cv"] = _render_structured_cv_text(record)
