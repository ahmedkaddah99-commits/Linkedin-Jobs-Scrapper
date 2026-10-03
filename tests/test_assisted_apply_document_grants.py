import base64
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from backend import create_backend


EXTENSION_ID = "a" * 32
EXTENSION_ORIGIN = f"chrome-extension://{EXTENSION_ID}"
VERIFIER = "v" * 43
CHALLENGE = base64.urlsafe_b64encode(
    hashlib.sha256(VERIFIER.encode("ascii")).digest()
).decode("ascii").rstrip("=")
PDF_BYTES = b"%PDF-1.4\n% Runr immutable CV fixture\n%%EOF\n"
DOCX_BYTES = b"PK\x03\x04 Runr immutable DOCX fixture"


class AssistedApplyDocumentGrantTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory(prefix="runr-aa-doc-grants-")
        self.addCleanup(self.temporary_directory.cleanup)
        environment = patch.dict(
            os.environ,
            {
                "DATABASE_BACKEND": "sqlite",
                "RUNR_ENV": "test",
                "TURSO_DATABASE_URL": "",
                "TURSO_AUTH_TOKEN": "",
                "OBJECT_STORAGE_BACKEND": "local",
                "OBJECT_STORAGE_LOCAL_ROOT": str(Path(self.temporary_directory.name) / "objects"),
                "RUNR_INTERNAL_OBJECT_STORAGE_LOCAL_ROOT": "",
            },
            clear=False,
        )
        environment.start()
        self.addCleanup(environment.stop)
        self.app = create_backend(Path(self.temporary_directory.name), storage_backend="sqlite")

    def _connected_user(self, suffix: str):
        user = self.app.upsert_user(
            {"email": f"aa-doc-{suffix}@example.com", "display_name": f"Candidate {suffix}"}
        )
        request = self.app.create_assisted_apply_connection_request(
            extension_origin=EXTENSION_ORIGIN,
            state=(suffix[0] if suffix else "s") * 32,
            challenge=CHALLENGE,
            installation_id=(suffix[0] if suffix else "i") * 32,
            version="1.0.0",
        )
        completion_url = self.app.authorize_assisted_apply_connection(
            user_id=user.user_id,
            request_id=request.request_id,
        )
        code = parse_qs(urlparse(completion_url).query)["code"][0]
        connection, session = self.app.exchange_assisted_apply_authorization(
            extension_origin=EXTENSION_ORIGIN,
            request_id=request.request_id,
            code=code,
            verifier=VERIFIER,
        )
        return user, connection, session

    def _bound_package(self, user_id: str, documents=None, portal="greenhouse"):
        object_key = f"users/{user_id}/workspace_cv/asset_cv/candidate.pdf"
        if documents is None:
            self.app.object_storage.put(object_key, PDF_BYTES, content_type="application/pdf")
            documents = [
                {
                    "document_id": "cv_version_7",
                    "document_version": 7,
                    "document_kind": "cv",
                    "asset_id": "asset_cv",
                    "object_key": object_key,
                    "mime_type": "application/pdf",
                    "file_name": "Candidate CV.pdf",
                    "sha256_hex": hashlib.sha256(PDF_BYTES).hexdigest(),
                }
            ]
        package = self.app.create_application_package(
            user_id=user_id,
            job={
                "job_id": "job_greenhouse_1",
                "title": "Engineer",
                "company": "Example",
                "portal": portal,
            },
            documents=documents,
        )
        launched = self.app.launch_application_package(user_id=user_id, package_id=package.package_id)
        self.app.bind_application_package(
            binding_id=launched.launch_tab_binding_id,
            extension_origin=EXTENSION_ORIGIN,
        )
        return package, object_key

    def test_grants_support_selected_cover_letters_and_supporting_documents_only(self):
        owner, _connection, session = self._connected_user("roles")
        selected = [
            ("cover", "cover_letter", "cover.pdf", "application/pdf", PDF_BYTES),
            (
                "supporting",
                "supporting_document",
                "certificate.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                DOCX_BYTES,
            ),
        ]
        documents = []
        for document_id, kind, file_name, mime_type, content in selected:
            object_key = f"users/{owner.user_id}/assisted-apply/{document_id}/{file_name}"
            self.app.object_storage.put(object_key, content, content_type=mime_type)
            documents.append(
                {
                    "document_id": document_id,
                    "document_version": 2,
                    "document_kind": kind,
                    "asset_id": f"asset_{document_id}",
                    "object_key": object_key,
                    "mime_type": mime_type,
                    "file_name": file_name,
                    "sha256_hex": hashlib.sha256(content).hexdigest(),
                }
            )
        package, _ = self._bound_package(owner.user_id, documents=documents, portal="lever")

        for document_id, kind, _file_name, mime_type, content in selected:
            grant = self.app.create_assisted_apply_document_grant(
                package_id=package.package_id,
                document_id=document_id,
                raw_session=session,
                extension_origin=EXTENSION_ORIGIN,
            )
            self.assertEqual(grant["file"]["documentKind"], kind)
            downloaded, metadata = self.app.consume_assisted_apply_document_grant(
                raw_grant=grant["grantToken"],
                raw_session=session,
                extension_origin=EXTENSION_ORIGIN,
            )
            self.assertEqual(downloaded, content)
            self.assertEqual(metadata["mimeType"], mime_type)

        with self.assertRaises(ValueError):
            self.app.create_assisted_apply_document_grant(
                package_id=package.package_id,
                document_id="not-selected",
                raw_session=session,
                extension_origin=EXTENSION_ORIGIN,
            )

    def test_grant_is_hash_only_session_scoped_one_time_and_version_audited(self):
        owner, _owner_connection, owner_session = self._connected_user("owner")
        _other, _other_connection, other_session = self._connected_user("other")
        package, _object_key = self._bound_package(owner.user_id)

        grant = self.app.create_assisted_apply_document_grant(
            package_id=package.package_id,
            document_id="cv_version_7",
            raw_session=owner_session,
            extension_origin=EXTENSION_ORIGIN,
        )
        self.assertEqual(grant["file"]["documentVersion"], 7)
        self.assertEqual(grant["uploadFieldIntent"], "greenhouse.resume")
        self.assertEqual(grant["file"]["sha256Hex"], hashlib.sha256(PDF_BYTES).hexdigest())
        self.assertNotIn("url", str(grant).lower())

        with self.app._assisted_apply_package_service._store.connection() as connection:
            stored = connection.execute(
                "SELECT * FROM assisted_apply_document_grants"
            ).fetchone()
        self.assertNotIn(grant["grantToken"], str(dict(stored)))
        self.assertEqual(stored["document_id"], "cv_version_7")
        self.assertEqual(stored["document_version"], 7)

        with self.assertRaises(PermissionError):
            self.app.consume_assisted_apply_document_grant(
                raw_grant=grant["grantToken"],
                raw_session=other_session,
                extension_origin=EXTENSION_ORIGIN,
            )

        downloaded, metadata = self.app.consume_assisted_apply_document_grant(
            raw_grant=grant["grantToken"],
            raw_session=owner_session,
            extension_origin=EXTENSION_ORIGIN,
        )
        self.assertEqual(downloaded, PDF_BYTES)
        self.assertEqual(metadata["documentId"], "cv_version_7")
        with self.assertRaises(PermissionError):
            self.app.consume_assisted_apply_document_grant(
                raw_grant=grant["grantToken"],
                raw_session=owner_session,
                extension_origin=EXTENSION_ORIGIN,
            )

    def test_expiry_and_post_grant_content_mismatch_are_rejected(self):
        owner, _connection, session = self._connected_user("expiry")
        package, object_key = self._bound_package(owner.user_id)
        grant = self.app.create_assisted_apply_document_grant(
            package_id=package.package_id,
            document_id="cv_version_7",
            raw_session=session,
            extension_origin=EXTENSION_ORIGIN,
        )
        with self.app._assisted_apply_package_service._store.connection() as connection:
            connection.execute(
                "UPDATE assisted_apply_document_grants SET expires_at='2000-01-01T00:00:00+00:00'"
            )
        with self.assertRaises(PermissionError):
            self.app.consume_assisted_apply_document_grant(
                raw_grant=grant["grantToken"],
                raw_session=session,
                extension_origin=EXTENSION_ORIGIN,
            )

        second = self.app.create_assisted_apply_document_grant(
            package_id=package.package_id,
            document_id="cv_version_7",
            raw_session=session,
            extension_origin=EXTENSION_ORIGIN,
        )
        self.app.object_storage.put(object_key, b"%PDF-mutated", content_type="application/pdf")
        with self.assertRaises(ValueError):
            self.app.consume_assisted_apply_document_grant(
                raw_grant=second["grantToken"],
                raw_session=session,
                extension_origin=EXTENSION_ORIGIN,
            )
        with self.app._assisted_apply_package_service._store.connection() as connection:
            rejected = connection.execute(
                "SELECT status, failure_reason FROM assisted_apply_document_grants WHERE status='rejected'"
            ).fetchone()
        self.assertEqual(
            (rejected["status"], rejected["failure_reason"]),
            ("rejected", "content_mismatch"),
        )

    def test_grant_rejects_unsupported_roles_mime_pairs_and_duplicate_cover_letters(self):
        owner, _connection, session = self._connected_user("reject")
        invalid_documents = [
            {
                "document_id": "certificate_unselected_role",
                "document_version": 1,
                "document_kind": "certificate",
                "asset_id": "asset_certificate",
                "object_key": f"users/{owner.user_id}/certificate.pdf",
                "mime_type": "application/pdf",
                "file_name": "Certificate.pdf",
            },
            {
                "document_id": "cover_wrong_mime",
                "document_version": 1,
                "document_kind": "cover_letter",
                "asset_id": "asset_cover",
                "object_key": f"users/{owner.user_id}/cover.docx",
                "mime_type": "application/pdf",
                "file_name": "Cover.docx",
            },
        ]
        for item in invalid_documents:
            self.app.object_storage.put(item["object_key"], PDF_BYTES, content_type=item["mime_type"])
        package, _ = self._bound_package(owner.user_id, documents=invalid_documents)
        for document_id in ("certificate_unselected_role", "cover_wrong_mime"):
            with self.assertRaises(ValueError):
                self.app.create_assisted_apply_document_grant(
                    package_id=package.package_id,
                    document_id=document_id,
                    raw_session=session,
                    extension_origin=EXTENSION_ORIGIN,
                )

        duplicate_covers = [
            {**invalid_documents[1], "document_id": "cover_one", "file_name": "Cover.pdf"},
            {**invalid_documents[1], "document_id": "cover_two", "file_name": "Other.pdf"},
        ]
        with self.assertRaisesRegex(ValueError, "at most one cover letter"):
            self.app.create_application_package(
                user_id=owner.user_id,
                job={"job_id": "duplicate_cover", "portal": "greenhouse"},
                documents=duplicate_covers,
            )

    def test_grant_rejects_forged_or_ambiguous_upload_intents_and_retry_is_fresh(self):
        owner, _connection, session = self._connected_user("intent")
        package, _ = self._bound_package(owner.user_id)
        with self.assertRaisesRegex(ValueError, "upload field intent"):
            self.app.create_assisted_apply_document_grant(
                package_id=package.package_id,
                document_id="cv_version_7",
                adapter="greenhouse",
                upload_field_intent="greenhouse.cover_letter",
                raw_session=session,
                extension_origin=EXTENSION_ORIGIN,
            )
        first = self.app.create_assisted_apply_document_grant(
            package_id=package.package_id,
            document_id="cv_version_7",
            adapter="greenhouse",
            upload_field_intent="greenhouse.resume",
            raw_session=session,
            extension_origin=EXTENSION_ORIGIN,
        )
        self.app.consume_assisted_apply_document_grant(
            raw_grant=first["grantToken"], raw_session=session, extension_origin=EXTENSION_ORIGIN
        )
        with self.assertRaises(PermissionError):
            self.app.consume_assisted_apply_document_grant(
                raw_grant=first["grantToken"], raw_session=session, extension_origin=EXTENSION_ORIGIN
            )
        second = self.app.create_assisted_apply_document_grant(
            package_id=package.package_id,
            document_id="cv_version_7",
            adapter="greenhouse",
            upload_field_intent="greenhouse.resume",
            raw_session=session,
            extension_origin=EXTENSION_ORIGIN,
        )
        self.assertNotEqual(first["grantToken"], second["grantToken"])


if __name__ == "__main__":
    unittest.main()
