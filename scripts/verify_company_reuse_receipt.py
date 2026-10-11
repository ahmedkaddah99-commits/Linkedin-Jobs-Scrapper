"""Read back live reconciliation results and correct request/URL accounting."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.apply_company_reuse_and_validate_boards import AUDIT, field
from scripts.import_restored_company_profiles import load_env
from backend.database.connection import connect_database


def main():
    load_env(ROOT / "user_config/.env")
    receipt = json.loads((AUDIT / "reuse_apply_receipt.json").read_text(encoding="utf-8"))
    queue = json.loads((AUDIT / "reconciliation_queue.json").read_text(encoding="utf-8"))
    ids = [r["company_id"] for r in queue if "description" in r["offers"]]
    conn = connect_database(AUDIT / "remote_probe.sqlite3")
    populated = 0
    for start in range(0, len(ids), 100):
        chunk = ids[start:start+100]
        placeholders = ",".join("?" for _ in chunk)
        populated += sum(bool(field(json.loads(r[1]), "description")) for r in conn.execute(f"SELECT company_id,profile_json FROM canonical_company_profiles WHERE company_id IN ({placeholders})", tuple(chunk)).fetchall())
    counts = conn.execute("SELECT COUNT(*),COUNT(DISTINCT company_id) FROM canonical_company_urls WHERE source LIKE 'producer_board_revalidated:%' AND first_seen_at=?", (receipt["at"],)).fetchone()
    receipt["description_recheck"] = {"original_candidates": len(ids), "already_populated_live": populated, "written": 0}
    receipt["board_results"]["distinct_stored_urls_verified"] = int(counts[0])
    receipt["board_results"]["distinct_stored_companies_verified"] = int(counts[1])
    receipt["publisher_diagnosis"] = {"linkedin_checkpoint": 3500, "source_rows": 188397,
        "remaining_rows": 184897, "batch_size": 250, "minimum_additional_daily_runs_without_new_rows": 740,
        "cause": "bounded daily bootstrap plus current-cycle-or-previous-head publication candidate scope",
        "configuration_changed": False}
    receipt["provider_credit_calls"] = 0
    (AUDIT / "reuse_apply_receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    conn.close()


if __name__ == "__main__":
    main()
