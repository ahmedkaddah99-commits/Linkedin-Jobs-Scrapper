"""Apply a user-supplied company website list and fetch free CompanyEnrich logos.

The input website list is matched locally against ``company_name``.  This
script only calls CompanyEnrich's public free logo endpoint for the domains
that are matched from that list; it does not use a paid enrichment endpoint or
an API key.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import os
import re
import sqlite3
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

from populate_free_companyenrich_logos import (
    DEFAULT_CSV,
    DEFAULT_DB,
    OUTPUT_COLUMN,
    CSV_ENCODING,
    fetch_all_free_logos,
    normalize_domain,
    normalize_linkedin_url,
    write_csv_in_place,
)


KNOWN_WEBSITES = Path(os.environ["RUNR_KNOWN_WEBSITES_CSV"]) if os.environ.get("RUNR_KNOWN_WEBSITES_CSV") else None
STATUS_COLUMN = "website_discovery_status"


def clean(value: Any) -> str:
    return str(value or "").strip()


def normalize_company_name(value: Any) -> str:
    """Normalize names across accents, mojibake, and trailing list markers."""
    text = clean(value).rstrip(" \\/")
    for _ in range(2):
        if not any(marker in text for marker in ("Ã", "Â", "â", "ð")):
            break
        try:
            repaired = text.encode("latin1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
        if repaired == text:
            break
        text = repaired
    text = text.replace("\ufffd", " ")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(character for character in text if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def _identity_rank(row: dict[str, str]) -> tuple[int, int, int]:
    canonical_id = clean(row.get("canonical_CompanyID"))
    linkedin_id = clean(row.get("linkedin_company_id"))
    linkedin_url = clean(row.get("linkedin_company_url"))
    return (
        int(bool(canonical_id and canonical_id != "//")),
        int(linkedin_id.isdigit()),
        int(bool(linkedin_url)),
    )


def _name_score(known_name: str, master_name: str) -> float:
    if not known_name or not master_name:
        return 0.0
    if known_name == master_name:
        return 1.0
    known_tokens = set(known_name.split())
    master_tokens = set(master_name.split())
    if known_tokens and known_tokens.issubset(master_tokens):
        return 0.96
    return difflib.SequenceMatcher(None, known_name.replace(" ", ""), master_name.replace(" ", "")).ratio()


def match_known_rows(
    known_rows: list[dict[str, str]], master_rows: list[dict[str, str]]
) -> dict[str, Any]:
    """Match known website rows to master rows without guessing weak matches."""
    normalized_master = [normalize_company_name(row.get("company_name")) for row in master_rows]
    by_name: dict[str, list[int]] = {}
    for index, name in enumerate(normalized_master):
        if name:
            by_name.setdefault(name, []).append(index)

    matches: dict[int, int] = {}
    unmatched: list[int] = []
    ambiguous: dict[int, list[int]] = {}
    for known_index, known_row in enumerate(known_rows):
        known_name = normalize_company_name(known_row.get("company_name_as_listed"))
        exact_candidates = by_name.get(known_name, [])
        if len(exact_candidates) == 1:
            matches[known_index] = exact_candidates[0]
            continue
        if len(exact_candidates) > 1:
            ranked = sorted(exact_candidates, key=lambda index: _identity_rank(master_rows[index]), reverse=True)
            if len(ranked) == 1 or _identity_rank(master_rows[ranked[0]]) != _identity_rank(master_rows[ranked[1]]):
                matches[known_index] = ranked[0]
            else:
                ambiguous[known_index] = exact_candidates
            continue

        scored = sorted(
            (
                _name_score(known_name, master_name),
                _identity_rank(master_rows[index]),
                index,
            )
            for index, master_name in enumerate(normalized_master)
            if master_name
        )
        scored.reverse()
        if not scored or scored[0][0] < 0.88:
            unmatched.append(known_index)
            continue
        if len(scored) > 1 and scored[0][0] - scored[1][0] < 0.05:
            ambiguous[known_index] = [entry[2] for entry in scored if entry[0] == scored[0][0]]
            continue
        matches[known_index] = scored[0][2]

    return {"matches": matches, "unmatched": unmatched, "ambiguous": ambiguous}


def load_known_websites(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding=CSV_ENCODING, newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {"company_name_as_listed", "official_website"}
    missing = required - set(rows[0]) if rows else required
    if missing:
        raise ValueError(f"Known website CSV is missing columns: {sorted(missing)}")
    return rows


def update_database_logos(
    db_path: Path,
    matched_rows: list[dict[str, str]],
    logos_by_domain: dict[str, str],
) -> int:
    """Update only matched LinkedIn rows in the existing state database."""
    with sqlite3.connect(db_path, timeout=60) as connection:
        connection.execute("PRAGMA busy_timeout=60000")
        columns = {row[1] for row in connection.execute("PRAGMA table_info(url_resolution)")}
        if OUTPUT_COLUMN not in columns:
            connection.execute(f"ALTER TABLE url_resolution ADD COLUMN {OUTPUT_COLUMN} TEXT NOT NULL DEFAULT ''")

        updates: dict[str, str] = {}
        for row in matched_rows:
            linkedin_url = normalize_linkedin_url(row.get("linkedin_company_url"))
            domain = normalize_domain(row.get("website_url"))
            logo = logos_by_domain.get(domain, "")
            if linkedin_url and logo:
                updates[linkedin_url] = logo

        db_urls = {
            normalize_linkedin_url(raw_url): raw_url
            for raw_url, in connection.execute("SELECT normalized_url FROM url_resolution")
            if normalize_linkedin_url(raw_url)
        }
        persisted = 0
        for normalized_url, logo in updates.items():
            raw_url = db_urls.get(normalized_url)
            if raw_url is None:
                continue
            connection.execute(
                f"UPDATE url_resolution SET {OUTPUT_COLUMN}=? WHERE normalized_url=?",
                (logo, raw_url),
            )
            persisted += 1
        return persisted


def apply_known_websites(
    known_path: Path,
    csv_path: Path,
    db_path: Path,
    *,
    workers: int,
    timeout: float,
    write: bool,
) -> dict[str, Any]:
    known_rows = load_known_websites(known_path)
    with csv_path.open("r", encoding=CSV_ENCODING, newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        master_rows = list(reader)
    if "website_url" not in fieldnames or OUTPUT_COLUMN not in fieldnames:
        raise ValueError("Master CSV must contain website_url and companyenrich_free_logo_url")

    matching = match_known_rows(known_rows, master_rows)
    matches: dict[int, int] = matching["matches"]
    conflicts: list[dict[str, str]] = []
    matched_rows: list[dict[str, str]] = []
    matched_master_indices: set[int] = set()
    for known_index, master_index in matches.items():
        known_row = known_rows[known_index]
        master_row = master_rows[master_index]
        supplied_url = clean(known_row.get("official_website"))
        supplied_domain = normalize_domain(supplied_url)
        if not supplied_domain:
            conflicts.append({"company": clean(known_row.get("company_name_as_listed")), "reason": "invalid website"})
            continue
        existing_url = clean(master_row.get("website_url"))
        if existing_url and normalize_domain(existing_url) != supplied_domain:
            conflicts.append({
                "company": clean(known_row.get("company_name_as_listed")),
                "reason": f"existing domain {normalize_domain(existing_url)} differs from {supplied_domain}",
            })
            continue
        if not existing_url:
            master_row["website_url"] = supplied_url
        master_row[STATUS_COLUMN] = "found"
        matched_rows.append(master_row)
        matched_master_indices.add(master_index)

    domains = sorted({normalize_domain(row.get("website_url")) for row in matched_rows} - {""})
    logos_by_domain: dict[str, str] = {}
    if write and domains:
        logos_by_domain = __import__("asyncio").run(
            fetch_all_free_logos(domains, workers=max(1, workers), timeout_seconds=max(1.0, timeout))
        )
        for row in matched_rows:
            logo = logos_by_domain.get(normalize_domain(row.get("website_url")), "")
            if logo:
                row[OUTPUT_COLUMN] = logo

    database_rows_updated = 0
    if write:
        if STATUS_COLUMN not in fieldnames:
            fieldnames.append(STATUS_COLUMN)
        write_csv_in_place(csv_path, fieldnames, master_rows)
        database_rows_updated = update_database_logos(db_path, matched_rows, logos_by_domain)

    return {
        "known_rows": len(known_rows),
        "matched_known_rows": len(matches),
        "matched_master_rows": len(matched_master_indices),
        "unmatched": [clean(known_rows[index].get("company_name_as_listed")) for index in matching["unmatched"]],
        "ambiguous": {
            clean(known_rows[index].get("company_name_as_listed")): candidates
            for index, candidates in matching["ambiguous"].items()
        },
        "conflicts": conflicts,
        "unique_domains": len(domains),
        "logo_urls_found": sum(bool(value) for value in logos_by_domain.values()),
        "database_rows_updated": database_rows_updated,
        "paid_api_key_used": False,
        "paid_company_enrichment_endpoint_used": False,
        "write": write,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--known-csv",
        type=Path,
        default=KNOWN_WEBSITES,
        required=KNOWN_WEBSITES is None,
        help="Explicit reviewed website mapping CSV; may also be supplied through RUNR_KNOWN_WEBSITES_CSV",
    )
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--workers", type=int, default=40)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--write", action="store_true", help="apply websites and fetch free logos")
    args = parser.parse_args()

    summary = apply_known_websites(
        args.known_csv.resolve(),
        args.csv.resolve(),
        args.db.resolve(),
        workers=args.workers,
        timeout=args.timeout,
        write=args.write,
    )
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
