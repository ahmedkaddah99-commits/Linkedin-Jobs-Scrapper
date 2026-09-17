from runr_automation.fingerprints import normalized_issue_fingerprint
from runr_automation.linear_client import FakeLinearClient, RemoteIssue
from runr_automation.poller import Poller
from runr_automation.reconciler import Reconciler, invalidated_stages
from runr_automation.state import StateStore


def test_cosmetic_edits_do_not_invalidate_expensive_stages() -> None:
    original = RemoteIssue(
        "linear-1",
        "RUN-1",
        "2026-09-17T10:00:00+00:00",
        "Add API",
        "Build the endpoint",
        payload={
            "acceptance_criteria": ["returns 200"],
            "allowed_paths": ["backend/api/**"],
            "comments": ["Looks good"],
        },
    )
    cosmetic_edit = RemoteIssue(
        "linear-1",
        "RUN-1",
        "2026-09-17T10:01:00+00:00",
        "Add API",
        "Build the endpoint",
        payload={
            "acceptance_criteria": ["returns 200"],
            "allowed_paths": ["backend/api/**"],
            "comments": ["Please ship this"],
        },
    )
    relevant_edit = RemoteIssue(
        "linear-1",
        "RUN-1",
        "2026-09-17T10:02:00+00:00",
        "Add API",
        "Build the endpoint",
        payload={
            "acceptance_criteria": ["returns 201"],
            "allowed_paths": ["backend/api/**"],
            "comments": ["Please ship this"],
        },
    )

    assert normalized_issue_fingerprint(original) == normalized_issue_fingerprint(cosmetic_edit)
    assert normalized_issue_fingerprint(original) != normalized_issue_fingerprint(relevant_edit)
    assert invalidated_stages(original, cosmetic_edit) == ()
    assert invalidated_stages(original, relevant_edit) == (
        "deduplicate",
        "research",
        "parallelize",
    )


def test_reconciliation_enqueues_each_new_event_once(tmp_path) -> None:
    store = StateStore(tmp_path / "state.db")
    client = FakeLinearClient(
        [RemoteIssue("linear-1", "RUN-1", "2026-09-17T10:00:00+00:00", "Add API", "Build it")]
    )
    Poller(store, client).run_once()

    first = Reconciler(store).run_once()
    second = Reconciler(store).run_once()

    assert first.enqueued_jobs == 1
    assert second.enqueued_jobs == 0
    with store.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 1
        assert connection.execute("SELECT processed_state FROM events").fetchone()[0] == "queued"
