from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Iterable

from backend.config.job_seeker import load_project_dotenv
from backend.connectors.company_career_discovery import (
    CareerDiscoveryResult,
    CareerUrlCandidate,
    discover_career_url,
    domain_from_url,
    utc_now_iso,
)
from backend.repositories.mysql_career_discovery import (
    MySqlCareerDiscoveryConfig,
    MySqlCareerDiscoveryStore,
)

REGULAR_JOBS_SOURCE = Path("Jobs-Urls") / "Master-Jobs-Url" / "Master-Jobs-Url.csv"
PHD_JOBS_SOURCE = Path("Jobs-Urls") / "List-of-All-European-Universities" / "ETER-DB-Euro-Uni-Export.csv"
DISCOVERY_SOURCE_PRESETS = ("regular", "phd")

COMPANY_NAME_COLUMNS = (
    "company",
    "company_name",
    "Company name",
    "name",
    "BAS.INSTNAME",
    "institution",
    "institution_name",
)
HOMEPAGE_URL_COLUMNS = (
    "website",
    "url",
    "homepage_url",
    "home_page_url",
    "domain",
    "company_domain",
    "BAS.WEBSITE",
)


def _compact(value) -> str:
    return " ".join(str(value or "").strip().split())


def _first_value(row: dict, columns: Iterable[str]) -> str:
    lower_lookup = {str(key).lower(): key for key in row}
    for column in columns:
        if column in row and _compact(row.get(column)):
            return _compact(row.get(column))
        matched_key = lower_lookup.get(column.lower())
        if matched_key and _compact(row.get(matched_key)):
            return _compact(row.get(matched_key))
    return ""


def _target_from_row(
    row: dict,
    *,
    company_name_column: str = "",
    homepage_url_column: str = "",
) -> dict[str, str]:
    company_name = _compact(row.get(company_name_column)) if company_name_column else ""
    homepage_url = _compact(row.get(homepage_url_column)) if homepage_url_column else ""

    if not company_name:
        company_name = _first_value(row, COMPANY_NAME_COLUMNS)
    if not homepage_url:
        homepage_url = _first_value(row, HOMEPAGE_URL_COLUMNS)

    return {
        "company_name": company_name,
        "homepage_url": homepage_url,
    }


def load_targets_from_csv(
    path: Path,
    *,
    company_name_column: str = "",
    homepage_url_column: str = "",
) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        targets = [
            _target_from_row(
                row,
                company_name_column=company_name_column,
                homepage_url_column=homepage_url_column,
            )
            for row in reader
        ]
    return [target for target in targets if target["company_name"] or target["homepage_url"]]


def load_targets_from_json(
    path: Path,
    *,
    company_name_column: str = "",
    homepage_url_column: str = "",
) -> list[dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        for key in ("companies", "items", "rows", "results"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
    if not isinstance(payload, list):
        raise ValueError("JSON input must be a list, or an object containing companies/items/rows/results.")

    targets = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        targets.append(
            _target_from_row(
                item,
                company_name_column=company_name_column,
                homepage_url_column=homepage_url_column,
            )
        )
    return [target for target in targets if target["company_name"] or target["homepage_url"]]


def load_targets(
    path: Path,
    *,
    input_format: str,
    company_name_column: str = "",
    homepage_url_column: str = "",
) -> list[dict[str, str]]:
    resolved_format = input_format
    if resolved_format == "auto":
        suffix = path.suffix.lower()
        if suffix == ".csv":
            resolved_format = "csv"
        elif suffix == ".json":
            resolved_format = "json"
        else:
            raise ValueError(f"Cannot auto-detect input format for {path}")

    if resolved_format == "csv":
        return load_targets_from_csv(
            path,
            company_name_column=company_name_column,
            homepage_url_column=homepage_url_column,
        )
    if resolved_format == "json":
        return load_targets_from_json(
            path,
            company_name_column=company_name_column,
            homepage_url_column=homepage_url_column,
        )
    raise ValueError(f"Unsupported input format: {input_format}")


def write_json_results(path: Path, results: list[CareerDiscoveryResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([result.to_dict() for result in results], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def write_company_site_entries(path: Path, results: list[CareerDiscoveryResult]) -> int:
    entries = [
        result.to_company_site_entry()
        for result in results
        if result.primary_career_url and result.crawl_status in {"found", "low_confidence"}
    ]
    entries = [entry for entry in entries if entry]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(entries) + ("\n" if entries else ""), encoding="utf-8")
    return len(entries)


def default_failure_output_path(source: str) -> str:
    normalized = str(source or "").strip().lower()
    output_dir = Path(".backend_data") / "career_discovery"
    if normalized == "regular":
        return str(output_dir / "regular_failures.csv")
    if normalized == "phd":
        return str(output_dir / "phd_failures.csv")
    if normalized == "all":
        return str(output_dir / "all_failures.csv")
    return str(output_dir / "company_career_discovery_failures.csv")


def write_failure_report(path: Path, results: list[CareerDiscoveryResult]) -> int:
    failures = [
        result
        for result in results
        if not result.primary_career_url and result.crawl_status not in {"found", "low_confidence"}
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "company_name",
                "homepage_url",
                "company_domain",
                "crawl_status",
                "confidence_score",
                "primary_career_url",
                "validation_evidence",
            ],
        )
        writer.writeheader()
        for result in failures:
            writer.writerow(
                {
                    "company_name": result.company_name,
                    "homepage_url": result.homepage_url,
                    "company_domain": result.company_domain,
                    "crawl_status": result.crawl_status,
                    "confidence_score": result.confidence_score,
                    "primary_career_url": result.primary_career_url,
                    "validation_evidence": " | ".join(result.validation_evidence or []),
                }
            )
    return len(failures)


def default_output_paths(source: str) -> tuple[str, str]:
    normalized = str(source or "").strip().lower()
    output_dir = Path(".backend_data") / "career_discovery"
    if normalized == "regular":
        return (
            str(output_dir / "regular_results.json"),
            str(Path("user_config") / "discovered_regular_company_career_sites.txt"),
        )
    if normalized == "phd":
        return (
            str(output_dir / "phd_results.json"),
            str(Path("user_config") / "discovered_phd_university_career_sites.txt"),
        )
    if normalized == "all":
        return (
            str(output_dir / "all_results.json"),
            str(Path("user_config") / "discovered_company_career_sites.txt"),
        )
    return (
        str(output_dir / "company_career_discovery_results.json"),
        str(Path("user_config") / "discovered_company_career_sites.txt"),
    )


def _slice_targets(targets: list[dict[str, str]], *, offset: int, limit: int) -> list[dict[str, str]]:
    start = max(0, int(offset))
    sliced = targets[start:]
    if int(limit) > 0:
        return sliced[: int(limit)]
    return sliced


def discover_targets(args, *, source_override: str = "") -> list[CareerDiscoveryResult]:
    if args.homepage_url or args.domain or args.company_name:
        targets = [
            {
                "company_name": args.company_name,
                "homepage_url": args.homepage_url or args.domain,
            }
        ]
    else:
        input_path = args.input or source_path_for_preset(source_override or args.source)
        if not input_path:
            raise ValueError("Provide --input, --source, or use --homepage-url/--domain for a single company.")
        targets = load_targets(
            Path(input_path),
            input_format=args.input_format,
            company_name_column=args.company_name_column,
            homepage_url_column=args.homepage_url_column,
        )

    targets = _slice_targets(targets, offset=args.offset, limit=args.limit)
    results: list[CareerDiscoveryResult] = []
    total = len(targets)

    for index, target in enumerate(targets, start=1):
        company_name = target.get("company_name", "")
        homepage_url = target.get("homepage_url", "")
        print(f"[CareerDiscovery] {index}/{total} {company_name or homepage_url}")
        result = discover_career_url(
            homepage_url=homepage_url,
            company_name=company_name,
            request_timeout_seconds=args.timeout_seconds,
            shallow_crawl_pages=args.shallow_crawl_pages,
            use_rendered_fallback=args.use_rendered_fallback,
            allow_domain_guessing=args.allow_domain_guessing,
        )
        results.append(result)
        print(
            "[CareerDiscovery] "
            f"status={result.crawl_status} "
            f"score={result.confidence_score:.2f} "
            f"url={result.primary_career_url or '-'}"
        )

    return results


def source_path_for_preset(source: str) -> str:
    normalized = str(source or "").strip().lower()
    if normalized in {"", "custom"}:
        return ""
    if normalized in {"regular", "regular_jobs", "jobs"}:
        return str(REGULAR_JOBS_SOURCE)
    if normalized in {"phd", "universities", "university"}:
        return str(PHD_JOBS_SOURCE)
    if normalized == "all":
        raise ValueError("The 'all' preset spans multiple inputs. Use run_discovery() or the CLI command instead.")
    raise ValueError(f"Unsupported source preset: {source}")


def source_presets_for_run(source: str) -> list[str]:
    normalized = str(source or "").strip().lower()
    if normalized == "all":
        return list(DISCOVERY_SOURCE_PRESETS)
    if normalized in {"regular", "regular_jobs", "jobs"}:
        return ["regular"]
    if normalized in {"phd", "universities", "university"}:
        return ["phd"]
    return []


def _targets_for_source(args, source: str) -> list[dict[str, str]]:
    if args.homepage_url or args.domain or args.company_name:
        return [
            {
                "company_name": args.company_name,
                "homepage_url": args.homepage_url or args.domain,
            }
        ]

    input_path = args.input or source_path_for_preset(source)
    if not input_path:
        raise ValueError("Provide --input, --source, or use --homepage-url/--domain for a single company.")
    targets = load_targets(
        Path(input_path),
        input_format=args.input_format,
        company_name_column=args.company_name_column,
        homepage_url_column=args.homepage_url_column,
    )
    return _slice_targets(targets, offset=args.offset, limit=args.limit)


def _result_from_dict(payload: dict) -> CareerDiscoveryResult:
    candidates = []
    for item in payload.get("candidates") or []:
        if not isinstance(item, dict):
            continue
        candidates.append(
            CareerUrlCandidate(
                url=str(item.get("url") or ""),
                source=str(item.get("source") or ""),
                label=str(item.get("label") or ""),
                ats_type=str(item.get("ats_type") or ""),
                status_code=int(item.get("status_code") or 0),
                confidence_score=float(item.get("confidence_score") or 0.0),
                evidence=[str(value) for value in item.get("evidence") or [] if str(value).strip()],
            )
        )
    return CareerDiscoveryResult(
        company_domain=str(payload.get("company_domain") or ""),
        homepage_url=str(payload.get("homepage_url") or ""),
        company_name=str(payload.get("company_name") or ""),
        primary_career_url=str(payload.get("primary_career_url") or ""),
        secondary_candidate_urls=[
            str(value) for value in payload.get("secondary_candidate_urls") or [] if str(value).strip()
        ],
        ats_type=str(payload.get("ats_type") or ""),
        confidence_score=float(payload.get("confidence_score") or 0.0),
        discovered_at=str(payload.get("discovered_at") or ""),
        crawl_status=str(payload.get("crawl_status") or "not_found"),
        candidates=candidates,
        validation_evidence=[str(value) for value in payload.get("validation_evidence") or [] if str(value).strip()],
    )


def _synthetic_failure_result(target: dict[str, str], *, status: str, evidence: list[str]) -> CareerDiscoveryResult:
    homepage_url = str(target.get("homepage_url") or "")
    return CareerDiscoveryResult(
        company_domain=domain_from_url(homepage_url),
        homepage_url=homepage_url,
        company_name=str(target.get("company_name") or ""),
        primary_career_url="",
        secondary_candidate_urls=[],
        ats_type="",
        confidence_score=0.0,
        discovered_at=utc_now_iso(),
        crawl_status=status,
        candidates=[],
        validation_evidence=[str(item) for item in evidence if str(item).strip()],
    )


def _temporary_output_paths(source: str, label: str) -> tuple[Path, Path]:
    temp_dir = Path(".backend_data") / "career_discovery" / "tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return (
        temp_dir / f"{source}_{label}_results.json",
        temp_dir / f"{source}_{label}_sites.txt",
    )


def _child_command_for_chunk(
    *,
    source: str,
    offset: int,
    limit: int,
    args,
    output_json: Path,
    output_company_sites: Path,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "backend.tools.discover_company_careers",
        "--source",
        source,
        "--offset",
        str(offset),
        "--limit",
        str(limit),
        "--timeout-seconds",
        str(args.timeout_seconds),
        "--shallow-crawl-pages",
        str(args.shallow_crawl_pages),
        "--output-json",
        str(output_json),
        "--output-company-sites",
        str(output_company_sites),
    ]
    if args.allow_domain_guessing:
        command.append("--allow-domain-guessing")
    if args.use_rendered_fallback:
        command.append("--use-rendered-fallback")
    return command


def _child_command_for_target(
    *,
    target: dict[str, str],
    source: str,
    args,
    output_json: Path,
    output_company_sites: Path,
    use_rendered_fallback: bool,
    timeout_seconds: int,
    shallow_crawl_pages: int,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "backend.tools.discover_company_careers",
        "--source",
        source,
        "--company-name",
        str(target.get("company_name") or ""),
        "--homepage-url",
        str(target.get("homepage_url") or ""),
        "--limit",
        "1",
        "--timeout-seconds",
        str(timeout_seconds),
        "--shallow-crawl-pages",
        str(shallow_crawl_pages),
        "--output-json",
        str(output_json),
        "--output-company-sites",
        str(output_company_sites),
    ]
    if args.allow_domain_guessing:
        command.append("--allow-domain-guessing")
    if use_rendered_fallback:
        command.append("--use-rendered-fallback")
    return command


def _run_child_discovery(command: list[str], *, timeout_seconds: int) -> tuple[int, str, str, bool]:
    try:
        completed = subprocess.run(
            command,
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            timeout=max(1, int(timeout_seconds)),
        )
    except subprocess.TimeoutExpired as exc:
        stdout = str(exc.stdout or "")
        stderr = str(exc.stderr or "")
        return 124, stdout, stderr, True
    return completed.returncode, completed.stdout, completed.stderr, False


def _load_results_from_path(path: Path) -> list[CareerDiscoveryResult]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return []
    return [_result_from_dict(item) for item in payload if isinstance(item, dict)]


def _run_target_with_retries(
    *,
    source: str,
    target: dict[str, str],
    args,
    label: str,
) -> CareerDiscoveryResult:
    attempts = [
        {
            "use_rendered_fallback": bool(args.use_rendered_fallback),
            "timeout_seconds": max(5, int(args.timeout_seconds)),
            "shallow_crawl_pages": max(1, int(args.shallow_crawl_pages)),
            "status_on_timeout": "target_timeout",
        }
    ]
    if not args.use_rendered_fallback:
        attempts.append(
            {
                "use_rendered_fallback": True,
                "timeout_seconds": max(10, int(args.timeout_seconds) + 10),
                "shallow_crawl_pages": max(2, int(args.shallow_crawl_pages) + 2),
                "status_on_timeout": "rendered_retry_timeout",
            }
        )

    for attempt_index, attempt in enumerate(attempts, start=1):
        output_json, output_company_sites = _temporary_output_paths(source, f"{label}_attempt_{attempt_index}")
        command = _child_command_for_target(
            target=target,
            source=source,
            args=args,
            output_json=output_json,
            output_company_sites=output_company_sites,
            use_rendered_fallback=attempt["use_rendered_fallback"],
            timeout_seconds=attempt["timeout_seconds"],
            shallow_crawl_pages=attempt["shallow_crawl_pages"],
        )
        return_code, stdout, stderr, did_timeout = _run_child_discovery(
            command,
            timeout_seconds=attempt["timeout_seconds"] + 60,
        )
        results = _load_results_from_path(output_json)
        if return_code == 0 and results:
            result = results[0]
            if result.primary_career_url or attempt_index == len(attempts):
                return result
        if did_timeout and attempt_index == len(attempts):
            return _synthetic_failure_result(
                target,
                status=attempt["status_on_timeout"],
                evidence=[
                    f"Subprocess timed out after {attempt['timeout_seconds'] + 60} seconds.",
                    stdout.strip(),
                    stderr.strip(),
                ],
            )
        if return_code != 0 and attempt_index == len(attempts):
            return _synthetic_failure_result(
                target,
                status="target_subprocess_failed",
                evidence=[
                    f"Child process exited with code {return_code}.",
                    stdout.strip(),
                    stderr.strip(),
                ],
            )

    return _synthetic_failure_result(target, status="target_retry_exhausted", evidence=["Unknown retry failure."])


def _run_chunk_with_fallback(
    *,
    source: str,
    targets: list[dict[str, str]],
    base_offset: int,
    args,
    chunk_number: int,
) -> list[CareerDiscoveryResult]:
    chunk_size = len(targets)
    output_json, output_company_sites = _temporary_output_paths(source, f"chunk_{chunk_number}_{base_offset}")
    command = _child_command_for_chunk(
        source=source,
        offset=base_offset,
        limit=chunk_size,
        args=args,
        output_json=output_json,
        output_company_sites=output_company_sites,
    )
    hard_timeout_seconds = int(getattr(args, "hard_timeout_seconds", 0) or 0)
    timeout_seconds = hard_timeout_seconds or max(300, int(args.timeout_seconds) * max(1, chunk_size) * 4)
    return_code, stdout, stderr, did_timeout = _run_child_discovery(command, timeout_seconds=timeout_seconds)
    results = _load_results_from_path(output_json)
    if return_code == 0 and len(results) == chunk_size:
        return results

    print(
        "[CareerDiscovery:robust] "
        f"chunk offset={base_offset} size={chunk_size} did not finish cleanly; "
        "falling back to per-target discovery."
    )
    if stdout.strip():
        print(stdout.strip())
    if stderr.strip():
        print(stderr.strip())

    fallback_results: list[CareerDiscoveryResult] = []
    for index, target in enumerate(targets, start=1):
        label = f"target_{base_offset + index - 1}"
        if not did_timeout and index <= len(results):
            fallback_results.append(results[index - 1])
            continue
        fallback_results.append(
            _run_target_with_retries(
                source=source,
                target=target,
                args=args,
                label=label,
            )
        )
    return fallback_results


def _run_robust_discovery_for_source(args, *, source: str) -> tuple[dict, list[CareerDiscoveryResult]]:
    targets = _targets_for_source(args, source)
    total = len(targets)
    batch_size = max(1, int(getattr(args, "robust_batch_size", 1) or 1))
    start_offset = max(0, int(getattr(args, "offset", 0) or 0))
    aggregate_results: list[CareerDiscoveryResult] = []
    output_json_value = str(getattr(args, "output_json", "") or "")
    output_company_sites_value = str(getattr(args, "output_company_sites", "") or "")
    output_failures_value = str(getattr(args, "output_failures_csv", "") or "")

    print(
        "[CareerDiscovery:robust] "
        f"source={source} total_targets={total} batch_size={batch_size} start_offset={start_offset}"
    )

    for chunk_index, relative_offset in enumerate(range(0, total, batch_size), start=1):
        chunk_targets = targets[relative_offset : relative_offset + batch_size]
        actual_offset = start_offset + relative_offset
        print(
            "[CareerDiscovery:robust] "
            f"source={source} chunk={chunk_index} offset={actual_offset} size={len(chunk_targets)}"
        )
        chunk_results = _run_chunk_with_fallback(
            source=source,
            targets=chunk_targets,
            base_offset=actual_offset,
            args=args,
            chunk_number=chunk_index,
        )
        aggregate_results.extend(chunk_results)
        _persist_discovery_results(
            source=source,
            results=aggregate_results,
            output_json_value=output_json_value,
            output_company_sites_value=output_company_sites_value,
            failure_report_value=output_failures_value,
        )

    return _persist_discovery_results(
        source=source,
        results=aggregate_results,
        output_json_value=output_json_value,
        output_company_sites_value=output_company_sites_value,
        failure_report_value=output_failures_value,
        save_mysql=bool(getattr(args, "save_mysql", False)),
        mysql_config=_mysql_config_from_args(args) if getattr(args, "save_mysql", False) else None,
    ), aggregate_results


def add_discover_company_careers_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        "--source",
        default="custom",
        choices=["custom", "regular", "phd", "all"],
        help=(
            "Named input preset. regular uses Jobs-Urls/Master-Jobs-Url/Master-Jobs-Url.csv; "
            "phd uses Jobs-Urls/List-of-All-European-Universities/ETER-DB-Euro-Uni-Export.csv; "
            "all runs both presets and writes both per-source outputs plus a combined list."
        ),
    )
    parser.add_argument("--input", default="", help="CSV or JSON file containing companies and homepage URLs.")
    parser.add_argument("--input-format", default="auto", choices=["auto", "csv", "json"])
    parser.add_argument("--company-name-column", default="", help="Override company-name column.")
    parser.add_argument("--homepage-url-column", default="", help="Override homepage/domain column.")
    parser.add_argument("--homepage-url", default="", help="Discover a single company homepage URL.")
    parser.add_argument("--domain", default="", help="Discover a single company domain.")
    parser.add_argument("--company-name", default="", help="Optional company name.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum targets to process. 0 means all.")
    parser.add_argument("--offset", type=int, default=0, help="Skip this many targets before processing.")
    parser.add_argument("--timeout-seconds", type=int, default=20)
    parser.add_argument("--shallow-crawl-pages", type=int, default=8)
    parser.add_argument("--use-rendered-fallback", action="store_true")
    parser.add_argument("--allow-domain-guessing", action="store_true")
    parser.add_argument("--output-json", default="")
    parser.add_argument("--output-company-sites", default="")
    parser.add_argument("--output-failures-csv", default="")
    parser.add_argument(
        "--robust-batch-size",
        type=int,
        default=0,
        help="Run discovery in subprocess batches with checkpointing and per-target fallback.",
    )
    parser.add_argument(
        "--hard-timeout-seconds",
        type=int,
        default=0,
        help="Hard timeout for each subprocess batch when using --robust-batch-size.",
    )
    parser.add_argument("--save-mysql", action="store_true")
    parser.add_argument("--mysql-host", default="")
    parser.add_argument("--mysql-port", type=int, default=0)
    parser.add_argument("--mysql-user", default="")
    parser.add_argument("--mysql-password", default="")
    parser.add_argument("--mysql-database", default="")
    parser.add_argument("--mysql-table", default="")
    return parser


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Discover and store company career URLs.")
    add_discover_company_careers_arguments(parser)
    return parser.parse_args(argv)


def _mysql_config_from_args(args) -> MySqlCareerDiscoveryConfig:
    env_config = MySqlCareerDiscoveryConfig.from_env()
    return MySqlCareerDiscoveryConfig(
        host=args.mysql_host or env_config.host,
        port=args.mysql_port or env_config.port,
        user=args.mysql_user or env_config.user,
        password=args.mysql_password or env_config.password,
        database=args.mysql_database or env_config.database,
        table=args.mysql_table or env_config.table,
    )


def _persist_discovery_results(
    *,
    source: str,
    results: list[CareerDiscoveryResult],
    output_json_value: str = "",
    output_company_sites_value: str = "",
    failure_report_value: str = "",
    save_mysql: bool = False,
    mysql_config: MySqlCareerDiscoveryConfig | None = None,
) -> dict:
    default_output_json, default_output_company_sites = default_output_paths(source)
    default_failure_output = default_failure_output_path(source)
    output_json = Path(output_json_value or default_output_json)
    output_company_sites = Path(output_company_sites_value or default_output_company_sites)
    write_json_results(output_json, results)
    company_site_count = write_company_site_entries(output_company_sites, results)
    failure_report_path = Path(failure_report_value or default_failure_output)
    failure_count = write_failure_report(failure_report_path, results)

    mysql_count = 0
    if save_mysql:
        store = MySqlCareerDiscoveryStore(mysql_config or MySqlCareerDiscoveryConfig.from_env())
        store.initialize()
        mysql_count = store.upsert_results(results)

    found_count = sum(1 for result in results if result.primary_career_url)
    return {
        "source": source,
        "processed": len(results),
        "found": found_count,
        "not_found": len(results) - found_count,
        "output_json": str(output_json),
        "output_company_sites": str(output_company_sites),
        "company_site_entries": company_site_count,
        "failure_report_path": str(failure_report_path),
        "failure_count": failure_count,
        "mysql_rows_saved": mysql_count,
        "results": [result.to_dict() for result in results],
    }


def run_discovery(args) -> dict:
    load_project_dotenv()
    normalized_source = str(getattr(args, "source", "custom") or "custom").strip().lower()

    if int(getattr(args, "robust_batch_size", 0) or 0) > 0:
        if normalized_source == "all":
            if any(
                str(value or "").strip()
                for value in (
                    getattr(args, "input", ""),
                    getattr(args, "homepage_url", ""),
                    getattr(args, "domain", ""),
                    getattr(args, "company_name", ""),
                )
            ):
                raise ValueError("The 'all' preset can only be used with the built-in regular and phd source files.")
            combined_results: list[CareerDiscoveryResult] = []
            source_summaries: list[dict] = []
            for source in DISCOVERY_SOURCE_PRESETS:
                source_summary, source_results = _run_robust_discovery_for_source(args, source=source)
                combined_results.extend(source_results)
                source_summaries.append({key: value for key, value in source_summary.items() if key != "results"})
            combined_summary = _persist_discovery_results(
                source="all",
                results=combined_results,
                output_json_value=str(getattr(args, "output_json", "") or ""),
                output_company_sites_value=str(getattr(args, "output_company_sites", "") or ""),
                failure_report_value=str(getattr(args, "output_failures_csv", "") or ""),
                save_mysql=bool(getattr(args, "save_mysql", False)),
                mysql_config=_mysql_config_from_args(args) if getattr(args, "save_mysql", False) else None,
            )
            combined_summary["source_summaries"] = source_summaries
            return combined_summary
        robust_summary, _ = _run_robust_discovery_for_source(args, source=normalized_source)
        return robust_summary

    if normalized_source == "all":
        if any(
            str(value or "").strip()
            for value in (
                getattr(args, "input", ""),
                getattr(args, "homepage_url", ""),
                getattr(args, "domain", ""),
                getattr(args, "company_name", ""),
            )
        ):
            raise ValueError("The 'all' preset can only be used with the built-in regular and phd source files.")
        mysql_config = _mysql_config_from_args(args) if getattr(args, "save_mysql", False) else None
        combined_results: list[CareerDiscoveryResult] = []
        source_summaries: list[dict] = []

        for source in DISCOVERY_SOURCE_PRESETS:
            results = discover_targets(args, source_override=source)
            combined_results.extend(results)
            source_summary = _persist_discovery_results(
                source=source,
                results=results,
                save_mysql=False,
            )
            source_summaries.append(
                {
                    key: value
                    for key, value in source_summary.items()
                    if key != "results"
                }
            )

        combined_summary = _persist_discovery_results(
            source="all",
            results=combined_results,
            output_json_value=str(getattr(args, "output_json", "") or ""),
            output_company_sites_value=str(getattr(args, "output_company_sites", "") or ""),
            failure_report_value=str(getattr(args, "output_failures_csv", "") or ""),
            save_mysql=bool(getattr(args, "save_mysql", False)),
            mysql_config=mysql_config,
        )
        combined_summary["source_summaries"] = source_summaries
        return combined_summary

    results = discover_targets(args)
    return _persist_discovery_results(
        source=normalized_source,
        results=results,
        output_json_value=str(getattr(args, "output_json", "") or ""),
        output_company_sites_value=str(getattr(args, "output_company_sites", "") or ""),
        failure_report_value=str(getattr(args, "output_failures_csv", "") or ""),
        save_mysql=bool(getattr(args, "save_mysql", False)),
        mysql_config=_mysql_config_from_args(args) if getattr(args, "save_mysql", False) else None,
    )


def run_from_args(args) -> int:
    payload = run_discovery(args)
    print(f"[CareerDiscovery] wrote results: {payload['output_json']}")
    print(
        "[CareerDiscovery] wrote company-site entries: "
        f"{payload['output_company_sites']} ({payload['company_site_entries']})"
    )
    print(
        "[CareerDiscovery] wrote failure report: "
        f"{payload['failure_report_path']} ({payload['failure_count']})"
    )
    for source_summary in payload.get("source_summaries", []):
        print(
            "[CareerDiscovery] "
            f"{source_summary['source']}: processed={source_summary['processed']} "
            f"found={source_summary['found']} "
            f"failures={source_summary['failure_count']} "
            f"output={source_summary['output_company_sites']}"
        )
    if getattr(args, "save_mysql", False):
        print(f"[CareerDiscovery] saved MySQL rows: {payload['mysql_rows_saved']}")
    print(f"[CareerDiscovery] done. processed={payload['processed']} found={payload['found']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    return run_from_args(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
