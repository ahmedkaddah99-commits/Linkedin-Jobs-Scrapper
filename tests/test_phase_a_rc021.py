from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.domain.models import ArtifactRecord
from backend.storage import (
    LocalObjectStorage,
    ObjectNotFoundError,
    ObjectDownloadRejected,
    materialize_object,
    publish_file_artifacts,
    validate_object_download,
)


class Rc021StorageTests(unittest.TestCase):
    def test_artifact_object_keys_are_immutable_across_content_revisions(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            storage = LocalObjectStorage(root / "objects")
            source = root / "generated" / "cv.pdf"
            source.parent.mkdir()
            source.write_bytes(b"revision-one")
            artifact = ArtifactRecord(artifact_id="artifact_cv", artifact_type="cv_pdf", path=str(source))

            first = publish_file_artifacts(storage, run_id="run_1", artifacts=[artifact])[0]
            first_key = str(first.metadata["object_key"])
            source.write_bytes(b"revision-two")
            second = publish_file_artifacts(storage, run_id="run_1", artifacts=[artifact])[0]
            second_key = str(second.metadata["object_key"])

            self.assertNotEqual(first_key, second_key)
            self.assertEqual(storage.get(first_key), b"revision-one")
            self.assertEqual(storage.get(second_key), b"revision-two")

    def test_materialization_cache_prunes_old_entries_by_byte_cap(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            storage = LocalObjectStorage(root / "objects")
            first_key = "private/users/user_1/files/one.txt"
            second_key = "private/users/user_1/files/two.txt"
            storage.put(first_key, b"1234", content_type="text/plain")
            storage.put(second_key, b"5678", content_type="text/plain")

            with patch.dict(
                os.environ,
                {
                    "OBJECT_STORAGE_CACHE_ROOT": str(root / "cache"),
                    "OBJECT_STORAGE_CACHE_MAX_BYTES": "4",
                    "OBJECT_STORAGE_CACHE_MAX_AGE_SECONDS": "3600",
                },
            ):
                first_path = materialize_object(storage, first_key, filename="one.txt")
                second_path = materialize_object(storage, second_key, filename="two.txt")

            self.assertFalse(first_path.exists())
            self.assertEqual(second_path.read_bytes(), b"5678")

    def test_local_signed_download_rejects_tampering_and_expiry(self):
        current_time = [1_000]
        with tempfile.TemporaryDirectory() as temporary_directory:
            storage = LocalObjectStorage(
                temporary_directory,
                signing_secret="test-secret",
                clock=lambda: current_time[0],
            )
            key = "private/users/user_1/files/cv.pdf"
            storage.put(key, b"pdf", content_type="application/pdf")
            url = storage.signed_download_url(key, expires_in_seconds=10, download_filename="cv.pdf")
            from urllib.parse import parse_qs, unquote, urlparse

            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            self.assertEqual(
                storage.verify_signed_download(
                    unquote(parsed.path.split("/v1/storage/objects/", 1)[1]),
                    expires_at=query["expires"][0],
                    signature=query["signature"][0],
                    download_filename=query["download"][0],
                ),
                key,
            )
            with self.assertRaises(ObjectNotFoundError):
                storage.verify_signed_download(
                    key,
                    expires_at=query["expires"][0],
                    signature="tampered",
                    download_filename="cv.pdf",
                )
            current_time[0] = 1_011
            with self.assertRaises(ObjectNotFoundError):
                storage.verify_signed_download(
                    key,
                    expires_at=query["expires"][0],
                    signature=query["signature"][0],
                    download_filename="cv.pdf",
                )

    def test_local_signed_route_serves_valid_link_and_hides_expired_link(self):
        from urllib.parse import parse_qs, urlparse

        from backend.api.routes.registry import ApiRouteContext
        from backend.api.routes.storage import _handle_get

        class Handler:
            def __init__(self):
                self.body = None
                self.error = None

            def _send_bytes(self, body, *, content_type, download_name):
                self.body = (body, content_type, download_name)

            def _send_error(self, status, code, message, **_kwargs):
                self.error = (status, code, message)

        current_time = [1_000]
        with tempfile.TemporaryDirectory() as temporary_directory:
            storage = LocalObjectStorage(
                temporary_directory,
                signing_secret="test-secret",
                clock=lambda: current_time[0],
            )
            key = "private/users/user_1/files/cv.pdf"
            storage.put(key, b"pdf", content_type="application/pdf")
            url = storage.signed_download_url(key, expires_in_seconds=10, download_filename="cv.pdf")
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            handler = Handler()
            context = ApiRouteContext(
                application=type("App", (), {"object_storage": storage})(),
                handler=handler,
                method="GET",
                segments=tuple(["storage", "objects", *key.split("/")]),
                query=query,
            )

            self.assertTrue(_handle_get(context))
            self.assertEqual(handler.body, (b"pdf", "application/pdf", "cv.pdf"))

            current_time[0] = 1_011
            expired_handler = Handler()
            expired_context = ApiRouteContext(
                application=context.application,
                handler=expired_handler,
                method="GET",
                segments=context.segments,
                query=query,
            )
            self.assertTrue(_handle_get(expired_context))
            self.assertEqual(expired_handler.error[0], 404)

    def test_download_policy_rejects_unapproved_mime_and_size(self):
        with self.assertRaises(ObjectDownloadRejected):
            validate_object_download(content_type="application/x-msdownload", size=10, filename="run.exe")
        with patch.dict(os.environ, {"OBJECT_STORAGE_MAX_DOWNLOAD_BYTES": "4"}):
            with self.assertRaises(ObjectDownloadRejected):
                validate_object_download(content_type="application/pdf", size=5, filename="cv.pdf")

    def test_cloud_download_redirect_does_not_read_object_through_api(self):
        from types import SimpleNamespace

        from backend.api.server import build_handler

        class DirectStorage:
            supports_direct_download = True

            def __init__(self):
                self.signed = []

            def signed_download_url(self, key, *, download_filename="", expires_in_seconds=None):
                self.signed.append((key, download_filename, expires_in_seconds))
                return "https://objects.example/signed.pdf"

            def get(self, _key):
                raise AssertionError("the API must not read a direct object download")

        storage = DirectStorage()
        application = SimpleNamespace(object_storage=storage)
        handler_type = build_handler(application)
        handler = object.__new__(handler_type)
        handler._client_disconnected = False
        handler._response_started = False
        redirect = {}
        handler._send_redirect = lambda location, **kwargs: redirect.update({"location": location, **kwargs})

        handler._send_portable_download(
            application,
            object_key="private/users/user_1/files/cv.pdf",
            file_path="C:/worker-only/cv.pdf",
            download_name="Candidate CV.pdf",
            content_type="application/pdf",
            object_size=8,
        )

        self.assertEqual(redirect["location"], "https://objects.example/signed.pdf")
        self.assertEqual(redirect["object_storage_bytes"], 8)
        self.assertEqual(storage.signed[0][1], "Candidate CV.pdf")


if __name__ == "__main__":
    unittest.main()
