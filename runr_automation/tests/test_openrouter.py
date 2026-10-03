import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from runr_automation.providers.openrouter import OpenRouterProvider
from runr_automation.smoke import run_provider_verification
from runr_automation.scope_router import ScopeManifest
from runr_automation.state import StateStore


class _OpenRouterHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        server = self.server
        server.calls += 1
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        content = "Runr openrouter controller smoke passed.\n" if b"Runr openrouter controller smoke passed." in body else "implemented\n"
        if server.calls == 1:
            tool_call = {
                "id": "call-write",
                "type": "function",
                "function": {
                    "name": "write_file",
                    "arguments": json.dumps(
                        {"path": "src/result.txt" if content.startswith("Runr") else "allowed/result.txt", "content": content}
                    ),
                },
            }
        elif server.calls == 2:
            tool_call = {
                "id": "call-test",
                "type": "function",
                "function": {"name": "run_required_tests", "arguments": "{}"},
            }
        else:
            tool_call = {
                "id": "call-finish",
                "type": "function",
                "function": {
                    "name": "finish",
                    "arguments": json.dumps({"summary": "bounded implementation complete"}),
                },
            }
        response = {
            "id": f"openrouter-test-{server.calls}",
            "choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [tool_call]}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.01},
        }
        body = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        return


class _Server(ThreadingHTTPServer):
    calls: int = 0


def _server():
    server = _Server(("127.0.0.1", 0), _OpenRouterHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, f"http://127.0.0.1:{server.server_port}/api/v1"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_openrouter_tool_loop_is_scoped_and_records_cost(tmp_path: Path) -> None:
    server_and_endpoint = _server()
    server, endpoint = next(server_and_endpoint)
    try:
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "README.md").write_text("base\n", encoding="utf-8")
        store = StateStore(tmp_path / "state.db")
        provider = OpenRouterProvider(
            "test-openrouter-key",
            model="test/model",
            endpoint=endpoint,
            store=store,
            max_usd_per_job=1,
            max_usd_per_day=2,
        )
        request = SimpleNamespace(
            job_id="job-1",
            scope=ScopeManifest(
                issue_id="issue-1",
                subsystem="test",
                co_owners=(),
                allowed_reads=("README.md",),
                allowed_writes=("allowed/result.txt",),
                denied_roots=(),
                required_tests=("focused-test",),
            ),
        )
        prompt = tmp_path / "prompt.md"
        prompt.write_text("Implement the bounded change.", encoding="utf-8")
        tests: list[tuple[str, ...]] = []
        result = provider.run_implementation(
            request,
            prompt,
            cwd=repo,
            test_runner=lambda _cwd, commands: tests.append(commands) or True,
        )

        assert result.returncode == 0
        assert result.session_id == "openrouter-test-3"
        assert (repo / "allowed" / "result.txt").read_text(encoding="utf-8") == "implemented\n"
        assert tests == [("focused-test",)]
        assert server.calls == 3
        assert store.provider_spend(job_id="job-1", provider="openrouter") == pytest.approx((0.03, 0.03))
    finally:
        server.shutdown()
        server_and_endpoint.close() if hasattr(server_and_endpoint, "close") else None


def test_openrouter_budget_stops_before_request(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.db")
    store.record_provider_spend(
        job_id="job-1", provider="openrouter", model="test/model", amount_usd=0.01
    )
    provider = OpenRouterProvider(
        "test-openrouter-key",
        model="test/model",
        endpoint="http://127.0.0.1:1/api/v1",
        store=store,
        max_usd_per_job=0.01,
        max_usd_per_day=1,
    )
    request = SimpleNamespace(
        job_id="job-1",
        scope=ScopeManifest("issue-1", "test", (), ("README.md",), ("result.txt",), (), ()),
    )
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Implement.", encoding="utf-8")

    result = provider.run_implementation(request, prompt, cwd=tmp_path, test_runner=lambda *_: True)

    assert result.returncode == 1
    assert "budget exhausted" in result.output


def test_openrouter_reaches_real_controller_approval_cycle(tmp_path: Path) -> None:
    server_and_endpoint = _server()
    server, endpoint = next(server_and_endpoint)
    try:
        provider = OpenRouterProvider(
            "test-openrouter-key",
            model="test/model",
            endpoint=endpoint,
            store=StateStore(tmp_path / "verification" / "openrouter-e2e" / "runtime" / "state.db"),
            max_usd_per_job=1,
            max_usd_per_day=2,
        )
        report = run_provider_verification(
            tmp_path / "verification",
            "openrouter",
            provider,
            run_id="openrouter-e2e",
        )

        assert report["status"] == "awaiting_approval"
        assert report["tests_passed"] is True
        assert report["clean_worktree"] is True
        assert report["commit_sha"]
        assert server.calls == 3
    finally:
        server.shutdown()
        server_and_endpoint.close() if hasattr(server_and_endpoint, "close") else None
