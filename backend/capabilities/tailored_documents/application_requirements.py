from __future__ import annotations

import re
from typing import Any, Mapping


APPLICATION_REQUIREMENTS_VERSION = "2026-05-31.cv-language-v2"

_REQUEST_CONTEXT_PATTERN = re.compile(
    r"\b("
    r"attach|attached|attachment|include|including|submit|send|sent|upload|uploaded|provide|provided|"
    r"required|requirement|mandatory|must|please|application|bewerbung|bewerbungsunterlagen|"
    r"beifugen|beifuegen|einreichen|hochladen|mitsenden"
    r")\b",
    re.IGNORECASE,
)

_NO_PHOTO_PATTERNS = (
    re.compile(r"\b(?:cv|resume|curriculum\s+vitae|lebenslauf)\b.{0,80}\bwithout\s+(?:a\s+)?(?:photo|picture)\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\bwithout\s+(?:a\s+)?(?:photo|picture)\b.{0,80}\b(?:cv|resume|curriculum\s+vitae)\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\bno\s+(?:photo|picture)\b.{0,80}\b(?:cv|resume|curriculum\s+vitae)\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\b(?:cv|resume|curriculum\s+vitae)\b.{0,80}\bno\s+(?:photo|picture)\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\b(?:lebenslauf)\b.{0,80}\bohne\s+(?:foto|bild)\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\bohne\s+(?:foto|bild)\b.{0,80}\b(?:lebenslauf|bewerbung)\b", re.IGNORECASE | re.DOTALL),
)

_DOCUMENT_REQUIREMENTS = (
    {
        "document_type": "motivation_letter",
        "label": "Motivation letter",
        "patterns": (
            re.compile(r"\bmotivation\s+letter\b", re.IGNORECASE),
            re.compile(r"\bletter\s+of\s+motivation\b", re.IGNORECASE),
            re.compile(r"\bcover\s+letter\b", re.IGNORECASE),
            re.compile(r"\banschreiben\b", re.IGNORECASE),
            re.compile(r"\bmotivationsschreiben\b", re.IGNORECASE),
        ),
    },
    {
        "document_type": "recommendation_letter",
        "label": "Recommendation letter",
        "patterns": (
            re.compile(r"\brecommendation\s+letter\b", re.IGNORECASE),
            re.compile(r"\bletter\s+of\s+recommendation\b", re.IGNORECASE),
            re.compile(r"\breference\s+letter\b", re.IGNORECASE),
            re.compile(r"\brecommendations?\b", re.IGNORECASE),
            re.compile(r"\breferenzschreiben\b", re.IGNORECASE),
        ),
    },
    {
        "document_type": "transcript",
        "label": "Transcript of records",
        "patterns": (
            re.compile(r"\btranscript(?:\s+of\s+records)?\b", re.IGNORECASE),
            re.compile(r"\brecords?\s+of\s+study\b", re.IGNORECASE),
            re.compile(r"\bnotenspiegel\b", re.IGNORECASE),
            re.compile(r"\bleistungsubersicht\b", re.IGNORECASE),
            re.compile(r"\bleistungsuebersicht\b", re.IGNORECASE),
        ),
    },
    {
        "document_type": "grades",
        "label": "Grades",
        "patterns": (
            re.compile(r"\bgrade\s+(?:report|overview|sheet|certificate)\b", re.IGNORECASE),
            re.compile(r"\bgrades?\b", re.IGNORECASE),
            re.compile(r"\bnoten\b", re.IGNORECASE),
        ),
    },
    {
        "document_type": "degree_certificate",
        "label": "Degree certificate",
        "patterns": (
            re.compile(r"\bdegree\s+certificate\b", re.IGNORECASE),
            re.compile(r"\buniversity\s+certificate\b", re.IGNORECASE),
            re.compile(r"\bfinal\s+(?:university\s+)?certificate\b", re.IGNORECASE),
            re.compile(r"\bdiploma\b", re.IGNORECASE),
            re.compile(r"\babschlusszeugnis\b", re.IGNORECASE),
            re.compile(r"\babschlussurkunde\b", re.IGNORECASE),
        ),
    },
)

_CV_LANGUAGE_TARGETS = (
    {
        "language": "German",
        "aliases": r"(?:german|deutsch(?:er|e|en|es)?(?:\s+sprache)?)",
    },
    {
        "language": "English",
        "aliases": r"(?:english|englisch(?:er|e|en|es)?(?:\s+sprache)?)",
    },
    {
        "language": "French",
        "aliases": r"(?:french|franzoesisch(?:er|e|en|es)?(?:\s+sprache)?)",
    },
    {
        "language": "Spanish",
        "aliases": r"(?:spanish|spanisch(?:er|e|en|es)?(?:\s+sprache)?)",
    },
)

_CV_DOCUMENT_CONTEXT = (
    r"(?:cv|resume|curriculum\s+vitae|application(?:\s+(?:documents|materials))?|"
    r"documents|lebenslauf|bewerbungsunterlagen|bewerbung|unterlagen)"
)
_CV_SUBMIT_CONTEXT = (
    r"(?:submit|send|upload|provide|attach|include|apply|einreichen|hochladen|"
    r"mitsenden|beifuegen|beifugen|bewerben|bewirb)"
)

_CV_SOURCE_LANGUAGE_MARKERS = {
    "English": (
        r"\bprofessional\s+summary\b",
        r"\bwork\s+experience\b",
        r"\bprofessional\s+experience\b",
        r"\bexperience\b",
        r"\beducation\b",
        r"\bskills\b",
        r"\blanguages\b",
        r"\bprojects\b",
        r"\bcertifications?\b",
    ),
    "German": (
        r"\blebenslauf\b",
        r"\bberufserfahrung\b",
        r"\bberufliche\s+erfahrung\b",
        r"\bausbildung\b",
        r"\bstudium\b",
        r"\bkenntnisse\b",
        r"\bf(?:ae|\u00e4)higkeiten\b",
        r"\bsprachkenntnisse\b",
        r"\bsprachen\b",
        r"\babschluss\b",
        r"\bpraktikum\b",
    ),
}


def _compile_cv_language_patterns() -> tuple[dict[str, Any], ...]:
    compiled: list[dict[str, Any]] = []
    for definition in _CV_LANGUAGE_TARGETS:
        aliases = str(definition["aliases"])
        compiled.append(
            {
                "language": str(definition["language"]),
                "patterns": (
                    re.compile(
                        rf"\b{_CV_DOCUMENT_CONTEXT}\b.{{0,90}}\b(?:in|auf)\s+(?:a\s+)?{aliases}\b",
                        re.IGNORECASE | re.DOTALL,
                    ),
                    re.compile(
                        rf"\b{aliases}\b(?:[\s\-]+(?:version|language|sprachige|sprachiger|sprachiges))?[\s\-]+{_CV_DOCUMENT_CONTEXT}\b",
                        re.IGNORECASE | re.DOTALL,
                    ),
                    re.compile(
                        rf"\b{_CV_SUBMIT_CONTEXT}\b.{{0,140}}\b{_CV_DOCUMENT_CONTEXT}\b.{{0,100}}\b(?:in|auf)\s+(?:a\s+)?{aliases}\b",
                        re.IGNORECASE | re.DOTALL,
                    ),
                    re.compile(
                        rf"\bapplications?\b.{{0,80}}\b(?:in|auf)\s+(?:a\s+)?{aliases}\b",
                        re.IGNORECASE | re.DOTALL,
                    ),
                    re.compile(
                        rf"\bbewerbung(?:sunterlagen)?\b.{{0,90}}\b(?:in|auf)\s+{aliases}\b",
                        re.IGNORECASE | re.DOTALL,
                    ),
                ),
            }
        )
    return tuple(compiled)


_CV_LANGUAGE_REQUIREMENT_PATTERNS = _compile_cv_language_patterns()


def _compact(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _job_requirement_text(job: Mapping[str, Any]) -> str:
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
        )
        if _compact(job.get(key))
    )


def _evidence_for_match(text: str, start: int, end: int, *, radius: int = 96) -> str:
    left = max(0, int(start) - radius)
    right = min(len(text), int(end) + radius)
    snippet = _compact(text[left:right])
    if left > 0:
        snippet = f"...{snippet}"
    if right < len(text):
        snippet = f"{snippet}..."
    return snippet


def _has_request_context(text: str, start: int, end: int) -> bool:
    left = max(0, int(start) - 90)
    right = min(len(text), int(end) + 90)
    return bool(_REQUEST_CONTEXT_PATTERN.search(text[left:right]))


def _detect_no_photo_requirement(text: str) -> dict[str, Any]:
    for pattern in _NO_PHOTO_PATTERNS:
        match = pattern.search(text)
        if match:
            return {
                "requires_no_photo": True,
                "evidence": _evidence_for_match(text, match.start(), match.end()),
                "confidence": "high",
            }
    return {"requires_no_photo": False, "evidence": "", "confidence": ""}


def _detect_required_documents(text: str) -> list[dict[str, Any]]:
    required_documents: list[dict[str, Any]] = []
    seen: set[str] = set()
    for definition in _DOCUMENT_REQUIREMENTS:
        document_type = str(definition["document_type"])
        for pattern in definition["patterns"]:
            match = pattern.search(text)
            if not match:
                continue
            if not _has_request_context(text, match.start(), match.end()):
                continue
            if document_type in seen:
                break
            seen.add(document_type)
            required_documents.append(
                {
                    "document_type": document_type,
                    "label": str(definition["label"]),
                    "evidence": _evidence_for_match(text, match.start(), match.end()),
                    "confidence": "medium",
                }
            )
            break
    return required_documents


def _detect_cv_language_requirement(text: str) -> dict[str, Any]:
    for definition in _CV_LANGUAGE_REQUIREMENT_PATTERNS:
        for pattern in definition["patterns"]:
            match = pattern.search(text)
            if match:
                return {
                    "target_language": str(definition["language"]),
                    "evidence": _evidence_for_match(text, match.start(), match.end()),
                    "confidence": "high",
                }
    return {"target_language": "", "evidence": "", "confidence": ""}


def _infer_cv_source_language(cv_text: str) -> str:
    text = str(cv_text or "").casefold()
    if not text.strip():
        return ""

    scores: dict[str, int] = {}
    for language, markers in _CV_SOURCE_LANGUAGE_MARKERS.items():
        score = 0
        for marker in markers:
            score += len(re.findall(marker, text, flags=re.IGNORECASE))
        scores[language] = score

    if not scores:
        return ""
    best_language, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score < 2:
        return ""
    competing_scores = [score for language, score in scores.items() if language != best_language]
    if competing_scores and best_score == max(competing_scores):
        return ""
    return best_language


def _cv_language_requirements(
    text: str,
    *,
    cv_text: str = "",
    cv_can_translate: bool = False,
) -> dict[str, Any]:
    requirement = _detect_cv_language_requirement(text)
    source_language = _infer_cv_source_language(cv_text)
    target_language = str(requirement.get("target_language") or "").strip()
    translation_required = bool(target_language and source_language and target_language != source_language)
    if target_language and (cv_can_translate or not source_language):
        output_language = target_language
    else:
        output_language = source_language or target_language or "English"
    return {
        **requirement,
        "source_language": source_language,
        "output_language": output_language,
        "translation_required": translation_required,
        "can_translate": bool(cv_can_translate),
        "will_translate": bool(translation_required and cv_can_translate),
    }


def detect_application_requirements(
    job: Mapping[str, Any],
    *,
    cv_includes_photo: bool = False,
    cv_text: str = "",
    cv_can_translate: bool = False,
) -> dict[str, Any]:
    text = _job_requirement_text(job)
    no_photo = _detect_no_photo_requirement(text)
    required_documents = _detect_required_documents(text)
    language_requirements = _cv_language_requirements(
        text,
        cv_text=cv_text,
        cv_can_translate=cv_can_translate,
    )
    warnings: list[dict[str, Any]] = []

    if no_photo["requires_no_photo"]:
        conflict = bool(cv_includes_photo)
        warnings.append(
            {
                "code": "cv_photo_conflict" if conflict else "cv_without_photo_requested",
                "severity": "blocking" if conflict else "review",
                "title": "CV photo conflicts with job instructions" if conflict else "CV without photo requested",
                "message": (
                    "The job instructions ask for a CV without a photo, but this workspace is configured to include one."
                    if conflict
                    else "The job instructions ask for a CV without a photo."
                ),
                "evidence": no_photo["evidence"],
            }
        )

    target_language = str(language_requirements.get("target_language") or "").strip()
    source_language = str(language_requirements.get("source_language") or "").strip()
    translation_required = bool(language_requirements.get("translation_required"))
    if target_language:
        if translation_required and not cv_can_translate:
            warnings.append(
                {
                    "code": "cv_language_conflict",
                    "severity": "blocking",
                    "title": f"{target_language} CV requested",
                    "message": (
                        f"The job instructions ask for a {target_language} CV, but the baseline CV appears "
                        f"to be {source_language}. Generate or upload a {target_language} CV before applying."
                    ),
                    "evidence": language_requirements.get("evidence", ""),
                }
            )
        elif translation_required and cv_can_translate:
            warnings.append(
                {
                    "code": "cv_language_translation_planned",
                    "severity": "review",
                    "title": f"{target_language} CV requested",
                    "message": (
                        f"The job instructions ask for a {target_language} CV. The baseline CV appears "
                        f"to be {source_language}, so the generated CV will be written in {target_language}."
                    ),
                    "evidence": language_requirements.get("evidence", ""),
                }
            )
        else:
            warnings.append(
                {
                    "code": "cv_language_requirement_detected",
                    "severity": "review",
                    "title": f"{target_language} CV requested",
                    "message": f"The job instructions ask for a {target_language} CV.",
                    "evidence": language_requirements.get("evidence", ""),
                }
            )

    for document in required_documents:
        warnings.append(
            {
                "code": "required_document_detected",
                "severity": "review",
                "title": f"{document['label']} requested",
                "message": f"The job instructions mention a required {str(document['label']).lower()}.",
                "document_type": document["document_type"],
                "evidence": document["evidence"],
            }
        )

    return {
        "version": APPLICATION_REQUIREMENTS_VERSION,
        "cv_requirements": {
            **no_photo,
            "configured_with_photo": bool(cv_includes_photo),
            "photo_conflict": bool(no_photo["requires_no_photo"] and cv_includes_photo),
            "language": language_requirements,
        },
        "required_documents": required_documents,
        "warnings": warnings,
    }


__all__ = [
    "APPLICATION_REQUIREMENTS_VERSION",
    "detect_application_requirements",
]
