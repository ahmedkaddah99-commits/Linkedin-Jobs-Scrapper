"""Deterministic company identity crosswalks for the historical acquisition catalog.

This module is intentionally pure and non-destructive.  It turns registry rows
into a durable old/source identity -> surviving canonical company ID map.  The
caller persists that map and applies it to versioned producer-state copies and
the canonical acquisition store in separate transactions.

Identity rules are ordered deliberately:

* exact normalized LinkedIn organization URL is the primary identity;
* numeric LinkedIn organization ID and CompanyEnrich ID corroborate it;
* website/domain is evidence only and never merges companies by itself; a full
  website URL may allocate a deterministic seed when no stronger identity is
  available;
* company name is an alias/evidence field, never an identity seed.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit


SCHEMA_VERSION = "runr.company_identity_crosswalk.v1"
MISSING_ID_MARKERS = frozenset({"", "//", "-", "--", "/", "null", "none", "nan", "n/a", "na", "unknown", "pending"})
STRONG_IDENTITY_TYPES = ("linkedin_org_url", "linkedin_org_id", "companyenrich_id")


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _value(value: Any) -> str:
    candidate = _text(value)
    return "" if candidate.casefold() in MISSING_ID_MARKERS else candidate


def _normal_numeric_id(value: Any) -> str:
    candidate = _value(value)
    return str(int(candidate)) if candidate.isascii() and candidate.isdecimal() else ""


def _normalize_linkedin_org_url(value: Any) -> str:
    raw = _text(value)
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return ""
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    if host != "linkedin.com" and not host.endswith(".linkedin.com"):
        return ""
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or parts[0].casefold() != "company":
        return ""
    slug = parts[1].strip().casefold()
    if not slug:
        return ""
    return f"https://www.linkedin.com/company/{slug}"


def _normalize_domain(value: Any) -> str:
    raw = _text(value)
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    try:
        host = (urlsplit(raw).hostname or "").casefold().removeprefix("www.")
    except ValueError:
        return ""
    return host if host and "." in host else ""


def _linkedin_identity_url(row: Mapping[str, Any]) -> str:
    value = row.get("linkedin_company_url") or row.get("linkedin_url")
    if _text(value):
        return _text(value)
    slug = _text(row.get("linkedin_slug"))
    page_type = _text(row.get("linkedin_page_type")).casefold()
    if slug and page_type in {"", "company", "organization"} and "/" not in slug and " " not in slug:
        return f"https://www.linkedin.com/company/{slug}"
    return ""


def _row_fingerprint(row: Mapping[str, Any]) -> str:
    payload = json.dumps({str(key): row[key] for key in sorted(row)}, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _strong_identity_keys(row: Mapping[str, Any]) -> list[tuple[str, str]]:
    keys: list[tuple[str, str]] = []
    linkedin_url = _normalize_linkedin_org_url(_linkedin_identity_url(row))
    if linkedin_url:
        keys.append(("linkedin_org_url", f"linkedin-org-url:{linkedin_url}"))
    linkedin_id = _normal_numeric_id(row.get("linkedin_company_id") or row.get("linkedin_org_id"))
    if linkedin_id:
        keys.append(("linkedin_org_id", f"linkedin-org:{linkedin_id}"))
    companyenrich_id = _value(row.get("companyenrich_id") or row.get("company_enrich_id"))
    if companyenrich_id:
        keys.append(("companyenrich_id", f"companyenrich:{companyenrich_id.casefold()}"))
    return keys


def _website_key(row: Mapping[str, Any]) -> str:
    domain = _normalize_domain(row.get("website_url") or row.get("website") or row.get("domain"))
    return f"domain:{domain}" if domain else ""


def _website_seed_key(row: Mapping[str, Any]) -> str:
    raw = _text(row.get("website_url") or row.get("website") or row.get("domain"))
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return ""
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    if not host or "." not in host:
        return ""
    path = "/" + "/".join(part for part in parsed.path.split("/") if part)
    # Keep domain/website evidence from merging two distinct employers by
    # itself.  The row fingerprint only makes a deterministic seed for this
    # otherwise-unidentified row; exact LinkedIn/strong identities still use
    # the shared crosswalk and can merge explicitly.
    return f"website-url:https://{host}{path.rstrip('/')}|row:{_row_fingerprint(row)[:16]}"


def _identity_keys(row: Mapping[str, Any]) -> list[tuple[str, str]]:
    strong = _strong_identity_keys(row)
    if strong:
        return strong
    seed = _website_seed_key(row)
    if seed:
        return [("website_url_seed", seed)]
    existing_id = _value(row.get("canonical_CompanyID") or row.get("canonical_company_id"))
    return [("existing_company_id", f"old-company:{existing_id}")] if existing_id else []


def _richness_score(row: Mapping[str, Any]) -> tuple[int, str]:
    score = 0
    score += 3 if _value(row.get("canonical_CompanyID") or row.get("canonical_company_id")) else 0
    score += 3 if _normalize_linkedin_org_url(_linkedin_identity_url(row)) else 0
    score += 3 if _normal_numeric_id(row.get("linkedin_company_id") or row.get("linkedin_org_id")) else 0
    score += 2 if _value(row.get("companyenrich_id") or row.get("company_enrich_id")) else 0
    score += 2 if _website_key(row) else 0
    score += 2 if _value(row.get("logo_url") or row.get("companyenrich_logo_url")) else 0
    score += 2 if _value(row.get("description") or row.get("company_description")) else 0
    score += 2 if _value(row.get("enrichment_status")).casefold() in {"complete", "verified"} else 0
    score += sum(1 for field in ("industry", "company_type", "employee_count", "headquarters_display", "founded_year") if _value(row.get(field)))
    return score, _text(row.get("canonical_CompanyID") or row.get("canonical_company_id"))


def _stable_id(identity_key: str) -> str:
    digest = hashlib.sha256(f"runr-company:{identity_key}".encode("utf-8")).hexdigest()[:24]
    return f"canonical_company_{digest}"


def canonical_company_id_for_row(row: Mapping[str, Any]) -> str:
    """Return a deterministic ID without falling back to company name."""

    existing_id = _value(row.get("canonical_CompanyID") or row.get("canonical_company_id"))
    if existing_id:
        return existing_id
    keys = _identity_keys(row)
    if not keys:
        raise ValueError("company identity requires a LinkedIn organization URL, numeric organization ID, CompanyEnrich ID, or website URL seed; name-only fallback is forbidden")
    primary = next((key for identity_type, key in keys if identity_type == "linkedin_org_url"), keys[0][1])
    return _stable_id(primary)


@dataclass(frozen=True)
class CompanyCrosswalk:
    mapping_by_row: dict[int, str]
    mapping_by_identity: dict[str, str]
    report: dict[str, Any]

    @property
    def rows(self) -> list[dict[str, Any]]:
        value = self.report.get("canonical_rows")
        return list(value) if isinstance(value, list) else []


def build_company_crosswalk(rows: Iterable[Mapping[str, Any]]) -> CompanyCrosswalk:
    prepared = [dict(row) for row in rows if isinstance(row, Mapping)]
    identities_by_row: dict[int, list[tuple[str, str]]] = {
        index: _identity_keys(row) for index, row in enumerate(prepared)
    }
    missing_identity_rows = [index for index, keys in identities_by_row.items() if not keys]
    if missing_identity_rows:
        raise ValueError(f"rows without a non-name company identity: {missing_identity_rows[:20]}")

    existing_by_key: dict[str, set[str]] = defaultdict(set)
    rows_by_existing_id: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(prepared):
        existing_id = _value(row.get("canonical_CompanyID") or row.get("canonical_company_id"))
        if existing_id:
            rows_by_existing_id[existing_id].append(index)
            for identity_type, key in identities_by_row[index]:
                if identity_type in STRONG_IDENTITY_TYPES:
                    existing_by_key[key].add(existing_id)

    score_by_id = {
        company_id: max((_richness_score(prepared[index]) for index in row_indexes), default=(0, company_id))
        for company_id, row_indexes in rows_by_existing_id.items()
    }

    # URL/strong-key conflicts are resolved deterministically before allocating
    # any new IDs.  The receipt records each loser so a store migration can
    # transactionally repoint its dependencies later.
    winner_by_key: dict[str, str] = {}
    merge_receipts: list[dict[str, Any]] = []
    for key, candidates in sorted(existing_by_key.items()):
        ordered = sorted(candidates, key=lambda company_id: (-score_by_id.get(company_id, (0, company_id))[0], company_id))
        if ordered:
            winner = ordered[0]
            winner_by_key[key] = winner
            for loser in ordered[1:]:
                merge_receipts.append({
                    "receipt_id": "company_merge_" + hashlib.sha256(f"{key}:{loser}:{winner}".encode("utf-8")).hexdigest()[:24],
                    "identity_key": key,
                    "winner_company_id": winner,
                    "loser_company_id": loser,
                    "basis": "strong_identity_key_and_richness_score",
                    "winner_score": score_by_id.get(winner, (0, winner))[0],
                    "loser_score": score_by_id.get(loser, (0, loser))[0],
                    "dependencies_repointed": False,
                })

    mapping_by_row: dict[int, str] = {}
    mapping_by_identity: dict[str, str] = {}
    conflict_count = 0
    url_seed_allocations = 0
    identity_seed_allocations = 0
    domain_only_non_merges = 0
    for index, row in enumerate(prepared):
        original_id = _value(row.get("canonical_CompanyID") or row.get("canonical_company_id"))
        keys = identities_by_row[index]
        url_key = next((key for identity_type, key in keys if identity_type == "linkedin_org_url"), "")
        candidates = {winner_by_key[key] for _identity_type, key in keys if key in winner_by_key}
        if url_key and url_key in winner_by_key:
            winner = winner_by_key[url_key]
            if candidates - {winner}:
                conflict_count += 1
        elif candidates:
            winner = sorted(candidates, key=lambda company_id: (-score_by_id.get(company_id, (0, company_id))[0], company_id))[0]
        elif original_id:
            winner = original_id
        else:
            winner = _stable_id(url_key or keys[0][1])
            if url_key or any(identity_type == "website_url_seed" for identity_type, _key in keys):
                url_seed_allocations += 1
            else:
                identity_seed_allocations += 1
        mapping_by_row[index] = winner
        for _identity_type, key in keys:
            previous = mapping_by_identity.get(key)
            if previous and previous != winner:
                conflict_count += 1
            mapping_by_identity[key] = winner
        if original_id and original_id != winner:
            mapping_by_identity[f"old-company:{original_id}"] = winner
        website_key = _website_key(row)
        if website_key and website_key not in existing_by_key:
            domain_only_non_merges += 1

    # The same loser can be discovered through more than one corroborating
    # key (for example the LinkedIn URL and numeric organization ID).  Keep a
    # single transactional merge receipt per loser/winner pair while retaining
    # every identity key that justified it.
    grouped_receipts: dict[tuple[str, str], dict[str, Any]] = {}
    for receipt in merge_receipts:
        pair = (receipt["loser_company_id"], receipt["winner_company_id"])
        current = grouped_receipts.get(pair)
        if current is None:
            current = dict(receipt)
            current["identity_keys"] = [receipt["identity_key"]]
            grouped_receipts[pair] = current
        elif receipt["identity_key"] not in current["identity_keys"]:
            current["identity_keys"].append(receipt["identity_key"])
    unique_receipts = {
        f"{loser}:{winner}": receipt
        for (loser, winner), receipt in grouped_receipts.items()
    }
    report = {
        "schema_version": SCHEMA_VERSION,
        "rows_before": len(prepared),
        "canonical_ids_before": len({
            _value(row.get("canonical_CompanyID") or row.get("canonical_company_id"))
            for row in prepared
            if _value(row.get("canonical_CompanyID") or row.get("canonical_company_id"))
        }),
        "canonical_ids_after": len(set(mapping_by_row.values())),
        "sentinel_rows_before": sum(not _value(row.get("canonical_CompanyID") or row.get("canonical_company_id")) for row in prepared),
        "sentinel_rows_after": 0,
        "duplicate_merges": len(unique_receipts),
        "conflicting_identity_rows": conflict_count,
        "url_seed_allocations": url_seed_allocations,
        "identity_seed_allocations": identity_seed_allocations,
        "domain_only_non_merges": domain_only_non_merges,
        "preexisting_identity_keys": sorted(winner_by_key),
        "merge_receipts": list(unique_receipts.values()),
        "mapping_idempotent": True,
        "name_only_fallback": False,
    }
    return CompanyCrosswalk(mapping_by_row, mapping_by_identity, report)


def canonicalize_registry_rows(rows: Iterable[Mapping[str, Any]]) -> CompanyCrosswalk:
    source_rows = [dict(row) for row in rows if isinstance(row, Mapping)]
    crosswalk = build_company_crosswalk(source_rows)
    canonical_rows: list[dict[str, Any]] = []
    preexisting_keys = set(crosswalk.report.get("preexisting_identity_keys") or [])
    for index, row in enumerate(source_rows):
        canonical_id = crosswalk.mapping_by_row[index]
        original_id = _value(row.get("canonical_CompanyID") or row.get("canonical_company_id"))
        keys = [key for _identity_type, key in _identity_keys(row)]
        aliases = sorted({
            value
            for value in (
                _text(row.get("company_name")),
                f"website_url:{_text(row.get('website_url') or row.get('website'))}" if _value(row.get("website_url") or row.get("website")) else "",
                f"linkedin_url:{_linkedin_identity_url(row)}" if _normalize_linkedin_org_url(_linkedin_identity_url(row)) else "",
                f"linkedin_org_id:{_normal_numeric_id(row.get('linkedin_company_id') or row.get('linkedin_org_id'))}" if _normal_numeric_id(row.get('linkedin_company_id') or row.get('linkedin_org_id')) else "",
                f"companyenrich_id:{_value(row.get('companyenrich_id') or row.get('company_enrich_id'))}" if _value(row.get('companyenrich_id') or row.get('company_enrich_id')) else "",
            )
            if value
        })
        updated = dict(row)
        updated["canonical_CompanyID"] = canonical_id
        updated["canonical_company_id"] = canonical_id
        updated["canonical_identity_keys"] = "|".join(keys)
        updated["identity_aliases"] = aliases
        updated["identity_resolution_status"] = (
            "merged_to_survivor" if original_id and original_id != canonical_id
            else "retained" if original_id
            else "matched_existing" if any(key in preexisting_keys for key in keys)
            else "allocated_url_seed" if any(
                key.startswith("linkedin-org-url:") or key.startswith("website-url:")
                for key in keys
            )
            else "allocated_identity_seed"
        )
        canonical_rows.append(updated)
    crosswalk.report["canonical_rows"] = canonical_rows
    return CompanyCrosswalk(crosswalk.mapping_by_row, crosswalk.mapping_by_identity, crosswalk.report)


def resolve_company_id(row: Mapping[str, Any], crosswalk: CompanyCrosswalk | Mapping[str, str]) -> str:
    """Resolve a producer row through a crosswalk without mutating source evidence."""

    mapping = crosswalk.mapping_by_identity if isinstance(crosswalk, CompanyCrosswalk) else crosswalk
    for _identity_type, key in _identity_keys(row):
        resolved = _value(mapping.get(key))
        if resolved:
            return resolved
    original_id = _value(row.get("canonical_CompanyID") or row.get("canonical_company_id"))
    if original_id:
        resolved = _value(mapping.get(f"old-company:{original_id}"))
        if resolved:
            return resolved
        return original_id
    return canonical_company_id_for_row(row)


__all__ = [
    "CompanyCrosswalk",
    "MISSING_ID_MARKERS",
    "SCHEMA_VERSION",
    "build_company_crosswalk",
    "canonical_company_id_for_row",
    "canonicalize_registry_rows",
    "resolve_company_id",
]
