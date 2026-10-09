"""Summarize the durable v16 ledger without exposing credentials."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
version = str(__import__("os").environ.get("COMPANY_ENRICH_API_VERSION", "16"))
path = ROOT / f"data/audit/companyenrich_live_2026-09-26/provider_results_v{version}_sequential_proxy.jsonl"
events = {}
company_events = {}
matched_ids = set()
result_ids = set()
cost = 0.0
for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
    try:
        item = json.loads(line)
    except (TypeError, ValueError):
        continue
    event = str(item.get("event") or "")
    events[event] = events.get(event, 0) + 1
    cid = str(item.get("company_id") or "")
    if cid:
        company_events.setdefault(cid, set()).add(event)
    if event == "result":
        result_ids.add(cid)
        if item.get("matched"):
            matched_ids.add(cid)
        try:
            cost += float(item.get("credit_cost") or 0)
        except (TypeError, ValueError):
            pass
print(json.dumps({"events": events, "unique_result_companies": len(result_ids), "unique_matched_companies": len(matched_ids), "credit_cost_from_result_events": cost, "unique_ledger_companies": len(company_events)}, indent=2))
