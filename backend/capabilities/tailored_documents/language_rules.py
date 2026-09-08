from __future__ import annotations

import re
from typing import Any


DEFAULT_GERMAN_SPECIAL_CHAR_THRESHOLD = 9999
DEFAULT_FRENCH_SPECIAL_CHAR_THRESHOLD = 0
DEFAULT_SPANISH_SPECIAL_CHAR_THRESHOLD = 0

GERMAN_SPECIAL_MARKERS = (
    "\u00e4",
    "\u00f6",
    "\u00fc",
    "\u00c4",
    "\u00d6",
    "\u00dc",
    "\u00df",
    "\u00c3\u00a4",
    "\u00c3\u00b6",
    "\u00c3\u00bc",
    "\u00c3\u009f",
)
FRENCH_SPECIAL_MARKERS = (
    "\u00e0",
    "\u00e2",
    "\u00e6",
    "\u00e7",
    "\u00e8",
    "\u00e9",
    "\u00ea",
    "\u00eb",
    "\u00ee",
    "\u00ef",
    "\u00f4",
    "\u0153",
    "\u00f9",
    "\u00fb",
    "\u00ff",
)
SPANISH_SPECIAL_MARKERS = (
    "\u00e1",
    "\u00e9",
    "\u00ed",
    "\u00f1",
    "\u00f3",
    "\u00fa",
    "\u00bf",
    "\u00a1",
)

CEFR_LEVEL_RANK = {
    "A1": 1,
    "A2": 2,
    "B1": 3,
    "B2": 4,
    "C1": 5,
    "C2": 6,
    "ANY": 0,
}

LANGUAGE_ALIASES: dict[str, tuple[str, ...]] = {
    "Arabic": ("arabic", "arabisch"),
    "Chinese": ("chinese", "mandarin", "cantonese", "chinesisch"),
    "Czech": ("czech", "tschechisch"),
    "Danish": ("danish", "danisch"),
    "Dutch": ("dutch", "niederl\u00e4ndisch"),
    "English": ("english", "englisch"),
    "Finnish": ("finnish", "finnisch"),
    "French": ("french", "franz\u00f6sisch"),
    "German": ("german", "deutsch"),
    "Italian": ("italian", "italienisch"),
    "Japanese": ("japanese", "japanisch"),
    "Korean": ("korean", "koreanisch"),
    "Polish": ("polish", "polnisch"),
    "Portuguese": ("portuguese", "portugiesisch"),
    "Romanian": ("romanian", "rum\u00e4nisch"),
    "Russian": ("russian", "russisch"),
    "Spanish": ("spanish", "spanisch"),
    "Swedish": ("swedish", "schwedisch"),
    "Turkish": ("turkish", "t\u00fcrkisch"),
    "Ukrainian": ("ukrainian", "ukrainisch"),
}

LANGUAGE_LEVEL_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("C2", ("native", "bilingual", "mother tongue", "muttersprach", "muttersprache")),
    ("C1", ("fluent", "business fluent", "professional", "full professional", "verhandlungssicher")),
    ("B2", ("upper intermediate", "good command", "good knowledge", "gute kenntnisse")),
    ("B1", ("intermediate", "working knowledge")),
    ("A2", ("basic", "elementary", "grundkenntnisse")),
    ("A1", ("beginner", "anf\u00e4nger")),
)

LANGUAGE_REQUIREMENT_CONTEXT = re.compile(
    r"\b("
    r"required|require|requires|requirement|must|mandatory|need|needed|needs|"
    r"fluent|proficient|proficiency|professional|business|excellent|strong|good|"
    r"native|bilingual|knowledge|command|skills?|language|languages|"
    r"voraussetzung|erforderlich|notwendig|kenntnisse|sprachniveau|"
    r"verhandlungssicher|flie(?:ss|\u00df)end|sehr\s+gut|gute"
    r")\b",
    re.IGNORECASE,
)


def _compact(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _job_language_text(job: dict[str, Any]) -> str:
    return "\n".join(
        _compact(job.get(key))
        for key in (
            "title",
            "company",
            "location_raw",
            "location",
            "full_description",
            "description_text",
            "description",
            "snippet",
            "requirements",
        )
        if _compact(job.get(key))
    )


def normalize_cefr_level(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.casefold() == "any":
        return "ANY"
    matches = re.findall(r"\b(A1|A2|B1|B2|C1|C2)\b", text, flags=re.IGNORECASE)
    if matches:
        normalized = [match.upper() for match in matches]
        return max(normalized, key=lambda item: CEFR_LEVEL_RANK.get(item, 0))
    folded = text.casefold()
    for level, hints in LANGUAGE_LEVEL_HINTS:
        if any(hint in folded for hint in hints):
            return level
    return ""


def _cefr_rank(value: Any) -> int:
    return CEFR_LEVEL_RANK.get(normalize_cefr_level(value), 0)


def _alias_pattern(alias: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![A-Za-z]){re.escape(alias)}(?![A-Za-z])", re.IGNORECASE)


def _window(text: str, start: int, end: int, radius: int = 90) -> str:
    return text[max(0, start - radius) : min(len(text), end + radius)]


def _requirement_evidence(text: str, start: int, end: int) -> str:
    snippet = _compact(_window(text, start, end, radius=110))
    if len(snippet) > 220:
        return f"{snippet[:217].rstrip()}..."
    return snippet


def _language_alias_hits(text: str):
    for language_name, aliases in LANGUAGE_ALIASES.items():
        for alias in aliases:
            for match in _alias_pattern(alias).finditer(text):
                yield language_name, alias, match.start(), match.end()


def extract_profile_language_levels(profile_languages: Any) -> dict[str, str]:
    if isinstance(profile_languages, str):
        raw_items = [item.strip() for item in re.split(r"[,;\n]+", profile_languages) if item.strip()]
    elif isinstance(profile_languages, (list, tuple, set)):
        raw_items = [str(item or "").strip() for item in profile_languages if str(item or "").strip()]
    else:
        return {}

    levels: dict[str, str] = {}
    for raw_item in raw_items:
        folded = raw_item.casefold()
        language_name = ""
        for canonical_name, aliases in LANGUAGE_ALIASES.items():
            if any(re.search(rf"(?<![A-Za-z]){re.escape(alias)}(?![A-Za-z])", folded) for alias in aliases):
                language_name = canonical_name
                break
        if not language_name:
            continue
        level = normalize_cefr_level(raw_item) or "ANY"
        existing = levels.get(language_name, "")
        if not existing or _cefr_rank(level) >= _cefr_rank(existing):
            levels[language_name] = level
    return levels


def detect_language_requirements(text: str) -> list[dict[str, str]]:
    requirements: dict[str, dict[str, str]] = {}
    normalized_text = str(text or "")
    for language_name, _alias, start, end in _language_alias_hits(normalized_text):
        context = _window(normalized_text, start, end)
        level = normalize_cefr_level(context)
        has_requirement_context = bool(LANGUAGE_REQUIREMENT_CONTEXT.search(context))
        if not level and not has_requirement_context:
            continue
        requirement_level = level or "ANY"
        existing = requirements.get(language_name)
        if existing and _cefr_rank(existing.get("required_level")) >= _cefr_rank(requirement_level):
            continue
        requirements[language_name] = {
            "language": language_name,
            "required_level": requirement_level,
            "evidence": _requirement_evidence(normalized_text, start, end),
        }
    return list(requirements.values())


def count_special_markers(text: str, markers: tuple[str, ...]) -> int:
    lowered = str(text or "").casefold()
    return sum(lowered.count(marker.casefold()) for marker in markers)


def _append_listing_language_reason(
    reasons: list[str],
    *,
    language_name: str,
    count: int,
    threshold: int,
) -> None:
    if threshold >= 0 and count > threshold:
        reasons.append(
            f"Listing appears to be written in {language_name} above configured threshold "
            f"(count {count} > threshold {threshold})."
        )


def _append_required_language_reasons(
    reasons: list[str],
    requirements: list[dict[str, str]],
    *,
    profile_languages: Any = None,
    max_german_level: str = "B2",
) -> None:
    profile_levels = extract_profile_language_levels(profile_languages)
    if profile_levels:
        for requirement in requirements:
            language_name = requirement["language"]
            required_level = normalize_cefr_level(requirement.get("required_level")) or "ANY"
            saved_level = profile_levels.get(language_name, "")
            if not saved_level:
                reasons.append(f"Required language {language_name} is not listed in configured languages.")
                continue
            if required_level != "ANY" and _cefr_rank(saved_level) < _cefr_rank(required_level):
                if saved_level == "ANY":
                    reasons.append(
                        f"{language_name} level requirement ({required_level}) cannot be verified because saved level is missing."
                    )
                else:
                    reasons.append(
                        f"{language_name} level requirement ({required_level}) is above saved level ({saved_level})."
                    )
        return

    max_german = normalize_cefr_level(max_german_level) or "B2"
    for requirement in requirements:
        if requirement["language"] != "German":
            continue
        required_level = normalize_cefr_level(requirement.get("required_level")) or "ANY"
        if required_level != "ANY" and _cefr_rank(required_level) > _cefr_rank(max_german):
            reasons.append(f"German level requirement ({required_level}) is above configured maximum ({max_german}).")


def detect_reasons(
    job: dict[str, Any],
    german_special_char_threshold: int,
    french_special_char_threshold: int,
    spanish_special_char_threshold: int,
    max_german_level: str,
    profile_languages: Any = None,
) -> list[str]:
    text = _job_language_text(job)
    reasons: list[str] = []

    _append_required_language_reasons(
        reasons,
        detect_language_requirements(text),
        profile_languages=profile_languages,
        max_german_level=max_german_level,
    )

    _append_listing_language_reason(
        reasons,
        language_name="German",
        count=count_special_markers(text, GERMAN_SPECIAL_MARKERS),
        threshold=max(0, int(german_special_char_threshold or 0)),
    )
    _append_listing_language_reason(
        reasons,
        language_name="French",
        count=count_special_markers(text, FRENCH_SPECIAL_MARKERS),
        threshold=max(0, int(french_special_char_threshold or 0)),
    )
    _append_listing_language_reason(
        reasons,
        language_name="Spanish",
        count=count_special_markers(text, SPANISH_SPECIAL_MARKERS),
        threshold=max(0, int(spanish_special_char_threshold or 0)),
    )

    deduped: list[str] = []
    for reason in reasons:
        if reason not in deduped:
            deduped.append(reason)
    return deduped


__all__ = [
    "DEFAULT_FRENCH_SPECIAL_CHAR_THRESHOLD",
    "DEFAULT_GERMAN_SPECIAL_CHAR_THRESHOLD",
    "DEFAULT_SPANISH_SPECIAL_CHAR_THRESHOLD",
    "LANGUAGE_ALIASES",
    "count_special_markers",
    "detect_language_requirements",
    "detect_reasons",
    "extract_profile_language_levels",
    "normalize_cefr_level",
]
