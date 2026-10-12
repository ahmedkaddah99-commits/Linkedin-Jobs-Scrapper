"""Persist a per-source-row catch-up ledger without changing the live catalog.

Publication membership is deliberately separate from customer discoverability.
Unresolved identities remain pending; they never become success by timeout.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_producer_catchup import utc_now, write_json
from scripts.publish_producer_states import (
    SOURCE_LINKEDIN, SOURCE_EMPLOYER, _manifest_companies, _source_group_from_rows,
    _row_payload, _target, adapt_linkedin_job, adapt_employer_job, load_manifest,
)


def inventory(operation, ledger):
    state = json.loads((operation / "snapshot.json").read_text(encoding="utf-8"))
    manifest = load_manifest(Path(state["manifest"]))
    mapping = (json.loads(Path(state["crosswalk"]).read_text(encoding="utf-8"))
               .get("mapping_by_identity", {}) if state["crosswalk"] else {})
    for source, name, table in ((SOURCE_LINKEDIN, "linkedin", "job_company_observations"),
                                 (SOURCE_EMPLOYER, "employer", "jobs")):
        companies = _manifest_companies(manifest, source, pilot_only=False, crosswalk=mapping)
        orgs = {org: cid for cid, company in companies.items() for org in company.get("linkedin_company_ids", ())}
        with sqlite3.connect((operation / (name + ".db")).as_uri() + "?mode=ro", uri=True) as con:
            con.row_factory = sqlite3.Row
            batch = []
            for row in con.execute(f"SELECT rowid,* FROM {table}"):
                payload = _row_payload(row)
                groups, _ = _source_group_from_rows([row], source=source,
                    canonical_by_source_company=orgs, selected_ids=set(companies), crosswalk=mapping)
                target, external, status, reason = "", "", "pending", "not_yet_reconciled"
                if not groups:
                    if payload.get("lifecycle_status") == "inactive":
                        status, reason = "excluded", "source_inactive"
                    else:
                        status, reason = "not_eligible_or_unresolved", "manifest_or_identity_requires_review"
                else:
                    cid, jobs = next(iter(groups.items()))
                    adapter = adapt_linkedin_job if source == SOURCE_LINKEDIN else adapt_employer_job
                    observation = adapter(jobs[0], cycle_id="catchup-inventory")
                    target = _target(companies[cid], source)["target_id"]
                    external = observation.source_job_id
                    if external in ("", "unknown"):
                        status, reason = "missing_source_evidence", "missing_external_identity"
                batch.append((source, row["rowid"], target, external, status, reason))
                if len(batch) >= 500:
                    ledger.executemany("INSERT OR IGNORE INTO targets(source,source_rowid,target_id,external_id,status,reason) VALUES(?,?,?,?,?,?)", batch)
                    ledger.commit()
                    batch.clear()
            ledger.executemany("INSERT OR IGNORE INTO targets(source,source_rowid,target_id,external_id,status,reason) VALUES(?,?,?,?,?,?)", batch)
            ledger.commit()
    ledger.execute("INSERT OR REPLACE INTO metadata VALUES('inventory_complete','1')")
    ledger.commit()


def audit(operation, catalog):
    with sqlite3.connect(operation / "outcomes.sqlite3") as ledger:
        ledger.executescript("""
            CREATE TABLE IF NOT EXISTS targets(
                source TEXT, source_rowid INTEGER, target_id TEXT, external_id TEXT,
                status TEXT, reason TEXT, canonical_job_id TEXT DEFAULT '', checked_at TEXT DEFAULT '',
                PRIMARY KEY(source,source_rowid));
            CREATE INDEX IF NOT EXISTS targets_identity ON targets(target_id,external_id);
            CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT);
        """)
        if not ledger.execute("SELECT 1 FROM metadata WHERE key='inventory_complete'").fetchone():
            inventory(operation, ledger)
        with sqlite3.connect(catalog.as_uri() + "?mode=ro", uri=True) as live:
            live.row_factory = sqlite3.Row
            checked = utc_now()
            # Indexed identities and PK joins: never fetch full catalog JSON.
            updates = []
            for target, external in ledger.execute("SELECT DISTINCT target_id,external_id FROM targets WHERE target_id<>'' AND external_id NOT IN ('','unknown')"):
                row = live.execute("""
                    SELECT j.canonical_job_id,j.lifecycle_state,q.status AS queue_status,q.reason_codes_json,
                           a.canonical_job_id AS published
                    FROM canonical_job_external_ids e
                    JOIN canonical_jobs j ON j.canonical_job_id=e.canonical_job_id
                    LEFT JOIN acquisition_publication_queue q ON q.canonical_job_id=j.canonical_job_id
                    LEFT JOIN acquisition_publication_head h ON h.head_id=1
                    LEFT JOIN acquisition_publication_jobs a ON a.publication_id=h.publication_id
                        AND a.canonical_job_id=j.canonical_job_id
                    WHERE e.source_id=? AND e.external_job_id=?
                """, (target, external)).fetchone()
                status, reason, canonical = "pending", "no_catalog_identity", ""
                if row:
                    canonical = row["canonical_job_id"]
                    if row["lifecycle_state"] != "active":
                        status, reason = "excluded", "catalog_" + row["lifecycle_state"]
                    elif row["published"]:
                        status, reason = "published_requires_app_check", "current_head_membership"
                    elif row["queue_status"] == "rejected":
                        status, reason = "failed_validation", row["reason_codes_json"]
                    else:
                        reason = "publication_" + str(row["queue_status"] or "missing_queue")
                updates.append((status, reason, canonical, checked, target, external))
                if len(updates) >= 500:
                    ledger.executemany("UPDATE targets SET status=?,reason=?,canonical_job_id=?,checked_at=? WHERE target_id=? AND external_id=?", updates)
                    ledger.commit()
                    updates.clear()
            ledger.executemany("UPDATE targets SET status=?,reason=?,canonical_job_id=?,checked_at=? WHERE target_id=? AND external_id=?", updates)
            ledger.commit()
        counts = dict(ledger.execute("SELECT status,count(*) FROM targets GROUP BY status"))
        summary = {"checked_at": checked, "source_rows": sum(counts.values()), "outcomes": counts,
                   "ready": False, "readiness_note": "Membership is not verified customer discoverability; resolve pending/review and run application acceptance."}
        write_json(operation / "outcomes.json", summary)
        return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operation", type=lambda p: Path(p).resolve(), required=True)
    parser.add_argument("--catalog", type=lambda p: Path(p).resolve(), required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.operation, args.catalog), indent=2))
