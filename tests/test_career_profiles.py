import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from backend.domain.models import (
    CAREER_PROFILE_STATUS_NOT_STARTED,
    CAREER_PROFILE_STATUS_NEEDS_REVIEW,
    CareerProfile,
    UserRecord,
)


class CareerProfileModelTests(unittest.TestCase):
    def test_create_with_minimum_fields(self):
        profile = CareerProfile.create(
            user_id="user_abc",
            name="Product Management 2026",
        )
        self.assertEqual(profile.user_id, "user_abc")
        self.assertEqual(profile.name, "Product Management 2026")
        self.assertEqual(profile.status, CAREER_PROFILE_STATUS_NOT_STARTED)
        self.assertEqual(profile.preferred_language, "en")
        self.assertEqual(profile.description, "")
        self.assertEqual(profile.target_direction, "")
        self.assertTrue(profile.profile_id.startswith("prof_"))
        self.assertTrue(profile.created_at)
        self.assertTrue(profile.updated_at)

    def test_create_with_all_fields(self):
        profile = CareerProfile.create(
            user_id="user_abc",
            name="My Profile",
            description="Senior engineering roles in Fintech",
            preferred_language="de",
            target_direction="Engineering Manager",
        )
        self.assertEqual(profile.name, "My Profile")
        self.assertEqual(profile.description, "Senior engineering roles in Fintech")
        self.assertEqual(profile.preferred_language, "de")
        self.assertEqual(profile.target_direction, "Engineering Manager")
        self.assertEqual(profile.status, CAREER_PROFILE_STATUS_NOT_STARTED)

    def test_to_dict_and_from_dict_roundtrip(self):
        profile = CareerProfile.create(
            user_id="user_abc",
            name="Test Profile",
            preferred_language="fr",
            target_direction="Data Scientist",
        )
        profile.status = CAREER_PROFILE_STATUS_NEEDS_REVIEW
        payload = profile.to_dict()
        restored = CareerProfile.from_dict(payload)
        self.assertEqual(restored.profile_id, profile.profile_id)
        self.assertEqual(restored.name, profile.name)
        self.assertEqual(restored.status, CAREER_PROFILE_STATUS_NEEDS_REVIEW)
        self.assertEqual(restored.preferred_language, "fr")
        self.assertEqual(restored.target_direction, "Data Scientist")

    def test_from_dict_with_partial_payload(self):
        profile = CareerProfile.from_dict(
            {"profile_id": "prof_123", "user_id": "user_x", "name": "Minimal"}
        )
        self.assertEqual(profile.profile_id, "prof_123")
        self.assertEqual(profile.name, "Minimal")
        self.assertEqual(profile.status, CAREER_PROFILE_STATUS_NOT_STARTED)
        self.assertEqual(profile.preferred_language, "en")

    def test_default_status_is_not_started(self):
        profile = CareerProfile.create(user_id="u1", name="P1")
        self.assertEqual(profile.status, "not_started")
        self.assertIn(profile.status, {
            "not_started",
            "extracting_evidence",
            "needs_review",
            "ready_for_tailoring",
        })


if __name__ == "__main__":
    unittest.main()
