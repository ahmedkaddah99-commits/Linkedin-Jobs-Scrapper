from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.tools.discover_company_careers import (
    _result_from_dict,
    write_company_site_entries,
    write_failure_report,
    write_json_results,
)


def _load_results(paths: list[Path]):
    results = []
    for path in sorted(paths, key=lambda item: item.name):
        if not path.exists():
            raise FileNotFoundError(f"Missing shard result file: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError(f"Shard result file must contain a JSON list: {path}")
        results.extend(_result_from_dict(item) for item in payload if isinstance(item, dict))
    return results


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Merge company-career discovery shard outputs.")
    parser.add_argument("--input-glob", required=True, help="Glob pattern for shard JSON files.")
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-company-sites", required=True)
    parser.add_argument("--output-failures-csv", required=True)
    return parser.parse_args(argv)


def run_from_args(args) -> int:
    paths = [Path(path) for path in sorted(Path().glob(args.input_glob))]
    if not paths:
        raise FileNotFoundError(f"No shard files matched: {args.input_glob}")

    results = _load_results(paths)
    output_json = Path(args.output_json)
    output_sites = Path(args.output_company_sites)
    output_failures = Path(args.output_failures_csv)
    write_json_results(output_json, results)
    write_company_site_entries(output_sites, results)
    write_failure_report(output_failures, results)
    print(
        "[CareerDiscoveryMerge] "
        f"merged={len(paths)} results={len(results)} "
        f"json={output_json} sites={output_sites} failures={output_failures}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    return run_from_args(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
