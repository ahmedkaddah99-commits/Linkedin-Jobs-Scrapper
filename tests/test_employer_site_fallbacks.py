from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from backend.connectors.employer_site_fallbacks import (
    _job_links_from_rendered_html,
    extract_embedded_jobs,
    fetch_browser_snapshot,
)


def test_extract_embedded_jobs_reads_framework_state_and_resolves_urls() -> None:
    html = """
    <html><body>
      <script type="application/json" id="__NEXT_DATA__">
        {"props":{"pageProps":{"jobs":[{"id":"42","title":"Data Engineer","url":"/jobs/42","description":"Build data products.","location":"Berlin, Germany"}]}}}
      </script>
    </body></html>
    """

    jobs = extract_embedded_jobs(html, "https://acme.example/careers")

    assert len(jobs) == 1
    assert jobs[0]["job_id"] == "42"
    assert jobs[0]["job_detail_url"] == "https://acme.example/jobs/42"
    assert jobs[0]["source_raw_payload"]["format"] == "embedded-json"


def test_extract_embedded_jobs_ignores_unrelated_application_state() -> None:
    html = '<script type="application/json">' + json.dumps({"props": {"user": {"name": "Ada"}}}) + "</script>"

    assert extract_embedded_jobs(html, "https://acme.example/careers") == []


def test_extract_embedded_jobs_ignores_organization_metadata() -> None:
    html = (
        '<script type="application/ld+json">'
        + json.dumps({"@type": "Organization", "name": "N26", "url": "https://n26.com/en-eu"})
        + "</script>"
    )

    assert extract_embedded_jobs(html, "https://n26.com/en-eu/careers") == []


def test_rendered_job_links_ignore_external_hosts() -> None:
    html = """
    <a href="https://acme.example/jobs/local">Local Engineer</a>
    <a href="https://external.example/jobs/foreign">Foreign Engineer</a>
    """

    jobs = _job_links_from_rendered_html(html, "https://acme.example/careers", max_job_links=10)

    assert [job["job_detail_url"] for job in jobs] == ["https://acme.example/jobs/local"]


class _FakeResponse:
    def __init__(self, url: str, payload: object) -> None:
        self.url = url
        self.headers = {"content-type": "application/json"}
        self.request = SimpleNamespace(resource_type="xhr")
        self._payload = payload

    def json(self) -> object:
        return self._payload


class _FakePage:
    def __init__(self) -> None:
        self.handlers: dict[str, object] = {}

    def on(self, event: str, callback: object) -> None:
        self.handlers[event] = callback

    def goto(self, *_args: object, **_kwargs: object) -> None:
        response = _FakeResponse(
            "https://acme.example/api/jobs",
            {
                "jobs": [
                    {"id": "xhr-1", "title": "Backend Engineer", "url": "/jobs/xhr-1", "location": "Hamburg, Germany"}
                ]
            },
        )
        callback = self.handlers["response"]
        callback(response)  # type: ignore[operator]

    def wait_for_timeout(self, *_args: object) -> None:
        return None

    def content(self) -> str:
        return '<html><h1>Backend Engineer</h1><script type="application/json">{"jobs":[]}</script></html>'


class _FakeContext:
    def new_page(self) -> _FakePage:
        return _FakePage()


class _FakeBrowser:
    def new_context(self, **_kwargs: object) -> _FakeContext:
        return _FakeContext()

    def close(self) -> None:
        return None


class _FakeChromium:
    def launch(self, **_kwargs: object) -> _FakeBrowser:
        return _FakeBrowser()


class _FakePlaywright:
    chromium = _FakeChromium()

    def __enter__(self) -> "_FakePlaywright":
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def test_fetch_browser_snapshot_keeps_same_origin_xhr_and_rendered_content(monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.connectors.employer_site_fallbacks as fallbacks

    monkeypatch.setattr(fallbacks, "sync_playwright", lambda: _FakePlaywright())

    snapshot = fetch_browser_snapshot(
        "https://acme.example/careers",
        max_job_links=10,
        timeout_seconds=5,
        max_requests=5,
    )

    assert snapshot["status"] == "completed"
    assert snapshot["jobs"][0]["source_raw_payload"]["format"] == "xhr"
    assert snapshot["jobs"][0]["job_detail_url"] == "https://acme.example/jobs/xhr-1"


def test_fetch_browser_snapshot_returns_report_data_when_browser_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.connectors.employer_site_fallbacks as fallbacks

    monkeypatch.setattr(fallbacks, "sync_playwright", None)

    snapshot = fetch_browser_snapshot(
        "https://acme.example/careers",
        max_job_links=10,
        timeout_seconds=5,
        max_requests=5,
    )

    assert snapshot["status"] == "browser_unavailable"
    assert snapshot["jobs"] == []
