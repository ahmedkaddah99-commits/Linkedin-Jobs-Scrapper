"""Durable, overlap-aware Linear issue polling."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .fingerprints import normalized_issue_fingerprint
from .linear_client import LinearIssueReader
from .redaction import redact
from .state import StateStore


WATERMARK_KEY = "linear_watermark"


@dataclass(frozen=True)
class PollResult:
    pages: int
    recorded_events: int
    watermark: str | None


class Poller:
    def __init__(self, store: StateStore, client: LinearIssueReader, *, overlap_seconds: int = 90) -> None:
        self.store = store
        self.client = client
        self.overlap_seconds = overlap_seconds

    def run_once(self) -> PollResult:
        watermark = self._read_watermark()
        requested_after = _subtract_overlap(watermark, self.overlap_seconds) if watermark else None
        cursor: str | None = None
        pages = 0
        recorded_events = 0
        newest = watermark

        while True:
            page = self.client.list_issues(requested_after, cursor=cursor)
            pages += 1
            page_newest = max((issue.updated_at for issue in page.issues), default=None)
            if page_newest and (newest is None or _parse_timestamp(page_newest) > _parse_timestamp(newest)):
                newest = page_newest
            with self.store.connect() as connection:
                for issue in page.issues:
                    fingerprint = normalized_issue_fingerprint(issue)
                    event_key = f"{issue.linear_id}:{issue.updated_at}:{fingerprint}"
                    now = datetime.now(timezone.utc).isoformat()
                    connection.execute(
                        """
                        INSERT INTO issues(
                            linear_id, identifier, latest_remote_timestamp,
                            normalized_fingerprint, subsystem, lifecycle_state,
                            payload_json, observed_at
                        ) VALUES (?, ?, ?, ?, NULL, ?, ?, ?)
                        ON CONFLICT(linear_id) DO UPDATE SET
                            identifier=excluded.identifier,
                            latest_remote_timestamp=excluded.latest_remote_timestamp,
                            normalized_fingerprint=excluded.normalized_fingerprint,
                            lifecycle_state=excluded.lifecycle_state,
                            payload_json=excluded.payload_json,
                            observed_at=excluded.observed_at
                        """,
                        (
                            issue.linear_id,
                            issue.identifier,
                            issue.updated_at,
                            fingerprint,
                            issue.lifecycle_state,
                            json.dumps(redact(issue.payload), sort_keys=True),
                            now,
                        ),
                    )
                    cursor_result = connection.execute(
                        """
                        INSERT OR IGNORE INTO events(
                            event_key, payload_hash, first_seen, last_seen, processed_state
                        ) VALUES (?, ?, ?, ?, 'pending')
                        """,
                        (event_key, fingerprint, now, now),
                    )
                    recorded_events += cursor_result.rowcount
                if newest is not None:
                    connection.execute(
                        """
                        INSERT INTO controller_state(key, value, updated_at)
                        VALUES (?, ?, ?)
                        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                        """,
                        (WATERMARK_KEY, newest, datetime.now(timezone.utc).isoformat()),
                    )

            if page.next_cursor is None:
                break
            cursor = page.next_cursor

        return PollResult(pages=pages, recorded_events=recorded_events, watermark=newest)

    def _read_watermark(self) -> str | None:
        with self.store.connect() as connection:
            row = connection.execute(
                "SELECT value FROM controller_state WHERE key = ?", (WATERMARK_KEY,)
            ).fetchone()
        return row[0] if row else None


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _subtract_overlap(value: str, overlap_seconds: int) -> str:
    return (_parse_timestamp(value) - timedelta(seconds=overlap_seconds)).isoformat()
