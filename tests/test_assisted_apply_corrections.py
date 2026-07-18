import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import create_backend
from backend.application.assisted_apply_correction_service import AssistedApplyCorrectionService
from backend.application.assisted_apply_package_service import ApplicationPackageStore


class AssistedApplyCorrectionTests(unittest.TestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory(prefix="runr-aa-corrections-")
        self.addCleanup(temporary_directory.cleanup)
        self.root = Path(temporary_directory.name)
        environment = patch.dict(os.environ, {
            "DATABASE_BACKEND": "sqlite",
            "RUNR_ENV": "test",
            "TURSO_DATABASE_URL": "",
            "TURSO_AUTH_TOKEN": "",
            "OBJECT_STORAGE_BACKEND": "local",
            "OBJECT_STORAGE_LOCAL_ROOT": str(self.root / "objects"),
            "RUNR_INTERNAL_OBJECT_STORAGE_LOCAL_ROOT": "",
        }, clear=False)
        environment.start()
        self.addCleanup(environment.stop)
        self.app = create_backend(self.root, storage_backend="sqlite")
        self.owner = self.app.upsert_user({"email": "owner@example.com", "display_name": "Owner"})
        self.other = self.app.upsert_user({"email": "other@example.com", "display_name": "Other"})
        self.store = ApplicationPackageStore(self.app.repositories)
        self.service = AssistedApplyCorrectionService(self.app.repositories)

    def create_package(self, *, company="Acme", title="Engineer", location="Germany", value="Old"):
        return self.app.create_application_package(
            user_id=self.owner.user_id,
            job={
                "job_id": f"job-{company}-{title}-{value}",
                "title": title,
                "company": company,
                "portal": "greenhouse",
                "location": location,
            },
            answers=[{
                "field_intent": "preferred_name",
                "label": "Preferred name",
                "proposed_value": value,
                "source": "profile_verified",
                "sensitivity": "standard",
                "scope": "global",
                "confidence": 1,
                "requires_review": False,
            }],
        )

    def save(self, package, value, scope, *, user_id=None):
        return self.service.save_correction(
            user_id=user_id or self.owner.user_id,
            package=package,
            field_intent="preferred_name",
            corrected_value=value,
            scope=scope,
        )

    def test_application_and_do_not_save_are_never_persisted(self):
        package = self.create_package()
        self.assertFalse(self.save(package, "Application", "application")["persisted"])
        self.assertFalse(self.save(package, "Transient", "do_not_save")["persisted"])
        with self.service.store.connection() as connection:
            count = connection.execute("SELECT COUNT(*) FROM assisted_apply_corrections").fetchone()[0]
        self.assertEqual(count, 0)

    def test_durable_correction_is_owned_audited_and_matches_only_future_packages(self):
        original = self.create_package()
        result = self.save(original, "Corrected", "company")
        self.assertTrue(result["persisted"])
        self.assertEqual(self.store.get(original.package_id).answers[0].proposed_value, "Old")

        matching = self.create_package(company="Acme", value="Profile value")
        nonmatching = self.create_package(company="Other Co", value="Other profile value")
        self.assertEqual(matching.answers[0].proposed_value, "Corrected")
        self.assertEqual(matching.answers[0].source, "scoped_preference")
        self.assertIn("explicit_user_correction:company", matching.answers[0].reasons)
        self.assertEqual(nonmatching.answers[0].proposed_value, "Other profile value")
        self.assertEqual(len(self.service.store.audit_events(self.owner.user_id)), 1)
        self.assertEqual(self.service.store.audit_events(self.other.user_id), [])

    def test_authorization_precedence_conflict_and_freshness(self):
        package = self.create_package(title="Senior Engineer", location="Berlin, Germany")
        with self.assertRaises(PermissionError):
            self.save(package, "Stolen", "global", user_id=self.other.user_id)

        self.save(package, "Global", "global")
        self.save(package, "Country", "country")
        self.save(package, "Role", "role")
        self.save(package, "Company first", "company")
        self.save(package, "Company newest", "company")
        matched = self.create_package(value="Profile")
        self.assertEqual(matched.answers[0].proposed_value, "Company newest")
        role_match = self.create_package(company="Different", title="Junior Engineer", location="Munich, Germany", value="Profile")
        country_match = self.create_package(company="Different", title="Accountant", location="Munich, Germany", value="Profile")
        global_match = self.create_package(company="Different", title="Accountant", location="Paris, France", value="Profile")
        self.assertEqual(role_match.answers[0].proposed_value, "Role")
        self.assertEqual(country_match.answers[0].proposed_value, "Country")
        self.assertEqual(global_match.answers[0].proposed_value, "Global")

        with self.service.store.connection() as connection:
            connection.execute(
                "UPDATE assisted_apply_corrections SET expires_at = '2000-01-01T00:00:00+00:00' WHERE user_id = ?",
                (self.owner.user_id,),
            )
        fresh_package = self.create_package(value="Fresh profile")
        self.assertEqual(fresh_package.answers[0].proposed_value, "Fresh profile")
        events = self.service.store.audit_events(self.owner.user_id)
        self.assertEqual(
            [event["event_type"] for event in events],
            ["created", "created", "created", "created", "superseded", "created"],
        )

    def test_scope_requires_package_context_and_known_field(self):
        package = self.create_package(company="", location="")
        with self.assertRaisesRegex(ValueError, "no value"):
            self.save(package, "No company", "company")
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.service.save_correction(
                user_id=self.owner.user_id,
                package=package,
                field_intent="unknown",
                corrected_value="value",
                scope="global",
            )
