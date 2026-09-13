"""Exercise the real Python/Chromium collector using only a loopback fixture."""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.connectors.employer_site_fallbacks import fetch_browser_snapshot
from scripts.master_employer_jobs_catalog import RequestAccounting, TransportGate


def main() -> int:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'''<html><body><script type="application/json">
            {"jobs":[{"id":"fixture-1","title":"Fixture Engineer",
            "url":"/jobs/fixture-1","location":"Berlin, Germany"}]}
            </script></body></html>'''
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/careers"
    accounting = RequestAccounting(max_attempts=4)
    gate = TransportGate(accounting=accounting)
    try:
        result = fetch_browser_snapshot(
            url, timeout_seconds=10, max_requests=4,
            request_guard=gate.browser_request,
            browser_process_guard=gate.browser_process,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    jobs = result.get("jobs", [])
    passed = (
        result["status"] == "completed"
        and any(job.get("job_detail_url") == url.replace("/careers", "/jobs/fixture-1") for job in jobs)
        and 1 <= accounting.snapshot()["total_attempts"] <= 4
        and result.get("complete_snapshot") is False
    )
    print(json.dumps({
        "passed": passed, "fixture": "loopback_only", "status": result["status"],
        "error": result.get("error"), "jobs": len(jobs),
        "accounting": accounting.snapshot(), "complete_snapshot": result.get("complete_snapshot"),
    }, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
