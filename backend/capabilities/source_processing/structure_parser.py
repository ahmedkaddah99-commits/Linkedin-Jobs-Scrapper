from __future__ import annotations

import re
from typing import Any

_HEADING_PATTERN = re.compile(
    r"^\s*"
    r"(?:"
    r"(?:[A-Z][A-Z\s&/-]{3,}(?:\s*:?))"
    r"|"
    r"(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,6}\s*:?)"
    r"|"
    r"(?:#+\s+.+)"
    r"|"
    r"(?:\d+(?:\.\d+)*\s+.+)"
    r"|"
    r"(?:[-–—]{2,}\s*.*)"
    r")"
    r"\s*$",
    re.MULTILINE,
)

_BULLET_PATTERN = re.compile(
    r"^\s*(?:[-•·●○▪▸►⦁]\s+|(?:[*+]\s+)|(?:\d+[.)]\s+)).+$",
    re.MULTILINE,
)

_CERTIFICATE_PATTERN = re.compile(
    r"(?i)\b("
    r"(?:AWS|Azure|Google\s*Cloud|GCP|ISC2|CompTIA|PMI|Scrum|SAFe|ITIL|CISSP|"
    r"CCSP|CISA|CISM|CRISC|CEH|Security\+|Network\+|A\+|"
    r"TOGAF|Six\s*Sigma|Lean|Kaizen|PRINCE2|CAPM|PMP|"
    r"CFA|CPA|CMA|FRM|"
    r"ICAgile|PSM|CSM|CSPO|"
    r"Microsoft\s*Certified|Oracle\s*Certified|"
    r"Salesforce|HubSpot|"
    r"Certified|Certificate|Certification|Diploma)\b"
    r"[^.]*\bcertif(?:ied|icate|ication)\b"
    r"|[^.]*\bcertif(?:ied|icate|ication)\b[^.]*\b("
    r"(?:AWS|Azure|Google\s*Cloud|GCP|ISC2|CompTIA|PMI|Scrum|SAFe|ITIL|CISSP|"
    r"CCSP|CISA|CISM|CRISC|CEH|Security\+|Network\+|A\+|"
    r"TOGAF|Six\s*Sigma|Lean|Kaizen|PRINCE2|CAPM|PMP|"
    r"CFA|CPA|CMA|FRM|"
    r"ICAgile|PSM|CSM|CSPO|"
    r"Microsoft\s*Certified|Oracle\s*Certified|"
    r"Salesforce|HubSpot|"
    r"Certified|Certificate|Certification|Diploma)\b"
    r")"
    r")",
    re.MULTILINE,
)
_DATE_PATTERN = re.compile(
    r"\b("
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+\d{4}"
    r"|"
    r"\d{2}/\d{4}"
    r"|"
    r"\d{4}"
    r")"
    r"\s*(?:[-–—]|to|through|until)\s*"
    r"("
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+\d{4}"
    r"|"
    r"\d{2}/\d{4}"
    r"|"
    r"\d{4}"
    r"|"
    r"Present|Current|Now|today"
    r")\b",
    re.IGNORECASE,
)

_STANDALONE_DATE_PATTERN = re.compile(
    r"\b("
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+\d{4}"
    r"|"
    r"\d{4}"
    r")\b",
    re.IGNORECASE,
)

_EMPLOYER_PATTERNS = [
    re.compile(r"(?:Employer|Company|Organization|Firm|Employed\s*(?:at|by))\s*:?\s*(.+)", re.IGNORECASE),
    re.compile(r"(?:Work(?:ed|ing)?\s*(?:at|for|with))\s+(.+)", re.IGNORECASE),
    re.compile(r"^(.+)\s+(?:\d{4}\s*[-–—]\s*(?:\d{4}|Present))", re.MULTILINE),
]

_ROLE_PATTERNS = [
    re.compile(r"(?:Role|Position|Title|Job\s*Title|Function)\s*:?\s*(.+)", re.IGNORECASE),
    re.compile(
        r"(?:as\s+(?:a|an)\s+)?([^.]+?(?:Engineer|Manager|Analyst|Developer|Consultant|Designer|"
        r"Architect|Scientist|Director|Lead|Head|Officer|Specialist|Coordinator|"
        r"Administrator|Assistant|Associate|VP|Vice\s*President)[^.]*)",
        re.IGNORECASE,
    ),
]


def _extract_headings(text: str) -> list[str]:
    matches = _HEADING_PATTERN.findall(text)
    return [line.strip() for line in matches if line.strip()]


def _extract_bullets(text: str) -> list[str]:
    matches = _BULLET_PATTERN.findall(text)
    return [line.strip() for line in matches if line.strip()]


def _extract_certificates(text: str) -> list[str]:
    matches = _CERTIFICATE_PATTERN.findall(text)
    results: list[str] = []
    for match in matches:
        if isinstance(match, tuple):
            for item in match:
                if item:
                    results.append(item.strip())
        elif match:
            results.append(match.strip())
    return list(dict.fromkeys(results))


def _extract_dates(text: str) -> list[str]:
    range_matches = _DATE_PATTERN.findall(text)
    results: list[str] = []
    for match in range_matches:
        if isinstance(match, tuple) and len(match) >= 2 and match[0] and match[1]:
            results.append(f"{match[0]} – {match[1]}")
    standalone = _STANDALONE_DATE_PATTERN.findall(text)
    for date_str in standalone:
        if not any(date_str in existing for existing in results):
            results.append(date_str)
    return list(dict.fromkeys(results))


def _extract_employer(text: str) -> str:
    for pattern in _EMPLOYER_PATTERNS:
        match = pattern.search(text)
        if match:
            employer = match.group(1).strip()
            employer = re.sub(r"\s*[.,;:]\s*$", "", employer)
            if employer and len(employer) < 80:
                return employer
    return ""


def _extract_role(text: str) -> str:
    for pattern in _ROLE_PATTERNS:
        match = pattern.search(text)
        if match:
            role = match.group(1).strip()
            role = re.sub(r"\s*[.,;:]\s*$", "", role)
            if role and len(role) < 120:
                return role
    return ""


def _extract_letter_paragraphs(text: str) -> list[str]:
    """Detect cover letter paragraphs between salutation and closing."""
    lines = text.splitlines()
    salutations = {"dear", "to whom", "hiring manager", "recruiting team",
                    "hr team", "hello", "hi"}
    closings = {"sincerely", "best regards", "kind regards", "yours faithfully",
                "yours truly", "regards", "thank you for your consideration",
                "looking forward", "i look forward"}

    paragraphs: list[str] = []
    in_letter = False
    current: list[str] = []
    gap = 0

    for line in lines:
        stripped = line.strip()
        lower = stripped.lower()

        if not in_letter:
            if any(lower.startswith(m) for m in salutations):
                in_letter = True
                continue
        else:
            if any(m in lower for m in closings):
                in_letter = False
                if current:
                    paragraphs.append(" ".join(current).strip())
                current = []
                continue

            if not stripped:
                if current:
                    paragraphs.append(" ".join(current).strip())
                    current = []
                gap += 1
                if gap > 10:
                    in_letter = False
                continue

            current.append(stripped)
            gap = 0

    if current and in_letter:
        paragraphs.append(" ".join(current).strip())

    filtered: list[str] = []
    for para in paragraphs:
        clean = para.strip()
        if len(clean) < 15:
            continue
        if re.match(r"^[\d\s\-,.()/+@]+$", clean):
            continue
        filtered.append(clean)

    return filtered


def parse_structured_fields(text: str) -> dict[str, Any]:
    """Extract structured fields from raw text using heuristics."""
    if not text or not text.strip():
        return {
            "employer": "",
            "role": "",
            "dates": [],
            "headings": [],
            "bullets": [],
            "certificates": [],
            "letter_paragraphs": [],
        }

    return {
        "employer": _extract_employer(text),
        "role": _extract_role(text),
        "dates": _extract_dates(text),
        "headings": _extract_headings(text),
        "bullets": _extract_bullets(text),
        "certificates": _extract_certificates(text),
        "letter_paragraphs": _extract_letter_paragraphs(text),
    }
