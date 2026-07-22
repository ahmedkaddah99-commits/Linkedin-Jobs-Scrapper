"""Tests for CP-028: Evidence state model and transitions."""

import pytest

from backend.domain.evidence import (
    EVIDENCE_ACTION_NEEDED,
    EVIDENCE_KIND_EVIDENCE,
    EVIDENCE_KIND_GENERATED_OUTPUT,
    EVIDENCE_KIND_SOURCE,
    EVIDENCE_KIND_TIMELINE_MAPPING,
    EVIDENCE_KINDS,
    EVIDENCE_STATE_ARCHIVED,
    EVIDENCE_STATE_DRAFT,
    EVIDENCE_STATE_NEEDS_REVIEW,
    EVIDENCE_STATE_ORDER,
    EVIDENCE_STATE_PROCESSING,
    EVIDENCE_STATE_READY_FOR_TAILORING,
    EVIDENCE_STATE_REJECTED,
    EVIDENCE_STATE_VERIFIED,
    EVIDENCE_STATES,
    EVIDENCE_TRANSITIONS,
    EvidenceRecord,
    EvidenceStateHistory,
)


class TestEvidenceStates:
    """Acceptance criteria: All 7 states must be present."""

    def test_all_seven_states_defined(self):
        expected = {
            "draft", "processing", "needs_review", "verified",
            "rejected", "ready_for_tailoring", "archived",
        }
        assert EVIDENCE_STATES == expected

    def test_state_order_covers_all_states(self):
        assert set(EVIDENCE_STATE_ORDER) == EVIDENCE_STATES
        assert len(EVIDENCE_STATE_ORDER) == 7

    def test_every_state_has_action_needed(self):
        for state in EVIDENCE_STATES:
            assert state in EVIDENCE_ACTION_NEEDED, f"Missing action for {state}"
            assert len(EVIDENCE_ACTION_NEEDED[state]) > 10

    def test_every_state_has_transitions(self):
        for state in EVIDENCE_STATES:
            assert state in EVIDENCE_TRANSITIONS, f"Missing transitions for {state}"

    def test_four_evidence_kinds_defined(self):
        assert EVIDENCE_KINDS == {
            EVIDENCE_KIND_SOURCE,
            EVIDENCE_KIND_EVIDENCE,
            EVIDENCE_KIND_TIMELINE_MAPPING,
            EVIDENCE_KIND_GENERATED_OUTPUT,
        }



class TestEvidenceRecord:
    """Evidence records must default to draft and expose action_needed."""

    def test_created_record_defaults_to_draft(self):
        record = EvidenceRecord.create(workspace_id="ws_1", label="Test")
        assert record.state == EVIDENCE_STATE_DRAFT
        assert record.evidence_id.startswith("ev_")
        assert record.action_needed == EVIDENCE_ACTION_NEEDED[EVIDENCE_STATE_DRAFT]

    def test_roundtrip_to_dict_and_back(self):
        record = EvidenceRecord.create(
            workspace_id="ws_1", run_id="run_1", kind=EVIDENCE_KIND_SOURCE,
            label="Source item", description="A test source",
            source_ref="prof_abc", source_type="career_profile",
        )
        restored = EvidenceRecord.from_dict(record.to_dict())
        assert restored.evidence_id == record.evidence_id
        assert restored.action_needed == record.action_needed

    def test_can_be_created_with_explicit_state(self):
        record = EvidenceRecord.create(
            workspace_id="ws_1", state=EVIDENCE_STATE_VERIFIED,
            kind=EVIDENCE_KIND_GENERATED_OUTPUT,
        )
        assert record.state == EVIDENCE_STATE_VERIFIED


class TestEvidenceTransitions:
    """Only valid state transitions are allowed."""

    @pytest.mark.parametrize("from_state,to_state,expected", [
        (EVIDENCE_STATE_DRAFT, EVIDENCE_STATE_PROCESSING, True),
        (EVIDENCE_STATE_DRAFT, EVIDENCE_STATE_ARCHIVED, True),
        (EVIDENCE_STATE_DRAFT, EVIDENCE_STATE_VERIFIED, False),
        (EVIDENCE_STATE_PROCESSING, EVIDENCE_STATE_NEEDS_REVIEW, True),
        (EVIDENCE_STATE_PROCESSING, EVIDENCE_STATE_REJECTED, True),
        (EVIDENCE_STATE_NEEDS_REVIEW, EVIDENCE_STATE_VERIFIED, True),
        (EVIDENCE_STATE_NEEDS_REVIEW, EVIDENCE_STATE_REJECTED, True),
        (EVIDENCE_STATE_NEEDS_REVIEW, EVIDENCE_STATE_ARCHIVED, False),
        (EVIDENCE_STATE_VERIFIED, EVIDENCE_STATE_READY_FOR_TAILORING, True),
        (EVIDENCE_STATE_VERIFIED, EVIDENCE_STATE_ARCHIVED, True),
        (EVIDENCE_STATE_REJECTED, EVIDENCE_STATE_DRAFT, True),
        (EVIDENCE_STATE_REJECTED, EVIDENCE_STATE_ARCHIVED, True),
        (EVIDENCE_STATE_READY_FOR_TAILORING, EVIDENCE_STATE_ARCHIVED, True),
        (EVIDENCE_STATE_ARCHIVED, EVIDENCE_STATE_DRAFT, True),
        (EVIDENCE_STATE_ARCHIVED, EVIDENCE_STATE_PROCESSING, False),
    ])
    def test_transition_rules(self, from_state, to_state, expected):
        record = EvidenceRecord.create(workspace_id="ws_1", state=from_state)
        assert record.can_transition_to(to_state) == expected

    def test_full_happy_path_lifecycle(self):
        record = EvidenceRecord.create(workspace_id="ws_1")
        for target in [
            EVIDENCE_STATE_PROCESSING, EVIDENCE_STATE_NEEDS_REVIEW,
            EVIDENCE_STATE_VERIFIED, EVIDENCE_STATE_READY_FOR_TAILORING,
            EVIDENCE_STATE_ARCHIVED,
        ]:
            assert record.can_transition_to(target)
            record.state = target
        assert record.state == EVIDENCE_STATE_ARCHIVED


class TestEvidenceStateHistory:
    """State history must preserve timestamps and transitions."""

    def test_history_entry_created_with_timestamps(self):
        entry = EvidenceStateHistory.create(
            evidence_id="ev_abc",
            from_state=EVIDENCE_STATE_DRAFT,
            to_state=EVIDENCE_STATE_PROCESSING,
            reason="User submitted", actor="user_1",
        )
        assert entry.history_id.startswith("evhist_")
        assert entry.to_state == EVIDENCE_STATE_PROCESSING
        assert entry.reason == "User submitted"
        assert entry.actor == "user_1"
        assert entry.occurred_at

    def test_history_roundtrip(self):
        entry = EvidenceStateHistory.create(
            evidence_id="ev_abc",
            from_state=EVIDENCE_STATE_NEEDS_REVIEW,
            to_state=EVIDENCE_STATE_VERIFIED,
            reason="All data verified", actor="reviewer_1",
        )
        restored = EvidenceStateHistory.from_dict(entry.to_dict())
        assert restored.history_id == entry.history_id
        assert restored.to_state == entry.to_state
        assert restored.reason == entry.reason
