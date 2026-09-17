"""Linear client contracts and a deterministic fake used by controller tests."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class RemoteIssue:
    linear_id: str
    identifier: str
    updated_at: str
    title: str
    description: str
    lifecycle_state: str | None = None
    project_id: str | None = None
    label_ids: tuple[str, ...] = ()
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IssuePage:
    issues: tuple[RemoteIssue, ...]
    next_cursor: str | None = None


class LinearIssueReader(Protocol):
    def list_issues(
        self, updated_after: str | None, *, cursor: str | None = None, page_size: int = 50
    ) -> IssuePage: ...


class FakeLinearClient:
    """In-memory issue reader that records query watermarks for assertions."""

    def __init__(self, issues: list[RemoteIssue] | None = None) -> None:
        self.issues = list(issues or [])
        self.requested_after: list[str | None] = []

    def add(self, issue: RemoteIssue) -> None:
        self.issues.append(issue)

    def list_issues(
        self, updated_after: str | None, *, cursor: str | None = None, page_size: int = 50
    ) -> IssuePage:
        self.requested_after.append(updated_after)
        eligible = [
            issue
            for issue in self.issues
            if updated_after is None or _parse_timestamp(issue.updated_at) >= _parse_timestamp(updated_after)
        ]
        eligible.sort(key=lambda issue: (issue.updated_at, issue.linear_id))
        start = int(cursor or 0)
        page = tuple(eligible[start : start + page_size])
        next_cursor = str(start + page_size) if start + page_size < len(eligible) else None
        return IssuePage(page, next_cursor)


class LinearGraphQLClient:
    """Read Linear issues through the GraphQL API without persisting its token."""

    def __init__(self, token: str, team_id: str, endpoint: str = "https://api.linear.app/graphql") -> None:
        self._token = token
        self.team_id = team_id
        self.endpoint = endpoint

    def list_issues(
        self, updated_after: str | None, *, cursor: str | None = None, page_size: int = 50
    ) -> IssuePage:
        query = """
        query Issues($teamId: ID!, $after: String, $first: Int!, $updatedAfter: DateTime) {
          issues(
            filter: { team: { id: { eq: $teamId } }, updatedAt: { gte: $updatedAfter } }
            first: $first
            after: $after
          ) {
            nodes {
              id identifier updatedAt title description
              state { name }
              project { id }
              labels { nodes { id name parent { name } } }
            }
            pageInfo { hasNextPage endCursor }
          }
        }
        """
        payload = self._post(
            {
                "query": query,
                "variables": {
                    "teamId": self.team_id,
                    "after": cursor,
                    "first": page_size,
                    "updatedAfter": updated_after,
                },
            }
        )
        issues = tuple(_remote_issue(node) for node in payload["data"]["issues"]["nodes"])
        page_info = payload["data"]["issues"]["pageInfo"]
        return IssuePage(issues, page_info["endCursor"] if page_info["hasNextPage"] else None)

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": self._token,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlopen(request, timeout=30) as response:  # noqa: S310 - endpoint is configured by the user
            result = json.load(response)
        if result.get("errors"):
            raise RuntimeError("Linear GraphQL request failed")
        return result


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _remote_issue(node: dict[str, Any]) -> RemoteIssue:
    return RemoteIssue(
        linear_id=node["id"],
        identifier=node["identifier"],
        updated_at=node["updatedAt"],
        title=node["title"],
        description=node.get("description") or "",
        lifecycle_state=(node.get("state") or {}).get("name"),
        project_id=(node.get("project") or {}).get("id"),
        label_ids=tuple(label["id"] for label in (node.get("labels") or {}).get("nodes", [])),
        payload=node,
    )
