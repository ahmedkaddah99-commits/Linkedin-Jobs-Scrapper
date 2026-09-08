import base64
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from backend import create_backend


EXTENSION_ID = "a" * 32
EXTENSION_ORIGIN = f"chrome-extension://{EXTENSION_ID}"
VERIFIER = "v" * 43
CHALLENGE = base64.urlsafe_b64encode(
    hashlib.sha256(VERIFIER.encode("ascii")).digest()
).decode("ascii").rstrip("=")


class AssistedApplyTrackerConfirmationTests(unittest.TestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory(prefix="runr-aa-tracker-")
        self.addCleanup(temporary_directory.cleanup)
        environment = patch.dict(os.environ, {
            "DATABASE_BACKEND": "sqlite",
            "RUNR_ENV": "test",
            "TURSO_DATABASE_URL": "",
            "TURSO_AUTH_TOKEN": "",
            "OBJECT_STORAGE_BACKEND": "local",
            "OBJECT_STORAGE_LOCAL_ROOT": str(Path(temporary_directory.name) / "objects"),
            "RUNR_INTERNAL_OBJECT_STORAGE_LOCAL_ROOT": "",
        }, clear=False)
        environment.start()
        self.addCleanup(environment.stop)
        self.app = create_backend(Path(temporary_directory.name), storage_backend="sqlite")

    def connected_user(self, suffix: str):
        user = self.app.upsert_user({"email": f"tracker-{suffix}@example.com"})
        request = self.app.create_assisted_apply_connection_request(
            extension_origin=EXTENSION_ORIGIN,
            state=suffix[0] * 32,
            challenge=CHALLENGE,
            installation_id=suffix[0] * 32,
            version="1.0.0",
        )
        completion_url = self.app.authorize_assisted_apply_connection(
            user_id=user.user_id, request_id=request.request_id,
        )
        code = parse_qs(urlparse(completion_url).query)["code"][0]
        _connection, session = self.app.exchange_assisted_apply_authorization(
            extension_origin=EXTENSION_ORIGIN,
            request_id=request.request_id,
            code=code,
            verifier=VERIFIER,
        )
        return user, session

    def bound_package(self, user_id: str):
        package = self.app.create_application_package(
            user_id=user_id,
            job={
                "job_id": "job-aa14",
                "title": "Engineer",
                "company": "Example",
                "portal": "greenhouse",
                "url": "https://boards.greenhouse.io/example/jobs/1",
                "location": "Berlin",
            },
            answers=[{
                "field_intent": "candidate.email",
                "proposed_value": "private-answer@example.com",
                "source": "profile_verified",
                "sensitivity": "standard",
                "scope": "global",
                "confidence": 1,
                "requires_review": False,
            }],
            documents=[{
                "document_id": "cv-fixed-v7",
                "document_version": 7,
                "document_kind": "cv",
                "asset_id": "asset-cv",
                "object_key": f"users/{user_id}/cv.pdf",
                "mime_type": "application/pdf",
                "file_name": "Private Candidate Name.pdf",
                "sha256_hex": "a" * 64,
            }],
        )
        launched = self.app.launch_application_package(user_id=user_id, package_id=package.package_id)
        self.app.bind_application_package(
            binding_id=launched.launch_tab_binding_id,
            extension_origin=EXTENSION_ORIGIN,
        )
        return package

    def respond(self, package, session, decision="confirmed", evidence="success_banner"):
        return self.app.respond_to_assisted_apply_outcome(
            package_id=package.package_id,
            package_version=package.version,
            adapter="greenhouse",
            adapter_version="1.0.0",
            evidence_category=evidence,
            decision=decision,
            uploaded_documents=[{"document_id": "cv-fixed-v7", "document_version": 7}],
            raw_session=session,
            extension_origin=EXTENSION_ORIGIN,
        )

    def test_confirmation_is_owned_idempotent_and_visible_as_one_tracker_record(self):
        owner, owner_session = self.connected_user("owner")
        _other, other_session = self.connected_user("other")
        package = self.bound_package(owner.user_id)

        with self.assertRaises(PermissionError):
            self.respond(package, other_session)

        first = self.respond(package, owner_session)
        second = self.respond(package, owner_session)
        revised_package = self.bound_package(owner.user_id)
        revised = self.respond(revised_package, owner_session)
        self.assertTrue(first["created"])
        self.assertFalse(first["duplicate"])
        self.assertFalse(second["created"])
        self.assertTrue(second["duplicate"])
        self.assertTrue(revised["duplicate"])
        self.assertEqual(first["trackerRecordId"], second["trackerRecordId"])
        self.assertEqual(first["trackerRecordId"], revised["trackerRecordId"])

        refreshed = self.app.get_user(owner.user_id)
        records = refreshed.metadata["external_tracker_applications"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["source"], "assisted_apply")
        self.assertEqual(records[0]["assisted_apply"]["job_id"], "job-aa14")
        self.assertEqual(records[0]["assisted_apply"]["package_version"], package.version)
        self.assertEqual(
            records[0]["assisted_apply"]["document_versions"],
            [{"document_id": "cv-fixed-v7", "document_version": 7}],
        )

        with self.app._assisted_apply_package_service._store.connection() as connection:
            stored = connection.execute("SELECT * FROM assisted_apply_tracker_records").fetchall()
            events = connection.execute("SELECT * FROM assisted_apply_submission_events").fetchall()
        self.assertEqual(len(stored), 1)
        self.assertEqual(json.loads(stored[0]["document_versions_json"])[0]["document_version"], 7)
        self.assertEqual([row["event_type"] for row in events], [
            "possible_success", "user_confirmed", "possible_success", "user_confirmed",
            "possible_success", "user_confirmed",
        ])
        self.assertNotIn("private-answer@example.com", str([dict(row) for row in events]))
        self.assertNotIn("Private Candidate Name.pdf", str([dict(row) for row in events]))

    def test_declined_ambiguous_and_failed_attempts_create_no_tracker_record(self):
        owner, session = self.connected_user("decline")
        package = self.bound_package(owner.user_id)
        declined = self.respond(package, session, decision="declined")
        self.assertEqual(declined, {"decision": "declined", "created": False, "duplicate": False})
        with self.assertRaisesRegex(ValueError, "evidence"):
            self.respond(package, session, evidence="ambiguous")
        with self.assertRaisesRegex(ValueError, "Uploaded document"):
            self.app.respond_to_assisted_apply_outcome(
                package_id=package.package_id,
                package_version=package.version,
                adapter="greenhouse",
                adapter_version="1.0.0",
                evidence_category="success_banner",
                decision="confirmed",
                uploaded_documents=[{"document_id": "unknown", "document_version": 1}],
                raw_session=session,
                extension_origin=EXTENSION_ORIGIN,
            )
        with self.app._assisted_apply_package_service._store.connection() as connection:
            count = connection.execute("SELECT COUNT(*) FROM assisted_apply_tracker_records").fetchone()[0]
        self.assertEqual(count, 0)
        self.assertNotIn("external_tracker_applications", self.app.get_user(owner.user_id).metadata)


if __name__ == "__main__":
    unittest.main()
