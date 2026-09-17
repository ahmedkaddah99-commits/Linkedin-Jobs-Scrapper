from pathlib import Path

from tools.runr_automation.linear_client import FakeLinearClient, RemoteIssue
from tools.runr_automation.poller import Poller
from tools.runr_automation.state import StateStore


def test_poller_restarts_from_overlap_and_deduplicates_events(tmp_path: Path) -> None:
    client = FakeLinearClient(
        [
            RemoteIssue("linear-1", "RUN-1", "2026-09-17T10:00:00+00:00", "First", "A"),
            RemoteIssue("linear-2", "RUN-2", "2026-09-17T10:05:00+00:00", "Second", "B"),
        ]
    )
    store = StateStore(tmp_path / "state.db")
    poller = Poller(store, client, overlap_seconds=60)

    first = poller.run_once()
    client.add(
        RemoteIssue("linear-2", "RUN-2", "2026-09-17T10:06:00+00:00", "Second revised", "B")
    )

    second = Poller(store, client, overlap_seconds=60).run_once()

    assert first.recorded_events == 2
    assert second.recorded_events == 1
    assert client.requested_after[-1] == "2026-09-17T10:04:00+00:00"
    with store.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 3
        assert connection.execute("SELECT COUNT(*) FROM issues").fetchone()[0] == 2
        assert connection.execute(
            "SELECT value FROM controller_state WHERE key = 'linear_watermark'"
        ).fetchone()[0] == "2026-09-17T10:06:00+00:00"
