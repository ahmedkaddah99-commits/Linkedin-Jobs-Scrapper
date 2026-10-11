"""Deterministic domain boundaries for the inactive enrichment foundation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import re
import unicodedata
from typing import Any, Protocol

from .contracts import EnrichmentRequest, ProviderExecutionContext, ProviderResult


class PlaceNormalizer(Protocol):
    def resolve(self, request: EnrichmentRequest, context: ProviderExecutionContext) -> ProviderResult: ...


class CompanyProfileResolver(Protocol):
    def resolve(self, request: EnrichmentRequest, context: ProviderExecutionContext) -> ProviderResult: ...


class OccupationMapper(Protocol):
    def resolve(self, request: EnrichmentRequest, context: ProviderExecutionContext) -> ProviderResult: ...


class LanguageRequirementResolver(Protocol):
    def extract(
        self, *, structured: Any = None, description: str = "", posting_language: str = ""
    ) -> tuple["LanguageEvidence", ...]: ...


@dataclass(frozen=True, slots=True)
class PlaceInput:
    raw_display: str
    workplace_arrangement: str = ""
    remote_scope: str = ""


@dataclass(frozen=True, slots=True)
class LanguageEvidence:
    language: str
    status: str
    proficiency: str = ""
    evidence: str = ""
    extraction_method: str = ""


LANGUAGE_STATES = frozenset({"required", "preferred", "mentioned", "not_established"})
_LANGUAGE_ALIASES = {
    "de": "German",
    "deutsch": "German",
    "german": "German",
    "en": "English",
    "english": "English",
    "fr": "French",
    "français": "French",
    "french": "French",
    "es": "Spanish",
    "spanish": "Spanish",
    "nl": "Dutch",
    "dutch": "Dutch",
}
_LANGUAGE_WORDS = "|".join(re.escape(item) for item in sorted(_LANGUAGE_ALIASES, key=len, reverse=True))
_PROFICIENCY = r"(?:A1|A2|B1|B2|C1|C2|native|fluent|near-native)"


def normalize_text(value: Any) -> str:
    """Normalize matching text without changing the preserved display value."""

    return " ".join(unicodedata.normalize("NFKC", str(value or "")).split()).casefold()


def split_place_inputs(raw: Any, *, workplace_arrangement: str = "", remote_scope: str = "") -> tuple[PlaceInput, ...]:
    """Split structured locations while preserving comma-delimited place names."""

    values: list[Any]
    if isinstance(raw, Mapping):
        values = [raw.get("name") or raw.get("address") or raw.get("location") or ""]
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        values = list(raw)
    else:
        values = re.split(r"\s*[;|]\s*", str(raw or ""))

    result: list[PlaceInput] = []
    for value in values:
        if isinstance(value, Mapping):
            value = value.get("name") or value.get("address") or value.get("location") or ""
        display = " ".join(str(value or "").split())
        if not display:
            continue
        normalized_display = normalize_text(display)
        if (
            normalized_display in {"remote", "hybrid", "flexible", "worldwide", "global"}
            or normalized_display.startswith("remote ")
            or normalized_display.startswith("remote-")
        ):
            continue
        result.append(
            PlaceInput(
                raw_display=display,
                workplace_arrangement=str(workplace_arrangement or "").strip(),
                remote_scope=str(remote_scope or "").strip(),
            )
        )
    return tuple(result)


def build_place_requests(
    *,
    target_id: str,
    raw_location: Any,
    country_code: str = "",
    region: str = "",
    workplace_arrangement: str = "",
    remote_scope: str = "",
    policy_version: str = "enrichment_policy_v1",
    rule_version: str = "place_normalization_v1",
) -> tuple[EnrichmentRequest, ...]:
    """Build independent place requests; remote is context, not geography."""

    requests: list[EnrichmentRequest] = []
    for index, place in enumerate(
        split_place_inputs(
            raw_location,
            workplace_arrangement=workplace_arrangement,
            remote_scope=remote_scope,
        )
    ):
        requests.append(
            EnrichmentRequest(
                target_type="place",
                target_id=f"{target_id}:location:{index}",
                field_path="job_location",
                input={
                    "display": place.raw_display,
                    "country_code": country_code,
                    "region": region,
                },
                context={
                    "workplace_arrangement": place.workplace_arrangement,
                    "remote_scope": place.remote_scope,
                },
                policy_version=policy_version,
                rule_version=rule_version,
            )
        )
    return tuple(requests)


def company_identity_can_auto_link(*, domain: str = "", legal_entity_id: str = "", name: str = "") -> bool:
    """Name-only matches are candidates, never automatic company links."""

    del name
    return bool(str(domain or "").strip() or str(legal_entity_id or "").strip())


def build_company_request(
    *,
    target_id: str,
    name: str = "",
    domain: str = "",
    legal_entity_id: str = "",
    field_path: str = "company_identity",
    policy_version: str = "enrichment_policy_v1",
    rule_version: str = "company_identity_v1",
) -> EnrichmentRequest:
    return EnrichmentRequest(
        target_type="company",
        target_id=target_id,
        field_path=field_path,
        input={
            "name": str(name or "").strip(),
            "domain": str(domain or "").strip(),
            "legal_entity_id": str(legal_entity_id or "").strip(),
        },
        context={"name_only_auto_link_allowed": False},
        policy_version=policy_version,
        rule_version=rule_version,
    )


def build_occupation_request(
    *,
    target_id: str,
    title: str,
    department: str = "",
    description_excerpt: str = "",
    policy_version: str = "enrichment_policy_v1",
    rule_version: str = "occupation_mapping_v1",
) -> EnrichmentRequest:
    return EnrichmentRequest(
        target_type="occupation",
        target_id=target_id,
        field_path="occupation",
        input={"title": str(title or "").strip(), "department": str(department or "").strip()},
        context={"description_excerpt": str(description_excerpt or "")[:1000]},
        policy_version=policy_version,
        rule_version=rule_version,
    )


def _language_name(value: Any) -> str:
    token = normalize_text(value)
    return _LANGUAGE_ALIASES.get(token, "")


def _structured_language_items(structured: Any) -> list[Mapping[str, Any]]:
    if isinstance(structured, Mapping):
        return [
            {"language": key, **(value if isinstance(value, Mapping) else {"status": value})}
            for key, value in structured.items()
        ]
    if isinstance(structured, Sequence) and not isinstance(structured, (str, bytes)):
        return [item for item in structured if isinstance(item, Mapping)]
    return []


def extract_language_evidence(
    *,
    structured: Any = None,
    description: str = "",
    posting_language: str = "",
) -> tuple[LanguageEvidence, ...]:
    """Extract only explicit/labeled language evidence.

    ``posting_language`` is intentionally ignored.  The language used to write
    a posting is not proof of a required language or proficiency.
    """

    del posting_language
    result: list[LanguageEvidence] = []
    for item in _structured_language_items(structured):
        language = _language_name(item.get("language") or item.get("name") or item.get("value"))
        if not language:
            continue
        status = normalize_text(item.get("status") or item.get("requirement") or "mentioned")
        status = status if status in {"required", "preferred", "mentioned"} else "mentioned"
        proficiency = str(item.get("proficiency") or item.get("level") or "").strip()
        result.append(
            LanguageEvidence(
                language, status, proficiency, str(item.get("evidence") or ""), "structured_language_field"
            )
        )
    if result:
        return tuple(result)

    for match in re.finditer(
        rf"(?im)^\s*(?P<label>required|preferred)?\s*languages?\s*[:\-]\s*(?P<values>[^\n]+)",
        str(description or ""),
    ):
        label = normalize_text(match.group("label"))
        status = label if label in {"required", "preferred"} else "mentioned"
        for item in re.split(r",|\s+and\s+|\s*&\s*", match.group("values"), flags=re.IGNORECASE):
            language_match = re.search(rf"(?i)\b({_LANGUAGE_WORDS})\b", item)
            if not language_match:
                continue
            language = _language_name(language_match.group(1))
            proficiency_match = re.search(rf"\b({_PROFICIENCY})\b", item, flags=re.IGNORECASE)
            result.append(
                LanguageEvidence(
                    language,
                    status,
                    proficiency_match.group(1) if proficiency_match else "",
                    match.group(0).strip(),
                    "labeled_language_text",
                )
            )

    explicit_patterns = (
        rf"\b(?P<language>{_LANGUAGE_WORDS})(?:\s+(?P<proficiency>{_PROFICIENCY}))?\s+(?P<status>is\s+)?required\b",
        rf"\b(?P<language>{_LANGUAGE_WORDS})(?:\s+(?P<proficiency>{_PROFICIENCY}))?\s+(?P<status>is\s+)?preferred\b",
        rf"\bmust\s+(?:speak|be\s+fluent\s+in)\s+(?P<language>{_LANGUAGE_WORDS})\b",
    )
    for pattern in explicit_patterns:
        for match in re.finditer(pattern, str(description or ""), flags=re.IGNORECASE):
            language = _language_name(match.group("language"))
            status = "preferred" if "preferred" in match.group(0).casefold() else "required"
            result.append(
                LanguageEvidence(
                    language,
                    status,
                    str(match.groupdict().get("proficiency") or ""),
                    match.group(0).strip(),
                    "explicit_language_clause",
                )
            )

    deduplicated: dict[tuple[str, str, str], LanguageEvidence] = {}
    for item in result:
        deduplicated[(item.language, item.status, item.proficiency)] = item
    return tuple(deduplicated.values())


def language_state(evidence: Sequence[LanguageEvidence]) -> str:
    if not evidence:
        return "not_established"
    if any(item.status == "required" for item in evidence):
        return "required"
    if any(item.status == "preferred" for item in evidence):
        return "preferred"
    return "mentioned"


__all__ = [
    "CompanyProfileResolver",
    "LanguageEvidence",
    "LanguageRequirementResolver",
    "LANGUAGE_STATES",
    "OccupationMapper",
    "PlaceInput",
    "PlaceNormalizer",
    "build_company_request",
    "build_occupation_request",
    "build_place_requests",
    "company_identity_can_auto_link",
    "extract_language_evidence",
    "language_state",
    "normalize_text",
    "split_place_inputs",
]
