"""Tests for Career Profile Evidence domain model and service (CP-010)."""

import pytest

from backend.capabilities.career_profile_evidence.service import (
    count_evidence_by_status,
    create_evidence,
    defer_evidence,
    edit_evidence,
    get_evidence,
    get_verified_evidence,
    list_evidence,
    reject_evidence,
    verify_evidence,
)
from backend.domain.career_profile_evidence import (
    EVIDENCE_STATUS_DEFERRED,
    EVIDENCE_STATUS_PENDING,
    EVIDENCE_STATUS_REJECTED,
    EVIDENCE_STATUS_VERIFIED,
    CareerProfileEvidence,
)


class TestCareerProfileEvidenceModel:

    def test_create_evidence_defaults_to_pending(self):
        ev = CareerProfileEvidence.create(
            profile_id="prof_1", source_id="src_1",
            extracted_text="5 years at Acme Corp",
            extraction_reason="Experience extracted from CV",
            extraction_confidence=0.95,
        )
        assert ev.status == EVIDENCE_STATUS_PENDING
        assert ev.evidence_id.startswith("ev_")
        assert ev.extracted_text == "5 years at Acme Corp"
        assert ev.edited_text == ""
        assert ev.effective_text == "5 years at Acme Corp"
        assert ev.is_usable is False
        assert ev.is_rejected is False
        assert ev.is_deferred is False

    def test_verify_marks_evidence_as_usable(self):
        ev = CareerProfileEvidence.create(profile_id="p1", source_id="s1")
        assert ev.is_usable is False
        ev.verify()
        assert ev.status == EVIDENCE_STATUS_VERIFIED
        assert ev.is_usable is True

    def test_reject_preserves_original_text(self):
        ev = CareerProfileEvidence.create(
            profile_id="p1", source_id="s1",
            extracted_text="Important achievement",
        )
        ev.reject()
        assert ev.status == EVIDENCE_STATUS_REJECTED
        assert ev.is_rejected is True
        assert ev.is_usable is False
        assert ev.extracted_text == "Important achievement"

    def test_defer_sets_deferred_status(self):
        ev = CareerProfileEvidence.create(profile_id="p1", source_id="s1")
        ev.defer()
        assert ev.status == EVIDENCE_STATUS_DEFERRED
        assert ev.is_deferred is True

    def test_edit_preserves_original_and_records_history(self):
        ev = CareerProfileEvidence.create(
            profile_id="p1", source_id="s1",
            extracted_text="Worked at Acme",
        )
        ev.edit("Worked at Acme Corp (2019-2024)")
        assert ev.is_edited is True
        assert ev.edited_text == "Worked at Acme Corp (2019-2024)"
        assert ev.extracted_text == "Worked at Acme"
        assert ev.effective_text == "Worked at Acme Corp (2019-2024)"
        assert len(ev.edit_history) == 1
        assert ev.edit_history[0]["changed_by"] == "user"
        assert ev.edit_history[0]["previous_text"] == "Worked at Acme"

    def test_edit_resets_status_to_pending_unless_verified_or_rejected(self):
        ev = CareerProfileEvidence.create(profile_id="p1", source_id="s1")
        ev.verify()
        ev.edit("Updated")
        assert ev.status == EVIDENCE_STATUS_VERIFIED

        ev2 = CareerProfileEvidence.create(profile_id="p1", source_id="s2")
        ev2.reject()
        ev2.edit("Updated")
        assert ev2.status == EVIDENCE_STATUS_REJECTED

        ev3 = CareerProfileEvidence.create(profile_id="p1", source_id="s3")
        ev3.edit("Updated")
        assert ev3.status == EVIDENCE_STATUS_PENDING

    def test_to_dict_includes_computed_properties(self):
        ev = CareerProfileEvidence.create(
            profile_id="p1", source_id="s1",
            source_name="My CV.pdf", field_type="experience",
            extracted_text="Acme Corp", extraction_reason="job title",
            extraction_confidence=0.88,
        )
        d = ev.to_dict()
        assert d["status"] == "pending"
        assert d["is_edited"] is False
        assert d["is_usable"] is False
        assert d["effective_text"] == "Acme Corp"
        assert d["extraction_confidence"] == 0.88
        assert d["source_name"] == "My CV.pdf"
        assert d["extraction_reason"] == "job title"

    def test_from_dict_roundtrips(self):
        ev = CareerProfileEvidence.create(
            profile_id="p1", source_id="s1",
            field_type="skill", extracted_text="Python",
        )
        ev.edit("Python (expert)")
        ev.verify()
        d = ev.to_dict()
        restored = CareerProfileEvidence.from_dict(d)
        assert restored.evidence_id == ev.evidence_id
        assert restored.status == EVIDENCE_STATUS_VERIFIED
        assert restored.is_edited is True
        assert restored.edited_text == "Python (expert)"
        assert len(restored.edit_history) == 1


class TestCareerProfileEvidenceService:

    def test_create_and_get(self):
        ev = create_evidence(profile_id="prof_a", source_id="src_1", extracted_text="Test")
        retrieved = get_evidence("prof_a", ev.evidence_id)
        assert retrieved is not None
        assert retrieved.evidence_id == ev.evidence_id

    def test_get_missing_returns_none(self):
        assert get_evidence("nope", "ev_nope") is None

    def test_list_filters_by_profile(self):
        create_evidence(profile_id="prof_a", source_id="s1")
        create_evidence(profile_id="prof_a", source_id="s2")
        create_evidence(profile_id="prof_b", source_id="s3")
        assert len(list_evidence("prof_a")) == 2
        assert len(list_evidence("prof_b")) == 1

    def test_list_filters_by_status(self):
        e1 = create_evidence(profile_id="pf", source_id="s1")
        e2 = create_evidence(profile_id="pf", source_id="s2")
        verify_evidence("pf", e1.evidence_id)
        reject_evidence("pf", e2.evidence_id)
        assert len(list_evidence("pf", status=EVIDENCE_STATUS_VERIFIED)) == 1
        assert len(list_evidence("pf", status=EVIDENCE_STATUS_REJECTED)) == 1
        assert len(list_evidence("pf", status=EVIDENCE_STATUS_PENDING)) == 0

    def test_verify_reject_defer_work(self):
        ev = create_evidence(profile_id="pf", source_id="s1")
        verify_evidence("pf", ev.evidence_id)
        assert get_evidence("pf", ev.evidence_id).is_usable is True

        ev2 = create_evidence(profile_id="pf", source_id="s2")
        reject_evidence("pf", ev2.evidence_id)
        assert get_evidence("pf", ev2.evidence_id).is_rejected is True

        ev3 = create_evidence(profile_id="pf", source_id="s3")
        defer_evidence("pf", ev3.evidence_id)
        assert get_evidence("pf", ev3.evidence_id).is_deferred is True

    def test_edit_updates_text(self):
        ev = create_evidence(profile_id="pf", source_id="s1", extracted_text="Old")
        edit_evidence("pf", ev.evidence_id, "New text")
        updated = get_evidence("pf", ev.evidence_id)
        assert updated.effective_text == "New text"
        assert updated.is_edited is True

    def test_get_verified_only(self):
        e1 = create_evidence(profile_id="pf", source_id="s1")
        e2 = create_evidence(profile_id="pf", source_id="s2")
        create_evidence(profile_id="pf", source_id="s3")
        verify_evidence("pf", e1.evidence_id)
        verify_evidence("pf", e2.evidence_id)
        verified = get_verified_evidence("pf")
        assert len(verified) == 2

    def test_count_by_status(self):
        e1 = create_evidence(profile_id="pf", source_id="s1")
        e2 = create_evidence(profile_id="pf", source_id="s2")
        e3 = create_evidence(profile_id="pf", source_id="s3")
        verify_evidence("pf", e1.evidence_id)
        reject_evidence("pf", e2.evidence_id)
        defer_evidence("pf", e3.evidence_id)
        counts = count_evidence_by_status("pf")
        assert counts[EVIDENCE_STATUS_VERIFIED] == 1
        assert counts[EVIDENCE_STATUS_REJECTED] == 1
        assert counts[EVIDENCE_STATUS_DEFERRED] == 1
        assert counts[EVIDENCE_STATUS_PENDING] == 0

    def test_actions_return_none_for_missing(self):
        assert verify_evidence("pf", "nope") is None
        assert reject_evidence("pf", "nope") is None
        assert defer_evidence("pf", "nope") is None
        assert edit_evidence("pf", "nope", "text") is None
