"""Count live companies without a recorded CompanyEnrich request."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.database.connection import connect_database
from scripts.import_restored_company_profiles import load_env
from scripts.run_companyenrich_v16_resume import AUDIT, load_candidates, prior_state


def main() -> int:
    load_env(ROOT / "user_config/.env")
    connection = connect_database(AUDIT / "remote_probe.sqlite3")
    try:
        live = {str(row[0]) for row in connection.execute("SELECT company_id FROM canonical_companies").fetchall()}
        with_id = {
            str(row[0])
            for row in connection.execute(
                "SELECT company_id FROM canonical_company_profiles WHERE trim(COALESCE(json_extract(profile_json,'$.fields.companyenrich_id.value'),json_extract(profile_json,'$.additional_fields.companyenrich_id.value'),''))<>''"
            ).fetchall()
        }
        completed, unresolved, _ = prior_state()
        requested: set[str] = set()
        for path in sorted(AUDIT.glob("provider_results_*.jsonl")) + [AUDIT / "provider_result_recovered_interruption.jsonl"]:
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                try:
                    event = json.loads(line)
                except (TypeError, ValueError):
                    continue
                company_id = event.get("company_id")
                if company_id and event.get("event") in {"attempting", "result", "failed", "ambiguous_timeout", "rate_limited"}:
                    requested.add(str(company_id))
        remaining = load_candidates(connection, completed | unresolved)
        print(json.dumps({
            "live_companies": len(live),
            "companyenrich_id_present": len(live & with_id),
            "recorded_request_companies": len(live & requested),
            "never_requested_all_live": len(live - requested),
            "never_requested_missing_provider_id": len((live - requested) - with_id),
            "eligible_unattempted_for_runner": len(remaining),
            "unresolved_attempt_ledgers": len(live & unresolved),
            "definitive_or_ambiguous_results": len(live & completed),
        }, indent=2))
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
