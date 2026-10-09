from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.application.company_enrichment import ScrapeOpsLinkedInCompanyProvider
from backend.bootstrap import create_backend
from backend.database.connection import database_session


PREFIX = "manual-linkedin-full-sweep-20260815-bg"
BATCH_SIZE = 25


def _production_counts(db_path: Path) -> tuple[int, int, int]:
    with database_session(db_path) as connection:
        employer_count = int(
            connection.execute(
                "SELECT COUNT(*) n FROM canonical_companies WHERE COALESCE(entity_kind, 'unknown')='employer'"
            ).fetchone()["n"]
            or 0
        )
        attempted_count = int(
            connection.execute(
                "SELECT COUNT(DISTINCT company_id) n FROM company_enrichment_attempts WHERE cycle_key LIKE ?",
                (f"{PREFIX}-%",),
            ).fetchone()["n"]
            or 0
        )
        max_cycle = 0
        for row in connection.execute(
            "SELECT cycle_key FROM company_enrichment_attempts WHERE cycle_key LIKE ? GROUP BY cycle_key",
            (f"{PREFIX}-%",),
        ).fetchall():
            match = re.search(r"-(\d+)$", str(row["cycle_key"] or ""))
            if match:
                max_cycle = max(max_cycle, int(match.group(1)))
    return employer_count, attempted_count, max_cycle


def main() -> None:
    db_path = Path("data/runr-linkedin-sweep.db")
    application = create_backend(db_path, storage_backend="sqlite")
    provider = ScrapeOpsLinkedInCompanyProvider(
        api_key=os.getenv("SCRAPEOPS_API_KEY", ""),
        mode="basic",
        timeout_seconds=12,
        max_retries=0,
        prefer_direct=True,
    )
    employer_count, attempted_count, cycle_index = _production_counts(db_path)
    print(
        json.dumps(
            {"event": "linkedin_sweep_started", "employer_count": employer_count, "attempted_count": attempted_count},
            sort_keys=True,
        ),
        flush=True,
    )
    while attempted_count < employer_count:
        cycle_index += 1
        cycle_key = f"{PREFIX}-{cycle_index:03d}"
        result = application.run_due_company_enrichment(
            provider=provider,
            max_companies=BATCH_SIZE,
            concurrency=8,
            request_budget=100,
            cycle_key=cycle_key,
            force=True,
            force_all=True,
        )
        employer_count, attempted_count, _ = _production_counts(db_path)
        print(
            json.dumps(
                {
                    "event": "linkedin_sweep_batch",
                    "cycle_key": cycle_key,
                    "result": result,
                    "attempted_count": attempted_count,
                    "employer_count": employer_count,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            flush=True,
        )
        if not int(result.get("companies_processed") or 0):
            time.sleep(30)
    print(
        json.dumps(
            {"event": "linkedin_sweep_complete", "employer_count": employer_count, "attempted_count": attempted_count},
            sort_keys=True,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
