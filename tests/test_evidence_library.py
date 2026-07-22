import unittest

from backend.domain.models import (
    EVIDENCE_SOURCE_KIND_MANUAL,
    EVIDENCE_TYPE_ACHIEVEMENT,
    EVIDENCE_TYPE_LEADERSHIP,
    EVIDENCE_TYPE_PROJECT,
    EVIDENCE_VERIFICATION_STATE_UNVERIFIED,
    EVIDENCE_VERIFICATION_STATE_VERIFIED,
    EvidenceRecord,
    CareerProfile,
)
from backend.evidence_library.service import (
    create_evidence,
    delete_evidence,
    get_evidence,
    list_evidence,
    update_evidence,
)


class EvidenceRecordModelTests(unittest.TestCase):
    def test_create_with_minimum_fields(self):
        record = EvidenceRecord.create(
            experience_id="exp_abc",
            profile_id="prof_xyz",
        )
        self.assertEqual(record.experience_id, "exp_abc")
        self.assertEqual(record.profile_id, "prof_xyz")
        self.assertTrue(record.evidence_id.startswith("evid_"))
        self.assertEqual(record.source, EVIDENCE_SOURCE_KIND_MANUAL)
        self.assertEqual(record.verification_state, EVIDENCE_VERIFICATION_STATE_UNVERIFIED)
        self.assertEqual(record.evidence_type, EVIDENCE_TYPE_ACHIEVEMENT)
        self.assertEqual(record.action, "")
        self.assertEqual(record.why_it_mattered, "")
        self.assertEqual(record.tools, "")
        self.assertEqual(record.stakeholders, "")
        self.assertEqual(record.challenge, "")
        self.assertEqual(record.result, "")
        self.assertEqual(record.metric, "")

    def test_create_with_all_fields(self):
        record = EvidenceRecord.create(
            experience_id="exp_abc",
            profile_id="prof_xyz",
            action="Led a cross-functional team",
            why_it_mattered="Reduced time-to-market by 30%",
            tools="Python, Jira",
            stakeholders="VP Engineering, Product Managers",
            challenge="Legacy system with no test coverage",
            result="Delivered platform migration on time",
            metric="30% reduction in deployment time",
            source="manual",
            verification_state=EVIDENCE_VERIFICATION_STATE_VERIFIED,
            evidence_type=EVIDENCE_TYPE_LEADERSHIP,
            sort_order=1,
        )
        self.assertEqual(record.action, "Led a cross-functional team")
        self.assertEqual(record.why_it_mattered, "Reduced time-to-market by 30%")
        self.assertEqual(record.tools, "Python, Jira")
        self.assertEqual(record.stakeholders, "VP Engineering, Product Managers")
        self.assertEqual(record.challenge, "Legacy system with no test coverage")
        self.assertEqual(record.result, "Delivered platform migration on time")
        self.assertEqual(record.metric, "30% reduction in deployment time")
        self.assertEqual(record.verification_state, EVIDENCE_VERIFICATION_STATE_VERIFIED)
        self.assertEqual(record.evidence_type, EVIDENCE_TYPE_LEADERSHIP)
        self.assertEqual(record.sort_order, 1)

    def test_to_dict_and_from_dict_roundtrip(self):
        record = EvidenceRecord.create(
            experience_id="exp_abc",
            profile_id="prof_xyz",
            action="Built CI/CD pipeline",
            tools="GitHub Actions, Docker",
            evidence_type=EVIDENCE_TYPE_PROJECT,
        )
        payload = record.to_dict()
        restored = EvidenceRecord.from_dict(payload)
        self.assertEqual(restored.evidence_id, record.evidence_id)
        self.assertEqual(restored.experience_id, record.experience_id)
        self.assertEqual(restored.action, "Built CI/CD pipeline")
        self.assertEqual(restored.tools, "GitHub Actions, Docker")
        self.assertEqual(restored.evidence_type, EVIDENCE_TYPE_PROJECT)

    def test_default_verification_state_is_unverified(self):
        record = EvidenceRecord.create(experience_id="exp_x", profile_id="prof_x")
        self.assertEqual(record.verification_state, "unverified")

    def test_source_asset_ids_are_stripped(self):
        record = EvidenceRecord.create(
            experience_id="exp_x",
            profile_id="prof_x",
            source_asset_ids=["  asset_1  ", "", "asset_2"],
        )
        self.assertEqual(record.source_asset_ids, ["asset_1", "asset_2"])

    def test_fields_are_stripped(self):
        record = EvidenceRecord.create(
            experience_id="  exp_abc  ",
            profile_id="  prof_xyz  ",
            action="  Did important work  ",
            metric="  50%  ",
        )
        self.assertEqual(record.experience_id, "exp_abc")
        self.assertEqual(record.profile_id, "prof_xyz")
        self.assertEqual(record.action, "Did important work")
        self.assertEqual(record.metric, "50%")




class EvidenceLibraryServiceTests(unittest.TestCase):
    def setUp(self):
        self.profile = CareerProfile.create(
            user_id="user_test",
            name="Test Profile",
        )

    def _add_experience(self, exp_id="exp_1"):
        metadata = dict(self.profile.metadata or {})
        raw = metadata.get("work_experiences", [])
        raw.append({
            "experience_id": exp_id,
            "profile_id": self.profile.profile_id,
            "employer": "ACME",
            "job_title": "Engineer",
        })
        metadata["work_experiences"] = raw
        self.profile.metadata = metadata

    def test_create_and_list_evidence(self):
        self._add_experience("exp_1")
        create_evidence(self.profile, {
            "experience_id": "exp_1",
            "action": "Refactored auth module",
            "evidence_type": EVIDENCE_TYPE_PROJECT,
        })
        records = list_evidence(self.profile, experience_id="exp_1")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].action, "Refactored auth module")

    def test_list_with_no_evidence_returns_empty(self):
        self._add_experience("exp_1")
        records = list_evidence(self.profile, experience_id="exp_1")
        self.assertEqual(records, [])

    def test_create_requires_experience_id(self):
        with self.assertRaises(ValueError):
            create_evidence(self.profile, {})

    def test_get_evidence_by_id(self):
        self._add_experience("exp_1")
        created = create_evidence(self.profile, {
            "experience_id": "exp_1",
            "action": "Test action",
        })
        found = get_evidence(self.profile, created.evidence_id)
        self.assertIsNotNone(found)
        self.assertEqual(found.action, "Test action")

    def test_get_missing_evidence_returns_none(self):
        self._add_experience("exp_1")
        result = get_evidence(self.profile, "nonexistent")
        self.assertIsNone(result)

    def test_update_evidence(self):
        self._add_experience("exp_1")
        created = create_evidence(self.profile, {
            "experience_id": "exp_1",
            "action": "Original",
            "verification_state": EVIDENCE_VERIFICATION_STATE_UNVERIFIED,
        })
        updated = update_evidence(self.profile, created.evidence_id, {
            "action": "Updated action",
            "verification_state": EVIDENCE_VERIFICATION_STATE_VERIFIED,
        })
        self.assertEqual(updated.action, "Updated action")
        self.assertEqual(updated.verification_state, EVIDENCE_VERIFICATION_STATE_VERIFIED)

    def test_update_nonexistent_raises_key_error(self):
        with self.assertRaises(KeyError):
            update_evidence(self.profile, "nonexistent", {"action": "x"})

    def test_delete_evidence(self):


    def test_delete_nonexistent_raises_key_error(self):
        with self.assertRaises(KeyError):
            delete_evidence(self.profile, "nonexistent")

    def test_filter_by_evidence_type(self):
        self._add_experience("exp_1")
        create_evidence(self.profile, {
            "experience_id": "exp_1",
            "action": "Achievement 1",
            "evidence_type": EVIDENCE_TYPE_ACHIEVEMENT,
        })
        create_evidence(self.profile, {
            "experience_id": "exp_1",
            "action": "Project 1",
            "evidence_type": EVIDENCE_TYPE_PROJECT,
        })
        achievements = list_evidence(
            self.profile, experience_id="exp_1",
            evidence_type=EVIDENCE_TYPE_ACHIEVEMENT,
        )
        self.assertEqual(len(achievements), 1)
        self.assertEqual(achievements[0].action, "Achievement 1")

    def test_filter_by_verification_state(self):
        self._add_experience("exp_1")
        create_evidence(self.profile, {
            "experience_id": "exp_1",
            "action": "Unverified",
            "verification_state": EVIDENCE_VERIFICATION_STATE_UNVERIFIED,
        })
        create_evidence(self.profile, {
            "experience_id": "exp_1",
            "action": "Verified",
            "verification_state": EVIDENCE_VERIFICATION_STATE_VERIFIED,
        })
        verified = list_evidence(
            self.profile, experience_id="exp_1",
            verification_state=EVIDENCE_VERIFICATION_STATE_VERIFIED,
        )
        self.assertEqual(len(verified), 1)
        self.assertEqual(verified[0].action, "Verified")

    def test_filter_by_source(self):
        self._add_experience("exp_1")
        create_evidence(self.profile, {
            "experience_id": "exp_1",
            "action": "Manually entered",
            "source": EVIDENCE_SOURCE_KIND_MANUAL,
        })
        manual_items = list_evidence(
            self.profile, experience_id="exp_1",
            source=EVIDENCE_SOURCE_KIND_MANUAL,
        )
        self.assertEqual(len(manual_items), 1)
        self.assertEqual(manual_items[0].action, "Manually entered")

    def test_multiple_evidence_items_under_same_experience(self):
        self._add_experience("exp_1")
        for i in range(5):
            create_evidence(self.profile, {
                "experience_id": "exp_1",
                "action": f"Action {i}",
            })
        records = list_evidence(self.profile, experience_id="exp_1")
        self.assertEqual(len(records), 5)

    def test_saves_to_profile_metadata(self):
        self._add_experience("exp_1")
        create_evidence(self.profile, {
            "experience_id": "exp_1",
            "action": "Metadata test",
        })
        self.assertIn("evidence_library", self.profile.metadata)
        raw = self.profile.metadata["evidence_library"]
        self.assertIsInstance(raw, list)
        self.assertEqual(len(raw), 1)
        self.assertEqual(raw[0]["action"], "Metadata test")


if __name__ == "__main__":
    unittest.main()

        self._add_experience("exp_1")
        created = create_evidence(self.profile, {
            "experience_id": "exp_1",
            "action": "To be deleted",
        })
        delete_evidence(self.profile, created.evidence_id)
        self.assertIsNone(get_evidence(self.profile, created.evidence_id))
