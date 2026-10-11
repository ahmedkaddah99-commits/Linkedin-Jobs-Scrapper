import json
from io import BytesIO

import runr_automation.linear_client as linear_client


def test_linear_issue_query_uses_updated_after_type_accepted_by_linear_api(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout: int):
        captured["request"] = request
        assert timeout == 30
        return BytesIO(
            json.dumps(
                {
                    "data": {
                        "issues": {
                            "nodes": [],
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                        }
                    }
                }
            ).encode("utf-8")
        )

    monkeypatch.setattr(linear_client, "urlopen", fake_urlopen)

    linear_client.LinearGraphQLClient("token", "team").list_issues("2026-01-01T00:00:00+00:00")

    payload = json.loads(captured["request"].data)
    assert "$updatedAfter: DateTimeOrDuration" in payload["query"]


def test_initial_linear_issue_query_omits_null_updated_at_filter(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout: int):
        captured["request"] = request
        assert timeout == 30
        return BytesIO(
            b'{"data":{"issues":{"nodes":[],"pageInfo":{"hasNextPage":false,"endCursor":null}}}}'
        )

    monkeypatch.setattr(linear_client, "urlopen", fake_urlopen)

    linear_client.LinearGraphQLClient("token", "team").list_issues(None)

    payload = json.loads(captured["request"].data)
    assert "updatedAt: { gte: $updatedAfter }" not in payload["query"]
    assert "updatedAfter" not in payload["variables"]
