import json

from runr_automation.jobs.deduplicate import DeduplicationJob, IssueSummary


class FakeProjection:
    def __init__(self) -> None:
        self.calls = []

    def mark_duplicate(self, issue_id, candidate_id, evidence):
        self.calls.append((issue_id, candidate_id, evidence))

    def mark_review(self, issue_id, evidence):
        self.calls.append(("review", issue_id, evidence))


def test_ambiguous_candidate_stays_open_and_invalid_json_only_requests_review() -> None:
    issue = IssueSummary("RUN-20", "Add OAuth login", "support Google", "WS-06", ("backend/auth.py",))
    candidate = IssueSummary("RUN-10", "OAuth login", "support GitHub", "WS-06", ("backend/auth.py",))
    projection = FakeProjection()

    result = DeduplicationJob(projection).run(issue, (candidate,), lambda _: "not-json")

    assert result.outcome == "possible_duplicate"
    assert projection.calls[0][0] == "review"
    assert not any(call[0] == "RUN-20" for call in projection.calls)


def test_only_high_confidence_schema_valid_duplicate_mutates_relation() -> None:
    issue = IssueSummary("RUN-20", "Add OAuth login", "Google OAuth", "WS-06", ("backend/auth.py",))
    candidate = IssueSummary("RUN-10", "Add OAuth login", "Google OAuth", "WS-06", ("backend/auth.py",))
    projection = FakeProjection()
    model = lambda _: json.dumps({
        "outcome": "duplicate", "candidate_id": "RUN-10", "confidence": 0.97,
        "overlap": ["same acceptance criteria"], "differences": []
    })

    result = DeduplicationJob(projection).run(issue, (candidate,), model)

    assert result.outcome == "duplicate"
    assert projection.calls[0][0:2] == ("RUN-20", "RUN-10")
