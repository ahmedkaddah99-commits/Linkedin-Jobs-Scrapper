import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from backend.domain.models import (
    CAREER_PROFILE_STATUS_NOT_STARTED,
    CAREER_PROFILE_STATUS_NEEDS_REVIEW,
    CAREER_PROFILE_STATUS_UNBOUND,
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
            "unbound",
        })

    def test_unbound_status_is_valid(self):
        self.assertEqual(CAREER_PROFILE_STATUS_UNBOUND, "unbound")
        profile = CareerProfile.create(user_id="u1", name="Test")
        profile.status = CAREER_PROFILE_STATUS_UNBOUND
        self.assertEqual(profile.status, "unbound")
        payload = profile.to_dict()
        self.assertEqual(payload["status"], "unbound")
        restored = CareerProfile.from_dict(payload)
        self.assertEqual(restored.status, "unbound")

    def test_unbound_profile_has_cleared_bound_workspace(self):
        profile = CareerProfile.create(
            user_id="u1",
            name="Test",
            bound_workspace_id="ws_abc",
        )
        self.assertEqual(profile.bound_workspace_id, "ws_abc")
        # Simulate unbind on workspace deletion
        profile.bound_workspace_id = ""
        profile.status = CAREER_PROFILE_STATUS_UNBOUND
        profile.metadata = dict(profile.metadata)
        profile.metadata["unbound_reason"] = "Workspace 'ws_abc' was deleted."
        profile.metadata["unbound_at"] = profile.updated_at
        profile.metadata["unbound_former_workspace_id"] = "ws_abc"
        self.assertEqual(profile.bound_workspace_id, "")
        self.assertEqual(profile.status, CAREER_PROFILE_STATUS_UNBOUND)
        self.assertIn("unbound_reason", profile.metadata)
        self.assertIn("unbound_former_workspace_id", profile.metadata)
        self.assertEqual(profile.metadata["unbound_former_workspace_id"], "ws_abc")

if __name__ == "__main__":
    unittest.main()
