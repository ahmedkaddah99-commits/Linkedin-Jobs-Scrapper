"""Build the source-preserving master jobs CSV.

This is a projection only. It concatenates LinkedIn and employer-site rows;
it intentionally does not compare or merge records between those sources.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Legacy fields remain in the output for old LinkedIn CSV compatibility only;
# the producer schema below is the authoritative LinkedIn field source.
from scripts.master_employer_jobs_catalog import EMPLOYER_FIELDS
from scripts.master_linkedin_jobs_catalog import CATALOG_FIELDS as LINKEDIN_CATALOG_FIELDS
from scripts.master_linkedin_jobs_url_catalog import CSV_FIELDS as LEGACY_LINKEDIN_FIELDS


DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "Jobs-Urls" / "master linkedin jobs url"
MASTER_FIELDS = list(dict.fromkeys([*LINKEDIN_CATALOG_FIELDS, *LEGACY_LINKEDIN_FIELDS, *EMPLOYER_FIELDS]))

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


def iter_master_rows(
    linkedin_rows: Iterable[Mapping[str, Any]],
    employer_rows: Iterable[Mapping[str, Any]],
) -> Iterable[dict[str, str]]:
    """Yield both source datasets in stable order without cross-source dedupe."""

    for row in linkedin_rows:
        yield _normalize_row(row)
    for row in employer_rows:
        yield _normalize_row(row)


def build_master_rows(
    linkedin_rows: Iterable[Mapping[str, Any]],
    employer_rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, str]]:
    """Return both source datasets in stable order without cross-source dedupe."""

    return list(iter_master_rows(linkedin_rows, employer_rows))


def iter_csv_rows(path: Path) -> Iterable[dict[str, str]]:
    """Read a CSV one row at a time, returning no rows for a missing optional source."""

    if not path.exists():
        return
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


def _source_metrics_candidates(path: Path, source_name: str) -> tuple[Path, ...]:
    default_name = {
        "LinkedIn": "master_linkedin_jobs_metrics.json",
        "employer": "master_employer_jobs_metrics.json",
    }.get(source_name, "")
    candidates = [path.with_name(f"{path.stem}_metrics.json")]
    if default_name:
        candidates.append(path.parent / default_name)
    return tuple(dict.fromkeys(candidates))


def _generation_id(
    path: Path, *, source_name: str, explicit_generation_id: str | None
) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"{source_name} source CSV not found: {path}")
    generation_id = str(explicit_generation_id or "").strip()
    if generation_id:
        return generation_id
    for metrics_path in _source_metrics_candidates(path, source_name):
        if not metrics_path.is_file():
            continue
        try:
            payload = json.loads(metrics_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"{source_name} generation metadata is invalid: {metrics_path}: {exc}") from exc
        if isinstance(payload, Mapping):
            for key in ("generation_id", "run_id"):
                value = str(payload.get(key) or "").strip()
                if value:
                    return value
        raise ValueError(f"{source_name} generation ID is missing from {metrics_path}")
    expected = "--linkedin-generation-id" if source_name == "LinkedIn" else "--employer-generation-id"
    raise ValueError(
        f"{source_name} generation ID is required; pass {expected} or provide generation metadata next to {path}"
    )


def _iter_required_csv_rows(path: Path, *, source_name: str) -> Iterable[dict[str, str]]:
    """Stream one required source while rejecting missing or malformed input."""

    if not path.is_file():
        raise FileNotFoundError(f"{source_name} source CSV not found: {path}")
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames
            if not fieldnames or any(field is None or not str(field).strip() for field in fieldnames):
                raise ValueError(f"{source_name} source CSV has no valid header: {path}")
            identity_fields = (
                ("linkedin_job_id", "source_job_id")
                if source_name == "LinkedIn"
                else ("source_job_id", "job_title")
            )
            if not any(field in fieldnames for field in identity_fields):
                expected = ", ".join(identity_fields)
                raise ValueError(f"{source_name} source CSV is missing an identity field ({expected}): {path}")
            for row_number, row in enumerate(reader, start=2):
                if None in row or any(value is None for value in row.values()):
                    raise ValueError(f"{source_name} source CSV has a malformed row {row_number}: {path}")
                yield row
    except UnicodeError as exc:
        raise ValueError(f"{source_name} source CSV is not valid UTF-8: {path}") from exc
    except csv.Error as exc:
        raise ValueError(f"{source_name} source CSV is malformed: {path}: {exc}") from exc


def _temporary_path(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
    )
    temporary = Path(handle.name)
    handle.close()
    return temporary


def _validate_master_csv(path: Path, expected_rows: int) -> None:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != MASTER_FIELDS:
            raise ValueError(f"combined CSV header mismatch in {path}")
        row_count = 0
        for row in reader:
            if None in row:
                raise ValueError(f"combined CSV contains malformed row {row_count + 1}")
            row_count += 1
    if row_count != expected_rows:
        raise ValueError(f"combined CSV row count mismatch: expected {expected_rows}, got {row_count}")


def _write_master_jobs_csv_temp(rows: Iterable[Mapping[str, Any]], temporary: Path) -> int:
    temporary.parent.mkdir(parents=True, exist_ok=True)
    row_count = 0
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MASTER_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(_normalize_row(row))
            row_count += 1
    _validate_master_csv(temporary, row_count)
    return row_count


def write_master_jobs_csv(rows: Iterable[Mapping[str, Any]], path: Path) -> int:
    """Stream normalized rows to a validated temporary CSV and atomically promote it."""

    temporary = _temporary_path(path)
    try:
        row_count = _write_master_jobs_csv_temp(rows, temporary)
        os.replace(temporary, path)
        return row_count
    finally:
        if temporary.exists():
            temporary.unlink()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    return list(iter_csv_rows(path))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomic(payload: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_path(path)
    try:
        temporary.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def export_combined_catalog(
    *,
    linkedin_csv: Path,
    employer_csv: Path,
    output: Path,
    linkedin_generation_id: str | None = None,
    employer_generation_id: str | None = None,
    manifest: Path | None = None,
) -> dict[str, Any]:
    """Build the combined projection from two independently generated sources."""

    linkedin_id = _generation_id(
        linkedin_csv, source_name="LinkedIn", explicit_generation_id=linkedin_generation_id
    )
    employer_id = _generation_id(
        employer_csv, source_name="employer", explicit_generation_id=employer_generation_id
    )
    linkedin_rows_seen = 0
    employer_rows_seen = 0

    def linkedin_rows() -> Iterable[Mapping[str, Any]]:
        nonlocal linkedin_rows_seen
        for row in _iter_required_csv_rows(linkedin_csv, source_name="LinkedIn"):
            linkedin_rows_seen += 1
            yield row

    def employer_rows() -> Iterable[Mapping[str, Any]]:
        nonlocal employer_rows_seen
        for row in _iter_required_csv_rows(employer_csv, source_name="employer"):
            employer_rows_seen += 1
            yield row

    row_count = write_master_jobs_csv(iter_master_rows(linkedin_rows(), employer_rows()), output)
    manifest_path = manifest or output.with_name("master_jobs_manifest.json")
    manifest_payload: dict[str, Any] = {
        "schema_version": 1,
        "output": {"path": str(output), "rows": row_count},
        "inputs": {
            "linkedin": {
                "path": str(linkedin_csv),
                "generation_id": linkedin_id,
                "sha256": _sha256_file(linkedin_csv),
                "rows": linkedin_rows_seen,
            },
            "employer": {
                "path": str(employer_csv),
                "generation_id": employer_id,
                "sha256": _sha256_file(employer_csv),
                "rows": employer_rows_seen,
            },
        },
    }
    _write_json_atomic(manifest_payload, manifest_path)
    return {
        "rows": row_count,
        "output": str(output),
        "manifest": str(manifest_path),
        "linkedin_generation_id": linkedin_id,
        "employer_generation_id": employer_id,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--linkedin-csv", type=Path)
    parser.add_argument("--employer-csv", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--linkedin-generation-id")
    parser.add_argument("--employer-generation-id")
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args(argv)
    linkedin_csv = args.linkedin_csv or args.output_dir / "master_linkedin_jobs.csv"
    employer_csv = args.employer_csv or args.output_dir / "master_employer_jobs.csv"
    output = args.output or args.output_dir / "master_jobs.csv"
    try:
        result = export_combined_catalog(
            linkedin_csv=linkedin_csv,
            employer_csv=employer_csv,
            output=output,
            linkedin_generation_id=args.linkedin_generation_id,
            employer_generation_id=args.employer_generation_id,
            manifest=args.manifest,
        )
    except (OSError, ValueError, UnicodeError, csv.Error, json.JSONDecodeError) as exc:
        print(f"combined export failed: {exc}", file=sys.stderr)
        return 2
    print(f"wrote {result['rows']} rows to {output} using LinkedIn generation {result['linkedin_generation_id']} and employer generation {result['employer_generation_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "MASTER_FIELDS",
    "build_master_rows",
    "export_combined_catalog",
    "iter_csv_rows",
    "iter_master_rows",
    "read_csv_rows",
    "write_master_jobs_csv",
]
