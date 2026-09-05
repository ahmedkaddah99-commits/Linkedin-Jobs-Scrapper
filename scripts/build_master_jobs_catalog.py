"""Build the source-preserving master jobs CSV.

This is a projection only. It concatenates LinkedIn and employer-site rows;
it intentionally does not compare or merge records between those sources.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.master_employer_jobs_catalog import EMPLOYER_FIELDS
from scripts.master_linkedin_jobs_url_catalog import CSV_FIELDS


DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "Jobs-Urls" / "master linkedin jobs url"
MASTER_FIELDS = list(dict.fromkeys([*CSV_FIELDS, *EMPLOYER_FIELDS]))

try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(10_000_000)


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _source_type(row: Mapping[str, Any]) -> str:
    source_type = _text(row.get("source_type")).strip()
    if source_type:
        return source_type
    return "linkedin" if _text(row.get("linkedin_job_id")).strip() else "employer_site"


def _normalize_row(row: Mapping[str, Any]) -> dict[str, str]:
    result = {field: "" for field in MASTER_FIELDS}
    result.update({field: _text(row.get(field)) for field in MASTER_FIELDS if row.get(field) is not None})
    source_type = _source_type(row)
    result["source_type"] = source_type
    if source_type == "linkedin":
        result["source_provider"] = result["source_provider"] or "linkedin"
        result["source_job_id"] = result["source_job_id"] or result["linkedin_job_id"]
        result["source_job_url"] = result["source_job_url"] or result["linkedin_job_url"]
        result["apply_url_raw"] = result["apply_url_raw"] or result["apply_url"]
        result["apply_url_canonical"] = result["apply_url_canonical"] or result["apply_url"]
        result["title_raw"] = result["title_raw"] or result["job_title"]
        result["description_text"] = result["description_text"] or result["description"]
        result["location_raw"] = result["location_raw"] or result["location"]
        result["extraction_endpoint"] = result["extraction_endpoint"] or result["source_endpoint"]
        result["extraction_method"] = result["extraction_method"] or "linkedin_guest_search_and_detail_html"
        result["discovery_method"] = result["discovery_method"] or "linkedin_guest_search"
        result["source_site_url"] = result["source_site_url"] or "https://www.linkedin.com/jobs"
    else:
        result["source_provider"] = result["source_provider"] or "generic_employer_site"
        result["source_job_id"] = result["source_job_id"] or result["source_job_url"]
        result["job_title"] = result["job_title"] or result["title_raw"]
        result["title_raw"] = result["title_raw"] or result["job_title"]
        result["description_text"] = result["description_text"] or result["description"]
        result["location_raw"] = result["location_raw"] or result["location"]
    return result


def build_master_rows(
    linkedin_rows: Iterable[Mapping[str, Any]],
    employer_rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, str]]:
    """Return both source datasets in stable order without cross-source dedupe."""

    return [_normalize_row(row) for row in [*linkedin_rows, *employer_rows]]


def write_master_jobs_csv(rows: Iterable[Mapping[str, Any]], path: Path) -> None:
    normalized_rows = [_normalize_row(row) for row in rows]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=MASTER_FIELDS)
            writer.writeheader()
            writer.writerows(normalized_rows)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--linkedin-csv", type=Path)
    parser.add_argument("--employer-csv", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    linkedin_csv = args.linkedin_csv or args.output_dir / "master_linkedin_jobs.csv"
    employer_csv = args.employer_csv or args.output_dir / "master_employer_jobs.csv"
    output = args.output or args.output_dir / "master_jobs.csv"
    rows = build_master_rows(read_csv_rows(linkedin_csv), read_csv_rows(employer_csv))
    write_master_jobs_csv(rows, output)
    print(f"wrote {len(rows)} rows to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["MASTER_FIELDS", "build_master_rows", "read_csv_rows", "write_master_jobs_csv"]
