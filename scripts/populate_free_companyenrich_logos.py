"""Populate CompanyEnrich's free, domain-based logo URL in place.

This script deliberately calls only the public free logo endpoint:
``GET https://api.companyenrich.com/logo/{domain}``.
It never sends an API key and never calls a paid enrichment endpoint.

The CSV and the LinkedIn URL-resolution SQLite database are updated in place.
The free endpoint returns HTTP 200 for its no-match placeholder, so responses
whose image dimensions are 128x128 are treated as no-match and written blank.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sqlite3
import struct
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlsplit

import httpx
import requests


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "Company-Urls" / "Master-Company-Url" / "cleaned" / "Master-Company-Url-canonical_cleaned_linkedin_ids.csv"
DEFAULT_DB = ROOT / "Company-Urls" / "Master-Company-Url" / "cleaned" / "linkedin_company_enrichment_state" / "linkedin_id_resolution" / "linkedin_id_resolution.sqlite3"
OUTPUT_COLUMN = "companyenrich_free_logo_url"
FREE_LOGO_ENDPOINT = "https://api.companyenrich.com/logo/"
CSV_ENCODING = "utf-8-sig"
REQUEST_TIMEOUT_SECONDS = 5
DEFAULT_WORKERS = 80


def clean(value: Any) -> str:
    return str(value or "").strip()


def normalize_domain(value: Any) -> str:
    raw = clean(value)
    if not raw:
        return ""
    parsed = urlsplit(raw if "://" in raw else f"https://{raw}")
    host = clean(parsed.hostname).casefold().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    if "." not in host or any(ch.isspace() for ch in host):
        return ""
    return host


def normalize_linkedin_url(value: Any) -> str:
    raw = clean(value)
    if not raw:
        return ""
    parsed = urlsplit(raw if "://" in raw else f"https://{raw}")
    host = clean(parsed.hostname).casefold()
    parts = [part for part in parsed.path.split("/") if part]
    if not (host == "linkedin.com" or host.endswith(".linkedin.com")):
        return ""
    if len(parts) < 2 or parts[0].casefold() != "company":
        return ""
    slug = quote(unquote(parts[1].strip()).casefold(), safe="-._~")
    return f"https://www.linkedin.com/company/{slug}/"


def image_dimensions(content: bytes, content_type: str) -> tuple[int, int] | None:
    if content.startswith(b"\x89PNG\r\n\x1a\n") and len(content) >= 24:
        return struct.unpack(">II", content[16:24])
    if content.startswith(b"\xff\xd8"):
        index = 2
        while index + 9 < len(content):
            if content[index] != 0xFF:
                index += 1
                continue
            marker = content[index + 1]
            index += 2
            if marker in {0xD8, 0xD9}:
                continue
            if index + 2 > len(content):
                break
            segment_length = struct.unpack(">H", content[index:index + 2])[0]
            if segment_length < 2 or index + segment_length > len(content):
                break
            if marker in set(range(0xC0, 0xC4)) | set(range(0xC5, 0xC8)) | set(range(0xC9, 0xCC)) | set(range(0xCD, 0xD0)):
                if segment_length >= 7:
                    height, width = struct.unpack(">HH", content[index + 3:index + 7])
                    return width, height
            index += segment_length
    return None


def fetch_free_logo(domain: str, timeout_seconds: float = REQUEST_TIMEOUT_SECONDS) -> tuple[str, str]:
    """Return (domain, usable_logo_url), with no paid/API-key request path."""
    if not domain:
        return domain, ""
    try:
        response = requests.get(
            f"{FREE_LOGO_ENDPOINT}{domain}",
            timeout=timeout_seconds,
            allow_redirects=True,
        )
        content_type = clean(response.headers.get("content-type")).casefold()
        dimensions = image_dimensions(response.content, content_type)
        if response.status_code == 200 and content_type.startswith("image/") and dimensions and dimensions != (128, 128):
            return domain, f"{FREE_LOGO_ENDPOINT}{domain}"
    except requests.RequestException:
        pass
    return domain, ""


async def fetch_all_free_logos(
    domains: list[str], *, workers: int, timeout_seconds: float
) -> dict[str, str]:
    """Fetch one free endpoint response per domain with bounded async concurrency."""
    timeout = httpx.Timeout(
        connect=max(1.0, timeout_seconds),
        read=max(1.0, timeout_seconds),
        write=max(1.0, timeout_seconds),
        pool=max(1.0, timeout_seconds),
    )
    limits = httpx.Limits(
        max_connections=max(1, workers),
        max_keepalive_connections=min(max(1, workers), 20),
    )
    semaphore = asyncio.Semaphore(max(1, workers))
    results: dict[str, str] = {}
    completed = 0

    async with httpx.AsyncClient(timeout=timeout, limits=limits, follow_redirects=True) as client:
        async def fetch(domain: str) -> None:
            nonlocal completed
            async with semaphore:
                try:
                    response = await client.get(f"{FREE_LOGO_ENDPOINT}{domain}")
                    content_type = clean(response.headers.get("content-type")).casefold()
                    dimensions = image_dimensions(response.content, content_type)
                    if response.status_code == 200 and content_type.startswith("image/") and dimensions and dimensions != (128, 128):
                        results[domain] = f"{FREE_LOGO_ENDPOINT}{domain}"
                except httpx.HTTPError:
                    pass
                completed += 1
                if completed % 250 == 0 or completed == len(domains):
                    print({"free_logo_requests_completed": completed, "total": len(domains)}, flush=True)

        await asyncio.gather(*(fetch(domain) for domain in domains))
    return results


def load_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding=CSV_ENCODING, newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        if not fieldnames:
            raise ValueError("CSV has no header")
        return fieldnames, list(reader)


def write_csv_in_place(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    fd, temporary_name = tempfile.mkstemp(prefix=f"{path.stem}.", suffix=".tmp", dir=path.parent)
    os.close(fd)
    temporary_path = Path(temporary_name)
    try:
        with temporary_path.open("w", encoding=CSV_ENCODING, newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\r\n")
            writer.writeheader()
            writer.writerows(rows)
        try:
            os.replace(temporary_path, path)
        except PermissionError:
            # Windows can deny replacing a file held by an editor while still
            # allowing a normal write to the same path.
            with path.open("w", encoding=CSV_ENCODING, newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\r\n")
                writer.writeheader()
                writer.writerows(rows)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def update_database(path: Path, rows: list[dict[str, str]], logos_by_domain: dict[str, str]) -> int:
    with sqlite3.connect(path, timeout=60) as connection:
        connection.execute("PRAGMA busy_timeout=60000")
        columns = {row[1] for row in connection.execute("PRAGMA table_info(url_resolution)")}
        if OUTPUT_COLUMN not in columns:
            connection.execute(f"ALTER TABLE url_resolution ADD COLUMN {OUTPUT_COLUMN} TEXT NOT NULL DEFAULT ''")

        db_url_by_key: dict[str, str] = {}
        for raw_url, in connection.execute("SELECT normalized_url FROM url_resolution"):
            key = normalize_linkedin_url(raw_url)
            if not key:
                continue
            if key in db_url_by_key and db_url_by_key[key] != raw_url:
                raise RuntimeError(f"Duplicate database URLs after normalization: {key}")
            db_url_by_key[key] = raw_url
        csv_url_to_domain: dict[str, str] = {}
        for row in rows:
            linkedin_url = normalize_linkedin_url(row.get("linkedin_company_url"))
            if linkedin_url:
                csv_url_to_domain[linkedin_url] = normalize_domain(row.get("domain") or row.get("website_url"))
        missing = sorted(set(csv_url_to_domain) - set(db_url_by_key))
        if missing:
            raise RuntimeError(f"CSV/database URL mismatch; {len(missing)} CSV URLs are absent from the state database")

        updates = [
            (logos_by_domain.get(domain, "") if domain else "", db_url_by_key[linkedin_url])
            for linkedin_url, domain in csv_url_to_domain.items()
        ]
        connection.executemany(
            f"UPDATE url_resolution SET {OUTPUT_COLUMN}=? WHERE normalized_url=?",
            updates,
        )
        return len(updates)


def load_database_logos(path: Path) -> dict[str, str]:
    """Load the already-written DB values without making another API call."""
    with sqlite3.connect(path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(url_resolution)")}
        if OUTPUT_COLUMN not in columns:
            raise RuntimeError(f"Database does not contain {OUTPUT_COLUMN}")
        return {
            key: clean(logo)
            for raw_url, logo in connection.execute(
                f"SELECT normalized_url, {OUTPUT_COLUMN} FROM url_resolution"
            )
            for key in [normalize_linkedin_url(raw_url)]
            if key
        }


def write_csv_via_open_excel(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    """Write only the new column through the user's already-open Excel workbook."""
    try:
        import win32com.client
    except ImportError as exc:
        raise RuntimeError("pywin32 is required for --write-open-excel") from exc

    target_path = str(path.resolve()).casefold()
    try:
        excel = win32com.client.GetActiveObject("Excel.Application")
    except Exception as exc:
        raise RuntimeError("No active Excel instance was found") from exc

    workbook = None
    for candidate in excel.Workbooks:
        if str(candidate.FullName).casefold() == target_path:
            workbook = candidate
            break
    if workbook is None:
        raise RuntimeError(f"The target CSV is not open in the active Excel instance: {path}")

    worksheet = workbook.Worksheets(1)
    output_column_number = fieldnames.index(OUTPUT_COLUMN) + 1
    worksheet.Cells(1, output_column_number).Value = OUTPUT_COLUMN
    values = tuple((row[OUTPUT_COLUMN],) for row in rows)
    worksheet.Range(
        worksheet.Cells(2, output_column_number),
        worksheet.Cells(len(rows) + 1, output_column_number),
    ).Value = values

    previous_alerts = excel.DisplayAlerts
    try:
        excel.DisplayAlerts = False
        workbook.Save()
    finally:
        excel.DisplayAlerts = previous_alerts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--timeout", type=float, default=REQUEST_TIMEOUT_SECONDS)
    parser.add_argument(
        "--reuse-db-results",
        action="store_true",
        help="Populate the CSV from the existing DB column without making API requests.",
    )
    parser.add_argument(
        "--write-open-excel",
        action="store_true",
        help="Write the final column through the already-open Excel workbook.",
    )
    parser.add_argument(
        "--overwrite-existing",
        action="store_true",
        help="Refresh an existing result column instead of refusing to overwrite it.",
    )
    args = parser.parse_args()

    csv_path = args.csv.resolve()
    db_path = args.db.resolve()
    fieldnames, rows = load_csv(csv_path)
    if OUTPUT_COLUMN in fieldnames and not args.overwrite_existing:
        raise RuntimeError(f"{OUTPUT_COLUMN} already exists; refusing to overwrite an existing result column")
    if not db_path.exists():
        raise FileNotFoundError(db_path)

    domains = {
        normalize_domain(row.get("domain") or row.get("website_url"))
        for row in rows
    }
    domains.discard("")
    logo_by_linkedin_url: dict[str, str] | None = None
    if args.reuse_db_results:
        logo_by_linkedin_url = load_database_logos(db_path)
    else:
        logos_by_domain = asyncio.run(
            fetch_all_free_logos(
                sorted(domains),
                workers=max(1, args.workers),
                timeout_seconds=max(1.0, args.timeout),
            )
        )

    for row in rows:
        if logo_by_linkedin_url is not None:
            row[OUTPUT_COLUMN] = logo_by_linkedin_url.get(
                normalize_linkedin_url(row.get("linkedin_company_url")),
                "",
            )
        else:
            row[OUTPUT_COLUMN] = logos_by_domain.get(
                normalize_domain(row.get("domain") or row.get("website_url")),
                "",
            )

    if OUTPUT_COLUMN not in fieldnames:
        fieldnames.append(OUTPUT_COLUMN)
    updated_db_rows = 0 if args.reuse_db_results else update_database(db_path, rows, logos_by_domain)
    if args.write_open_excel:
        if not args.reuse_db_results:
            raise RuntimeError("--write-open-excel requires --reuse-db-results")
        write_csv_via_open_excel(csv_path, fieldnames, rows)
    else:
        write_csv_in_place(csv_path, fieldnames, rows)

    print({
        "csv": str(csv_path),
        "db": str(db_path),
        "rows": len(rows),
        "columns": len(fieldnames),
        "unique_domains_requested": len(domains),
        "logo_urls_written": sum(bool(row[OUTPUT_COLUMN]) for row in rows),
        "blank_logo_results": sum(not bool(row[OUTPUT_COLUMN]) for row in rows),
        "database_rows_updated": updated_db_rows,
        "endpoint": FREE_LOGO_ENDPOINT,
        "paid_api_key_used": False,
        "paid_company_enrichment_endpoint_used": False,
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
