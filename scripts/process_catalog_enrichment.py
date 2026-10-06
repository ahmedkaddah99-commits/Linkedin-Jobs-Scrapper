"""Continuously enrich queued published versions with Mistral Nemo on the VPS."""
from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from uuid import uuid4

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from backend.application.catalog_enrichment import attach_source_metadata, enrich_version
from backend.application.enrichment_field_pass import missing_fields, supplement
from backend.application.catalog_job_filters import PROMPT_VERSION as FILTER_PROMPT
from backend.application.vps_job_descriptions import NEMO_MODEL
from backend.config import load_project_dotenv
from backend.database.connection import validate_release_provenance


FILTER_ACCEPTABLE_SQL = """CASE WHEN json_valid(f.filters_json) THEN
    json_type(f.filters_json)='object' AND (
        json_extract(f.filters_json,'$.collar')='blue'
        OR EXISTS(SELECT 1 FROM job_filter_roles r WHERE r.version_id=f.version_id
            AND r.content_hash=f.content_hash)) ELSE 0 END"""


DESCRIPTION_ACCEPTABLE_SQL = """d.prompt_version IN ('runr_description_v1','runr_description_nemo_v2','runr_description_nemo_v3')
    AND CASE WHEN json_valid(d.summary_json) AND json_valid(d.structured_json) THEN
        json_type(d.summary_json)='object' AND json_type(d.structured_json)='object' AND (
            COALESCE(json_array_length(d.summary_json,'$.responsibilities'),0)>0
            OR COALESCE(json_array_length(d.summary_json,'$.required_qualifications'),0)>0
            OR COALESCE(json_array_length(d.summary_json,'$.preferred_qualifications'),0)>0
            OR COALESCE(json_array_length(d.summary_json,'$.benefits'),0)>0
            OR COALESCE(json_array_length(d.summary_json,'$.application_details'),0)>0
            OR LENGTH(TRIM(COALESCE(json_extract(d.summary_json,'$.overview'),'')))>0)
        ELSE 0 END"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def execute(sql: str, args=()) -> list[dict]:
    def parameter(value):
        if value is None:
            return {"type": "null"}
        if isinstance(value, int):
            return {"type": "integer", "value": str(value)}
        return {"type": "text", "value": str(value)}
    body = {"requests": [{"type": "execute", "stmt": {
        "sql": sql, "args": [parameter(v) for v in args], "want_rows": True}}, {"type": "close"}]}
    url = os.environ["TURSO_DATABASE_URL"].replace("libsql://", "https://").rstrip("/") + "/v2/pipeline"
    request = Request(url, data=json.dumps(body).encode(), headers={
        "Authorization": "Bearer " + os.environ["TURSO_AUTH_TOKEN"], "Content-Type": "application/json"})
    with urlopen(request, timeout=30) as response:
        result = json.load(response)["results"][0]
    if result["type"] != "ok":
        raise RuntimeError("turso_" + str(result.get("error", {}).get("code", "unknown")))
    value = result["response"]["result"]
    def decode(cell):
        if cell["type"] == "null":
            return None
        if cell["type"] == "integer":
            return int(cell["value"])
        return cell["value"]
    names = [c["name"] for c in value["cols"]]
    return [dict(zip(names, map(decode, row))) for row in value["rows"]]


class NemoClient:
    """Bound daily cost before calls and retain a durable local usage ledger."""
    def __init__(self, ledger: Path, budget: float):
        self.lock = threading.Lock()
        self.budget = budget
        ledger.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(ledger, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS calls(id TEXT PRIMARY KEY,day TEXT,reserved REAL,cost REAL,state TEXT)")
        self.db.execute("CREATE INDEX IF NOT EXISTS calls_day ON calls(day)")
        self.db.commit()

    def remaining(self) -> float:
        day = datetime.now(timezone.utc).date().isoformat()
        with self.lock:
            used = self.db.execute("SELECT COALESCE(SUM(COALESCE(cost,reserved)),0) FROM calls WHERE day=?", (day,)).fetchone()[0]
        return self.budget - used

    def __call__(self, prompt: str) -> dict:
        day = datetime.now(timezone.utc).date().isoformat()
        # UTF-8 bytes upper-bound input tokens; reserve the entire output cap.
        reserve = (len(prompt.encode()) + 8192) * 0.03 / 1_000_000
        identity = uuid4().hex
        with self.lock:
            used = self.db.execute("SELECT COALESCE(SUM(COALESCE(cost,reserved)),0) FROM calls WHERE day=?", (day,)).fetchone()[0]
            if used + reserve > self.budget:
                raise RuntimeError("daily_budget_exhausted")
            self.db.execute("INSERT INTO calls VALUES (?,?,?,NULL,'reserved')", (identity, day, reserve))
            self.db.commit()
        body = {"model": NEMO_MODEL, "messages": [{"role": "user", "content": prompt}],
                "temperature": 0, "max_tokens": 8192, "response_format": {"type": "json_object"},
                "provider": {"order": ["Parasail", "DeepInfra", "DekaLLM"], "require_parameters": True,
                             "max_price": {"prompt": 0.03, "completion": 0.03}}}
        request = Request("https://openrouter.ai/api/v1/chat/completions", data=json.dumps(body).encode(),
                          headers={"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"], "Content-Type": "application/json"})
        with urlopen(request, timeout=120) as response:
            payload = json.load(response)
        usage = payload.get("usage") or {}
        cost = usage.get("cost")
        if not isinstance(cost, (int, float)) or not math.isfinite(cost) or cost < 0:
            cost = reserve
        with self.lock:
            self.db.execute("UPDATE calls SET cost=?,state='received' WHERE id=?", (cost, identity))
            self.db.commit()
        if payload.get("model") != NEMO_MODEL:
            raise ValueError("unexpected_model")
        result = json.loads(payload["choices"][0]["message"]["content"])
        result["_runr_model"] = NEMO_MODEL
        return result


def claim(limit: int) -> tuple[str, list[dict]]:
    timestamp = now()
    execute("UPDATE job_enrichment_queue SET state='pending',next_attempt_at='' WHERE version_id IN ("
            "SELECT version_id FROM job_enrichment_queue WHERE state='completed' AND gap_pass_attempted=0 LIMIT ?)", (limit,))
    execute("UPDATE job_enrichment_queue SET state='pending',lease_token='',lease_expires_at='' "
            "WHERE state='processing' AND lease_expires_at<?", (timestamp,))
    token = uuid4().hex
    lease = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    rows = execute("""UPDATE job_enrichment_queue SET state='processing',attempts=attempts+1,
        lease_token=?,lease_expires_at=?,updated_at=? WHERE version_id IN (
        SELECT q.version_id FROM job_enrichment_queue q
        WHERE q.state='pending' AND q.next_attempt_at<=? ORDER BY q.next_attempt_at,q.version_id LIMIT ?)
        AND state='pending' RETURNING version_id""", (token, lease, timestamp, timestamp, limit))
    if not rows:
        return token, []
    ids = [r["version_id"] for r in rows]
    candidates = execute("""SELECT j.canonical_job_id,q.version_id AS current_version_id,j.title,j.canonical_url,
        CASE WHEN j.current_version_id=q.version_id THEN 1 ELSE 0 END AS version_is_current,
        q.attempts,v.content_hash,v.description,v.payload_json AS version_payload_json,v.location AS version_location,v.apply_url,
        CASE WHEN f.content_hash=v.content_hash AND """ + FILTER_ACCEPTABLE_SQL + """ THEN 1 ELSE 0 END AS filters_ready,
        CASE WHEN d.content_hash=v.content_hash AND """ + DESCRIPTION_ACCEPTABLE_SQL + """ THEN 1 ELSE 0 END AS description_ready
        FROM job_enrichment_queue q JOIN canonical_jobs j ON j.canonical_job_id=q.canonical_job_id
        JOIN job_posting_versions v ON v.version_id=q.version_id
        LEFT JOIN job_filter_intelligence f ON f.version_id=v.version_id
        LEFT JOIN job_description_intelligence d ON d.version_id=v.version_id
        WHERE v.version_id IN (""" + ",".join("?" for _ in ids) + ")",
        tuple(ids))
    return token, candidates


def save_stage(row: dict, token: str, output: dict) -> None:
    timestamp = now()
    guard = """SELECT 1 FROM job_enrichment_queue q JOIN canonical_jobs j
        ON j.canonical_job_id=q.canonical_job_id AND j.current_version_id=q.version_id
        JOIN job_posting_versions v ON v.version_id=q.version_id AND v.content_hash=q.content_hash
        WHERE q.version_id=? AND q.lease_token=? AND q.content_hash=? AND q.state='processing'"""
    ownership = (row["current_version_id"], token, row["content_hash"])
    if "filters" in output:
        raw = row.get("version_payload_json") or "{}"
        payload = json.loads(raw) if isinstance(raw, str) else raw
        filters = attach_source_metadata(output["filters"], payload)
        execute("""INSERT INTO job_filter_intelligence
            SELECT ?,?,?,?,?,?,? WHERE EXISTS(""" + guard + """)
            ON CONFLICT(version_id) DO UPDATE SET content_hash=excluded.content_hash,
            filters_json=excluded.filters_json,model=excluded.model,prompt_version=excluded.prompt_version,
            generated_at=excluded.generated_at RETURNING version_id""",
            (row["current_version_id"], row["canonical_job_id"], row["content_hash"], json.dumps(filters, ensure_ascii=False),
             NEMO_MODEL, FILTER_PROMPT, timestamp, *ownership))
    if "description" in output:
        d = output["description"]
        execute("""INSERT INTO job_description_intelligence
            SELECT ?,?,?,?,?,?,?,?,?,?,?,? WHERE EXISTS(""" + guard + """)
            ON CONFLICT(version_id) DO UPDATE SET content_hash=excluded.content_hash,
            summary_json=excluded.summary_json,structured_json=excluded.structured_json,original_json=excluded.original_json,
            provider=excluded.provider,model=excluded.model,prompt_version=excluded.prompt_version,
            generated_at=excluded.generated_at,updated_at=excluded.updated_at RETURNING version_id""",
            (d["version_id"], d["canonical_job_id"], d["content_hash"], json.dumps(d["summary"], ensure_ascii=False),
             json.dumps(d["structured_description"], ensure_ascii=False), json.dumps(d["original_posting"], ensure_ascii=False),
             "openrouter", NEMO_MODEL, d["prompt_version"], timestamp, timestamp, timestamp, *ownership))


def run_gap_pass(row, token, generate):
    cached = execute("""SELECT q.gap_pass_attempted,f.filters_json,d.summary_json,d.structured_json
        FROM job_enrichment_queue q
        LEFT JOIN job_filter_intelligence f ON f.version_id=q.version_id AND f.content_hash=q.content_hash
        LEFT JOIN job_description_intelligence d ON d.version_id=q.version_id AND d.content_hash=q.content_hash
        WHERE q.version_id=? AND q.lease_token=?""", (row['current_version_id'], token))
    if not cached or cached[0]['gap_pass_attempted']:
        return
    def object_value(raw):
        try:
            value=json.loads(raw or '{}')
            return value if isinstance(value,dict) else {}
        except ValueError:
            return {}
    filters,summary,structured = (object_value(cached[0][key]) for key in ('filters_json','summary_json','structured_json'))
    gaps=missing_fields(filters,summary,structured)
    reserved=execute("""UPDATE job_enrichment_queue SET gap_pass_attempted=?,missing_fields_json=?
        WHERE version_id=? AND lease_token=? AND state='processing' AND gap_pass_attempted=0
        AND EXISTS(SELECT 1 FROM canonical_jobs j WHERE j.canonical_job_id=job_enrichment_queue.canonical_job_id
            AND j.current_version_id=job_enrichment_queue.version_id) RETURNING version_id""",
        (1 if gaps else 2,json.dumps(gaps),row['current_version_id'],token))
    if not reserved or not gaps:
        return
    try:
        output,gaps=supplement(row,filters,summary,structured,generate)
        save_stage(row,token,output)
        execute("UPDATE job_enrichment_queue SET missing_fields_json=?,gap_pass_error_code='' WHERE version_id=? AND lease_token=?",
                (json.dumps(gaps),row['current_version_id'],token))
    except Exception as exc:
        if str(exc)=='daily_budget_exhausted':
            execute("UPDATE job_enrichment_queue SET gap_pass_attempted=0 WHERE version_id=? AND lease_token=?",
                    (row['current_version_id'],token))
            raise
        code='provider_http_'+str(exc.code) if isinstance(exc,HTTPError) else type(exc).__name__
        execute("UPDATE job_enrichment_queue SET gap_pass_error_code=? WHERE version_id=? AND lease_token=?",
                (code,row['current_version_id'],token))


def complete_if_ready(row,token):
    saved = execute("""UPDATE job_enrichment_queue SET state='completed',error_code='',
        lease_token='',lease_expires_at='',updated_at=? WHERE version_id=? AND lease_token=?
        AND EXISTS(SELECT 1 FROM job_filter_intelligence f WHERE f.version_id=job_enrichment_queue.version_id
            AND f.content_hash=job_enrichment_queue.content_hash AND """ + FILTER_ACCEPTABLE_SQL + """)
        AND EXISTS(SELECT 1 FROM job_description_intelligence d WHERE d.version_id=job_enrichment_queue.version_id
            AND d.content_hash=job_enrichment_queue.content_hash AND """ + DESCRIPTION_ACCEPTABLE_SQL + """)
        RETURNING version_id""", (now(), row["current_version_id"], token))
    return bool(saved)

def process(row: dict, token: str, generate) -> str:
    try:
        if not row.get("version_is_current", True):
            execute("UPDATE job_enrichment_queue SET state='superseded',lease_token='',lease_expires_at='',updated_at=? WHERE version_id=? AND lease_token=?",
                    (now(), row["current_version_id"], token))
            return "superseded"
        if not row["filters_ready"]:
            output = enrich_version({**row, "description_ready": True}, generate)
            save_stage(row, token, output)
            filters = output["filters"]
            if filters.get("collar") == "white" and not filters.get("roles"):
                raise ValueError("function_missing")
        if not row["description_ready"]:
            output = enrich_version({**row, "filters_ready": True}, generate)
            save_stage(row, token, output)
        run_gap_pass(row,token,generate)
        return "completed" if complete_if_ready(row,token) else "superseded"
    except Exception as exc:
        if isinstance(exc,ValueError) and str(exc) in {'source_missing','source_incomplete','function_missing','description_has_no_supported_facts','filter_validation_failed','filter_response_identity_mismatch'}:
            run_gap_pass(row,token,generate)
            if complete_if_ready(row,token):
                return "completed"
        code = str(exc) if str(exc) in {"source_missing", "source_incomplete"} else ("daily_budget_exhausted" if str(exc) == "daily_budget_exhausted" else type(exc).__name__)
        if isinstance(exc, HTTPError):
            code = "provider_http_" + str(exc.code)
        elif isinstance(exc, ValueError) and str(exc) in {
            "filter_response_identity_mismatch", "filter_validation_failed", "unexpected_model",
            "description_has_no_supported_facts", "function_missing"}:
            code = str(exc)
        state = code if code in {"source_missing", "source_incomplete"} else "pending"
        if code == "function_missing":
            state = "review_required"
        if code in {"filter_response_identity_mismatch", "filter_validation_failed",
                    "description_has_no_supported_facts"}:
            state = "review_required"
        retry = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
        execute("UPDATE job_enrichment_queue SET state=?,next_attempt_at=?,error_code=?,lease_token='',lease_expires_at='',updated_at=? "
                "WHERE version_id=? AND lease_token=?", (state, retry, code, now(), row["current_version_id"], token))
        return code


def main() -> int:
    load_project_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--max-jobs", type=int, default=512)
    parser.add_argument("--runtime-seconds", type=int, default=900)
    parser.add_argument("--daily-budget", type=float, default=10)
    parser.add_argument("--ledger", type=Path, default=Path("/srv/runr/state/nemo-enrichment-usage.sqlite3"))
    args = parser.parse_args()
    if not 1 <= args.workers <= 32 or not 1 <= args.max_jobs <= 10000 or args.daily_budget <= 0:
        parser.error("invalid worker, job or budget limit")
    for key in ("OPENROUTER_API_KEY", "TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN"):
        if not os.environ.get(key):
            parser.error("missing " + key)
    validate_release_provenance()
    generate = NemoClient(args.ledger, args.daily_budget)
    started = time.monotonic()
    counts: dict[str, int] = {}
    attempted = 0
    last_report = started
    exhausted = False
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        pending = set()
        while True:
            stop_claiming = (exhausted or attempted + len(pending) >= args.max_jobs
                             or time.monotonic() - started >= args.runtime_seconds
                             or counts.get("daily_budget_exhausted", 0))
            slots = args.workers - len(pending)
            if not stop_claiming and slots >= max(1, args.workers // 2):
                if generate.remaining() < 0.005:
                    counts["daily_budget_exhausted"] = counts.get("daily_budget_exhausted", 0) + 1
                    stop_claiming = True
                else:
                    token, rows = claim(min(slots, args.max_jobs - attempted - len(pending)))
                    if not rows:
                        exhausted = True
                        stop_claiming = True
                    pending.update(pool.submit(process, row, token, generate) for row in rows)
            if not pending:
                if stop_claiming:
                    break
                continue
            done, pending = wait(pending, timeout=30, return_when=FIRST_COMPLETED)
            for future in done:
                status = future.result()
                attempted += 1
                counts[status] = counts.get(status, 0) + 1
            if time.monotonic() - last_report >= 30:
                print(json.dumps({"attempted": attempted, "in_flight": len(pending), **counts}), flush=True)
                last_report = time.monotonic()
    print(json.dumps({"attempted": attempted, "seconds": round(time.monotonic() - started, 2), **counts}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
