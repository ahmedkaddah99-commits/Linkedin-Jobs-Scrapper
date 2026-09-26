import io
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from backend.storage import (
    InvalidObjectKeyError,
    LocalObjectStorage,
    ObjectMaterializationSession,
    ObjectNotFoundError,
    S3ObjectStorage,
    build_private_object_key,
    create_object_storage,
    materialize_object,
    normalize_object_key,
    probe_object_storage,
    publish_file_artifacts,
)
from backend.domain.models import ArtifactRecord


class _MissingObjectError(Exception):
    response = {"Error": {"Code": "NoSuchKey"}}


class _FakeS3Client:
    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}
        self.calls: list[tuple[str, dict]] = []

    def put_object(self, **kwargs):
        self.calls.append(("put_object", kwargs))
        self.objects[(kwargs["Bucket"], kwargs["Key"])] = bytes(kwargs["Body"])
        return {"ETag": '"fake-etag"'}

    def get_object(self, **kwargs):
        self.calls.append(("get_object", kwargs))
        try:
            body = self.objects[(kwargs["Bucket"], kwargs["Key"])]
        except KeyError as exc:
            raise _MissingObjectError from exc
        return {"Body": io.BytesIO(body)}

    def delete_object(self, **kwargs):
        self.calls.append(("delete_object", kwargs))
        self.objects.pop((kwargs["Bucket"], kwargs["Key"]), None)
        return {}

    def head_object(self, **kwargs):
        self.calls.append(("head_object", kwargs))
        if (kwargs["Bucket"], kwargs["Key"]) not in self.objects:
            raise _MissingObjectError
        return {}

    def generate_presigned_url(self, operation, **kwargs):
        self.calls.append(("generate_presigned_url", {"operation": operation, **kwargs}))
        return f"https://signed.example/{kwargs['Params']['Key']}?expires={kwargs['ExpiresIn']}"


class ObjectKeyTests(unittest.TestCase):
    def test_private_object_keys_are_deterministic_and_path_safe(self):
        arguments = {
            "namespace": "users",
            "owner_id": "user/123",
            "category": "candidate-assets",
            "object_id": "asset:456",
            "filename": "../Ahmed CV.pdf",
        }

        first = build_private_object_key(**arguments)
        second = build_private_object_key(**arguments)

        self.assertEqual(first, second)
        self.assertTrue(first.startswith("private/users/"))
        self.assertNotIn("..", first.split("/"))
        self.assertNotIn(" ", first)

    def test_normalize_object_key_rejects_traversal_and_absolute_paths(self):
        for key in ("../secret.txt", "/absolute.txt", "private//file.txt", r"private\..\file.txt"):
            with self.subTest(key=key):
                with self.assertRaises(InvalidObjectKeyError):
                    normalize_object_key(key)


class LocalObjectStorageTests(unittest.TestCase):
    def test_local_storage_keeps_atomic_put_paths_under_windows_limit(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            padding = max(1, 195 - len(str(base)))
            storage = LocalObjectStorage(base / ("r" * padding))
            key = "private/users/user_1/documents/document_1/cv.pdf"

            _normalized_key, object_path = storage._path_for(key)
            self.assertLess(len(str(object_path)), 260)
            self.assertEqual(storage.put(key, b"long-root-content").size, 17)
            self.assertEqual(storage.get(key), b"long-root-content")

    def test_local_storage_reads_and_deletes_previous_full_digest_layout(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            storage = LocalObjectStorage(temporary_directory)
            key = "private/users/user_1/documents/document_1/legacy.pdf"
            legacy_path = storage._legacy_digest_path_for(key)
            legacy_path.parent.mkdir(parents=True, exist_ok=True)
            legacy_path.write_bytes(b"legacy-content")

            self.assertTrue(storage.exists(key))
            self.assertEqual(storage.get(key), b"legacy-content")
            storage.delete(key)
            self.assertFalse(legacy_path.exists())

    def test_local_storage_supports_full_object_lifecycle(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            storage = LocalObjectStorage(temporary_directory)
            key = "private/users/user_1/documents/document_1/cv.pdf"

            stored = storage.put(
                key,
                b"pdf-content",
                content_type="application/pdf",
                metadata={"owner": "user_1"},
            )

            self.assertEqual(stored.key, key)
            self.assertEqual(stored.size, 11)
            self.assertEqual(stored.content_type, "application/pdf")
            self.assertTrue(stored.etag)
            self.assertTrue(storage.exists(key))
            self.assertEqual(storage.get(key), b"pdf-content")

            storage.delete(key)
            self.assertFalse(storage.exists(key))
            storage.delete(key)
            with self.assertRaises(ObjectNotFoundError):
                storage.get(key)

    def test_local_signed_download_url_is_scoped_and_expiring(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            storage = LocalObjectStorage(
                temporary_directory,
                download_base_url="http://localhost:8000/v1/storage/objects",
                signing_secret="test-signing-secret",
                clock=lambda: 1_000,
            )
            key = "private/users/user_1/documents/document_1/cv.pdf"
            storage.put(key, b"content")

            url = storage.signed_download_url(
                key,
                expires_in_seconds=300,
                download_filename="Candidate CV.pdf",
            )
            parsed = urlparse(url)
            query = parse_qs(parsed.query)

            self.assertEqual(parsed.path, f"/v1/storage/objects/{key}")
            self.assertEqual(query["expires"], ["1300"])
            self.assertEqual(query["download"], ["Candidate CV.pdf"])
            self.assertEqual(len(query["signature"][0]), 64)

    def test_local_factory_uses_environment_contract(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            storage = create_object_storage(
                {
                    "OBJECT_STORAGE_BACKEND": "local",
                    "OBJECT_STORAGE_LOCAL_ROOT": temporary_directory,
                    "LOCAL_OBJECT_STORAGE_SIGNING_SECRET": "test-secret",
                }
            )

            storage.put("private/users/user_1/files/file_1/value.txt", b"value")
            self.assertEqual(storage.get("private/users/user_1/files/file_1/value.txt"), b"value")
            self.assertEqual(Path(temporary_directory).resolve(), storage.root)

    def test_materialization_and_artifact_publication_survive_source_deletion(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            storage = LocalObjectStorage(root / "objects")
            source = root / "generated" / "cv.pdf"
            source.parent.mkdir()
            source.write_bytes(b"generated-pdf")
            artifact = ArtifactRecord(
                artifact_id="artifact_cv",
                artifact_type="cv_pdf",
                path=str(source),
            )

            published = publish_file_artifacts(
                storage,
                run_id="run_1",
                artifacts=[artifact],
            )[0]
            object_key = published.metadata["object_key"]
            source.unlink()

            with patch.dict(
                os.environ,
                {"OBJECT_STORAGE_CACHE_ROOT": str(root / "cache")},
            ):
                materialized = materialize_object(
                    storage,
                    object_key,
                    filename="cv.pdf",
                )

            self.assertEqual(materialized.read_bytes(), b"generated-pdf")
            self.assertTrue(storage.exists(object_key))

    def test_materialization_session_does_not_download_the_same_key_twice(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            storage = LocalObjectStorage(root / "objects")
            key = "private/users/user_1/documents/document_1/cv.pdf"
            storage.put(key, b"pdf-content")
            get_calls = 0
            original_get = storage.get

            def counted_get(object_key):
                nonlocal get_calls
                get_calls += 1
                return original_get(object_key)

            storage.get = counted_get
            with patch.dict(os.environ, {"OBJECT_STORAGE_CACHE_ROOT": str(root / "cache")}):
                session = ObjectMaterializationSession(storage)
                first = session.materialize(key, filename="cv.pdf")
                second = session.materialize(key, filename="renamed.pdf")

            self.assertEqual(first, second)
            self.assertEqual(get_calls, 1)

    def test_readiness_probe_is_bounded_when_storage_hangs(self):
        class SlowStorage:
            def put(self, *_args, **_kwargs):
                time.sleep(0.2)

            def get(self, _key):
                return b""

            def delete(self, _key):
                return None

        started = time.perf_counter()
        with self.assertRaises(TimeoutError):
            probe_object_storage(SlowStorage(), timeout_seconds=0.02)
        self.assertLess(time.perf_counter() - started, 0.15)


class S3ObjectStorageTests(unittest.TestCase):
    def _storage(self, client):
        return S3ObjectStorage(
            bucket="runr-test",
            endpoint_url="https://example-account.r2.cloudflarestorage.com",
            access_key_id="test-access-key",
            secret_access_key="test-secret-key",
            client=client,
        )

    def test_s3_storage_uses_injected_client_without_network_calls(self):
        client = _FakeS3Client()
        storage = self._storage(client)
        key = "private/users/user_1/documents/document_1/cv.pdf"

        stored = storage.put(
            key,
            b"pdf-content",
            content_type="application/pdf",
            metadata={"owner": "user_1"},
        )

        self.assertEqual(stored.etag, "fake-etag")
        self.assertTrue(storage.exists(key))
        self.assertEqual(storage.get(key), b"pdf-content")

        url = storage.signed_download_url(
            key,
            expires_in_seconds=120,
            download_filename="Candidate CV.pdf",
        )
        self.assertEqual(url, f"https://signed.example/{key}?expires=120")
        signing_call = client.calls[-1][1]
        self.assertEqual(signing_call["operation"], "get_object")
        self.assertEqual(signing_call["ExpiresIn"], 120)
        self.assertEqual(
            signing_call["Params"]["ResponseContentDisposition"],
            'attachment; filename="Candidate CV.pdf"',
        )

        storage.delete(key)
        self.assertFalse(storage.exists(key))
        with self.assertRaises(ObjectNotFoundError):
            storage.get(key)

    def test_s3_factory_accepts_r2_configuration_and_injected_client(self):
        client = _FakeS3Client()
        storage = create_object_storage(
            {
                "OBJECT_STORAGE_BACKEND": "r2",
                "S3_ENDPOINT_URL": "https://example-account.r2.cloudflarestorage.com",
                "S3_ACCESS_KEY_ID": "test-access-key",
                "S3_SECRET_ACCESS_KEY": "test-secret-key",
                "S3_BUCKET": "runr-test",
            },
            s3_client=client,
        )

        storage.put("private/users/user_1/files/file_1/value.txt", b"value")
        self.assertEqual(storage.get("private/users/user_1/files/file_1/value.txt"), b"value")

    def test_readiness_probe_performs_real_r2_write_read_delete_cycle(self):
        client = _FakeS3Client()
        result = probe_object_storage(self._storage(client), timeout_seconds=1)

        self.assertGreaterEqual(result.elapsed_ms, 0)
        self.assertEqual(
            [operation for operation, _kwargs in client.calls],
            ["put_object", "get_object", "delete_object"],
        )
        self.assertEqual(client.objects, {})


if __name__ == "__main__":
    unittest.main()
