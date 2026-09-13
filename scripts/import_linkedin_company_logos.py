"""Import LinkedIn-collected company logos into the canonical logo projection.

This is intentionally a bounded, repeatable maintenance command.  It reads the
company catalog (not job rows), resolves each LinkedIn logo to a canonical
company, downloads only the requested scope, validates the bytes, caches them in
Runr's configured object storage, and writes the existing
``canonical_company_profiles`` logo columns.  It never writes Turso or Render.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable, Mapping
import unicodedata
from urllib.parse import unquote, urlsplit

import requests

from backend.application.company_logo import (
    LogoValidationError,
    assert_public_official_host,
    cache_logo,
    validate_logo,
    validate_official_url,
)
from backend.storage import create_object_storage


LINKEDIN_LOGO_HOST_SUFFIXES = (".licdn.com", ".linkedin.com")
PROFILE_FIELDS = (
    "description",
    "website",
    "careers_page",
    "industry",
    "company_size",
    "headquarters",
    "founded_year",
    "company_stage",
    "funding_stage",
    "total_funding",
    "funding_year",
    "leadership_type",
    "benefits",
    "sponsorship",
    "logo",
)
MAX_LOGO_BYTES = 2 * 1024 * 1024
MISSING_VALUES = {"", "//", "none", "null", "n/a", "unknown"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalise_name(value: Any) -> str:
    decomposed = unicodedata.normalize("NFKD", _text(value)).casefold()
    ascii_text = decomposed.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", ascii_text)


def normalise_linkedin_slug(value: Any) -> str:
    """Return the company slug from a LinkedIn company URL."""

    raw = _text(value)
    if not raw:
        return ""
    parsed = urlsplit(raw if "://" in raw else f"https://{raw}")
    host = _text(parsed.hostname).casefold()
    if host not in {"linkedin.com", "www.linkedin.com"}:
        return ""
    parts = [unquote(item).strip() for item in parsed.path.split("/") if item.strip()]
    if len(parts) < 2 or parts[0].casefold() != "company":
        return ""
    return parts[1].casefold()


def _is_linkedin_logo_url(value: Any) -> bool:
    try:
        host = _text(urlsplit(_text(value)).hostname).casefold().rstrip(".")
    except ValueError:
        return False
    return any(host == suffix.removeprefix(".") or host.endswith(suffix) for suffix in LINKEDIN_LOGO_HOST_SUFFIXES)


def _linkedin_logo_url(row: Mapping[str, Any]) -> str:
    """Select only the LinkedIn-collected logo field, never CompanyEnrich."""

    direct = _text(row.get("logo_linkedin_source_url"))
    if direct and _is_linkedin_logo_url(direct):
        return direct
    direct = _text(row.get("linkedin_logo_url"))
    if direct and _is_linkedin_logo_url(direct):
        return direct
    source = _text(row.get("logo_source")).casefold()
    candidate = _text(row.get("logo_url"))
    if source in {"linkedin", "linkedin_company_master", "linkedin_company_page"} and _is_linkedin_logo_url(candidate):
        return candidate
    return ""


def load_linkedin_logo_candidates(path: str | Path) -> list[dict[str, str]]:
    """Load and deduplicate LinkedIn logo candidates from either company CSV."""

    candidates: dict[str, dict[str, str]] = {}
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            logo_url = _linkedin_logo_url(row)
            if not logo_url:
                continue
            candidate = {
                "canonical_company_id": _text(row.get("canonical_CompanyID") or row.get("canonical_company_id")),
                "company_id": _text(row.get("company_id")),
                "company_name": _text(row.get("company_name") or row.get("canonical_name") or row.get("company")),
                "linkedin_company_url": _text(row.get("linkedin_company_url") or row.get("Company-LinkedIn-url")),
                "linkedin_slug": _text(row.get("linkedin_slug")) or normalise_linkedin_slug(row.get("linkedin_company_url") or row.get("Company-LinkedIn-url")),
                "logo_url": logo_url,
                "logo_source": "LinkedIn",
                "source_row": _text(row.get("source_row_numbers") or row.get("No")),
            }
            key = candidate["linkedin_slug"] or candidate["canonical_company_id"] or _normalise_name(candidate["company_name"])
            if not key:
                continue
            old = candidates.get(key)
            if old is None or (candidate["canonical_company_id"] not in MISSING_VALUES and old["canonical_company_id"] in MISSING_VALUES):
                candidates[key] = candidate
    return list(candidates.values())


@dataclass(frozen=True)
class CompanyIndexes:
    by_id: Mapping[str, Mapping[str, Any]]
    by_slug: Mapping[str, tuple[Mapping[str, Any], ...]]
    by_name: Mapping[str, tuple[Mapping[str, Any], ...]]

    def resolve(self, candidate: Mapping[str, Any]) -> tuple[str, str]:
        direct_id = _text(candidate.get("canonical_company_id"))
        if direct_id not in MISSING_VALUES and direct_id in self.by_id:
            return direct_id, "canonical_id"
        slug = _text(candidate.get("linkedin_slug")) or normalise_linkedin_slug(candidate.get("linkedin_company_url"))
        slug_matches = self.by_slug.get(slug, ()) if slug else ()
        if len(slug_matches) == 1:
            return _text(slug_matches[0].get("company_id")), "linkedin_url"
        name = _normalise_name(candidate.get("company_name"))
        name_matches = self.by_name.get(name, ()) if name else ()
        if len(name_matches) == 1:
            return _text(name_matches[0].get("company_id")), "unique_name"
        return "", "unresolved"


def build_company_indexes(rows: Iterable[Mapping[str, Any]]) -> CompanyIndexes:
    by_id: dict[str, Mapping[str, Any]] = {}
    slugs: dict[str, list[Mapping[str, Any]]] = {}
    names: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        company_id = _text(row.get("company_id"))
        if not company_id:
            continue
        by_id[company_id] = row
        slug = normalise_linkedin_slug(row.get("provenance_url"))
        if slug:
            slugs.setdefault(slug, []).append(row)
        name = _normalise_name(row.get("canonical_name"))
        if name:
            names.setdefault(name, []).append(row)
    return CompanyIndexes(
        by_id=by_id,
        by_slug={key: tuple(value) for key, value in slugs.items()},
        by_name={key: tuple(value) for key, value in names.items()},
    )


def merge_logo_into_profile(
    profile: Mapping[str, Any] | None,
    *,
    logo_url: str,
    linkedin_company_url: str,
    verified_at: str,
) -> dict[str, Any]:
    """Merge the LinkedIn logo into the existing phase-F profile shape."""

    merged = dict(profile or {})
    fields = merged.get("fields")
    fields = dict(fields) if isinstance(fields, Mapping) else {}
    fields["logo"] = {
        "value": logo_url,
        "state": "known",
        "provenance": {
            "source": "linkedin_company_master",
            "url": linkedin_company_url or logo_url,
        },
        "verified_at": verified_at,
    }
    merged["schema_version"] = _text(merged.get("schema_version")) or "phase_f_v3"
    merged["fields"] = fields
    return merged


def _profile_status(profile: Mapping[str, Any]) -> str:
    fields = profile.get("fields") if isinstance(profile, Mapping) else {}
    fields = fields if isinstance(fields, Mapping) else {}
    known = sum(
        1
        for name in PROFILE_FIELDS
        if isinstance(fields.get(name), Mapping)
        and _text(fields[name].get("state")) == "known"
        and fields[name].get("value") not in (None, "", [])
    )
    if known == 0:
        return "absent"
    if known == len(PROFILE_FIELDS):
        return "present"
    return "incomplete"


def _proxy_url() -> str:
    explicit = _text(os.getenv("WEBSHARE_PROXY_URL") or os.getenv("WEBSHARE_PROXY"))
    if explicit:
        return explicit
    username = _text(os.getenv("WEBSHARE_PROXY_USERNAME"))
    password = _text(os.getenv("WEBSHARE_PROXY_PASSWORD"))
    host = _text(os.getenv("WEBSHARE_PROXY_HOST")) or "p.webshare.io"
    port = _text(os.getenv("WEBSHARE_PROXY_PORT")) or "80"
    if username and password:
        from urllib.parse import quote

        return f"http://{quote(username, safe='')}:{quote(password, safe='')}@{host}:{port}"
    return ""


def _fetch_logo(url: str, *, timeout_seconds: int, proxy_url: str) -> tuple[bytes, str, str]:
    safe_url = validate_official_url(url)
    host = _text(urlsplit(safe_url).hostname)
    if not _is_linkedin_logo_url(safe_url):
        raise LogoValidationError("linkedin_logo_host_not_allowed")
    assert_public_official_host(host)
    response = requests.get(
        safe_url,
        headers={"User-Agent": "Runr-linkedin-logo-import/1.0", "Accept": "image/*"},
        timeout=max(5, int(timeout_seconds)),
        allow_redirects=True,
        stream=True,
        proxies={"http": proxy_url, "https": proxy_url} if proxy_url else None,
    )
    try:
        if int(response.status_code or 0) != 200:
            raise RuntimeError(f"http_status_{response.status_code}")
        body = bytearray()
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if chunk:
                body.extend(chunk)
                if len(body) > MAX_LOGO_BYTES:
                    raise LogoValidationError("logo_size_invalid")
        content_type = _text(response.headers.get("content-type")).split(";", 1)[0].casefold()
        validated = validate_logo(bytes(body), content_type)
        final_url = _text(response.url) or safe_url
        return validated.data, validated.content_type, final_url
    finally:
        response.close()


def _load_active_company_ids(connection: Any) -> set[str]:
    rows = connection.execute(
        """
        SELECT DISTINCT j.company_id
        FROM acquisition_publication_head h
        JOIN acquisition_publication_jobs pj ON pj.publication_id=h.publication_id
        JOIN canonical_jobs j ON j.canonical_job_id=pj.canonical_job_id
        """
    ).fetchall()
    return {_text(row[0]) for row in rows if _text(row[0])}


def _write_profile(
    connection: Any,
    *,
    company_id: str,
    logo_url: str,
    linkedin_company_url: str,
    verified_at: str,
    object_key: str = "",
    content_hash: str = "",
    content_type: str = "",
    status: str = "cached",
) -> None:
    existing = connection.execute(
        "SELECT profile_json,logo_object_key,logo_source_url,logo_content_hash,logo_content_type,logo_verified_at,created_at,profile_status FROM canonical_company_profiles WHERE company_id=?",
        (company_id,),
    ).fetchone()
    current: dict[str, Any] = {}
    if existing is not None:
        try:
            decoded = json.loads(_text(existing[0]))
            if isinstance(decoded, Mapping):
                current = dict(decoded)
        except (TypeError, ValueError):
            current = {}
    merged = merge_logo_into_profile(
        current,
        logo_url=logo_url,
        linkedin_company_url=linkedin_company_url,
        verified_at=verified_at,
    )
    now = _now_iso()
    old_object = _text(existing[1]) if existing is not None else ""
    old_source = _text(existing[2]) if existing is not None else ""
    old_hash = _text(existing[3]) if existing is not None else ""
    old_type = _text(existing[4]) if existing is not None else ""
    old_verified = _text(existing[5]) if existing is not None else ""
    created = _text(existing[6]) if existing is not None else now
    connection.execute(
        """
        INSERT INTO canonical_company_profiles(
            company_id,profile_json,profile_status,logo_object_key,logo_source_url,
            logo_content_hash,logo_content_type,logo_verified_at,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(company_id) DO UPDATE SET
            profile_json=excluded.profile_json,
            profile_status=excluded.profile_status,
            logo_object_key=excluded.logo_object_key,
            logo_source_url=excluded.logo_source_url,
            logo_content_hash=excluded.logo_content_hash,
            logo_content_type=excluded.logo_content_type,
            logo_verified_at=excluded.logo_verified_at,
            updated_at=excluded.updated_at
        """,
        (
            company_id,
            json.dumps(merged, ensure_ascii=False, separators=(",", ":")),
            _profile_status(merged),
            object_key or old_object,
            logo_url or old_source,
            content_hash or old_hash,
            content_type or old_type,
            verified_at or old_verified,
            created,
            now,
        ),
    )
    enrichment_id = "linkedin_logo_" + hashlib.sha256(f"{company_id}:{logo_url}".encode("utf-8")).hexdigest()[:32]
    connection.execute(
        """
        INSERT INTO company_logo_enrichments(
            logo_enrichment_id,company_id,provider,source_url,object_key,content_hash,
            content_type,status,terms_metadata_json,provenance_json,observed_at,rule_version,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(logo_enrichment_id) DO UPDATE SET
            object_key=excluded.object_key,content_hash=excluded.content_hash,
            content_type=excluded.content_type,status=excluded.status,
            provenance_json=excluded.provenance_json,observed_at=excluded.observed_at,
            updated_at=excluded.updated_at
        """,
        (
            enrichment_id,
            company_id,
            "linkedin_company_master",
            logo_url,
            object_key,
            content_hash,
            content_type,
            status,
            "{}",
            json.dumps({"linkedin_company_url": linkedin_company_url, "source": "linkedin_company_master"}, separators=(",", ":")),
            verified_at,
            "company_logo_v1",
            created,
            now,
        ),
    )


def run_import(
    *,
    source: str | Path,
    database: str | Path,
    scope: str = "active",
    dry_run: bool = False,
    max_downloads: int = 1000,
    timeout_seconds: int = 15,
    force_refresh: bool = False,
) -> dict[str, Any]:
    candidates = load_linkedin_logo_candidates(source)
    connection = __import__("sqlite3").connect(str(database), timeout=60)
    connection.row_factory = __import__("sqlite3").Row
    connection.execute("PRAGMA busy_timeout=60000")
    try:
        companies = connection.execute("SELECT company_id,canonical_name,provenance_url FROM canonical_companies").fetchall()
        indexes = build_company_indexes(companies)
        active_ids = _load_active_company_ids(connection)
        mapped: list[tuple[dict[str, str], str, str]] = []
        unresolved = 0
        for candidate in candidates:
            company_id, method = indexes.resolve(candidate)
            if not company_id:
                unresolved += 1
                continue
            mapped.append((candidate, company_id, method))
        existing = {
            _text(row["company_id"]): row
            for row in connection.execute(
                "SELECT company_id,logo_object_key,logo_source_url FROM canonical_company_profiles"
            ).fetchall()
        }
        scoped = mapped if scope == "all" else [item for item in mapped if item[1] in active_ids]
        download_targets = []
        for candidate, company_id, method in scoped:
            profile = existing.get(company_id)
            has_object = bool(profile and _text(profile["logo_object_key"]))
            source_is_linkedin = bool(profile and _is_linkedin_logo_url(profile["logo_source_url"]))
            if force_refresh or not has_object or not source_is_linkedin:
                download_targets.append((candidate, company_id, method))
        result: dict[str, Any] = {
            "source": str(source),
            "scope": scope,
            "candidate_rows": len(candidates),
            "matched_rows": len(mapped),
            "unresolved_rows": unresolved,
            "database_companies": len(companies),
            "active_companies": len(active_ids),
            "scoped_matches": len(scoped),
            "download_targets": len(download_targets),
            "download_limit": max(0, int(max_downloads)),
            "dry_run": dry_run,
            "cached": 0,
            "source_only": 0,
            "failed": 0,
            "failures": [],
        }
        if dry_run:
            return result

        storage = create_object_storage(dict(os.environ))
        proxy_url = _proxy_url()
        downloaded: dict[str, tuple[dict[str, str], str, str, str, str, str]] = {}
        for candidate, company_id, method in download_targets[: max(0, int(max_downloads))]:
            try:
                body, content_type, final_url = _fetch_logo(
                    candidate["logo_url"],
                    timeout_seconds=timeout_seconds,
                    proxy_url=proxy_url,
                )
                validated = validate_logo(body, content_type)
                object_key, _written = cache_logo(storage, company_id, validated)
                downloaded[company_id] = (candidate, method, object_key, validated.content_hash, validated.content_type, final_url)
                result["cached"] += 1
            except Exception as exc:  # one bad CDN object must not abort the bounded import
                result["failed"] += 1
                if len(result["failures"]) < 25:
                    result["failures"].append({"company_id": company_id, "source_row": candidate["source_row"], "error": type(exc).__name__})

        now = _now_iso()
        connection.execute("BEGIN IMMEDIATE")
        try:
            for candidate, company_id, method in scoped:
                cached = downloaded.get(company_id)
                profile = existing.get(company_id)
                has_object = bool(profile and _text(profile["logo_object_key"]))
                if cached is not None:
                    _candidate, _method, object_key, content_hash, content_type, final_url = cached
                    _write_profile(
                        connection,
                        company_id=company_id,
                        logo_url=final_url or candidate["logo_url"],
                        linkedin_company_url=candidate["linkedin_company_url"],
                        verified_at=now,
                        object_key=object_key,
                        content_hash=content_hash,
                        content_type=content_type,
                        status="cached",
                    )
                elif not has_object:
                    _write_profile(
                        connection,
                        company_id=company_id,
                        logo_url=candidate["logo_url"],
                        linkedin_company_url=candidate["linkedin_company_url"],
                        verified_at=now,
                        status="source_only",
                    )
                    result["source_only"] += 1
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        result["transport"] = "webshare" if proxy_url else "direct"
        result["updated_profiles"] = result["cached"] + result["source_only"]
        return result
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Company CSV containing LinkedIn-collected logo fields")
    parser.add_argument("--database", required=True, help="Runr backend SQLite database")
    parser.add_argument("--scope", choices=("active", "all"), default="active")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-downloads", type=int, default=1000)
    parser.add_argument("--timeout-seconds", type=int, default=15)
    parser.add_argument("--force-refresh", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run_import(**vars(args)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
