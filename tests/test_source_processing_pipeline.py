"""CP-039R: Integration tests for the source processing pipeline.

Covers text and image fixtures through the full vertical path:
upload/bytes -> Gemini processing -> evidence extraction -> persistence.

Only mocks at the provider boundary (Gemini API client).
"""

from __future__ import annotations

import base64
import json
import os
import struct
import unittest
import zlib
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.capabilities.source_processing.pipeline import (
    build_source_processing_state,
    process_sources_and_extract_evidence,
)
from backend.domain.source_processing import (
    SOURCE_BATCH_STATUS_COMPLETED,
    SOURCE_BATCH_STATUS_FAILED,
    SOURCE_BATCH_STATUS_TIMEOUT,
    SOURCE_STATUS_EMPTY,
    SOURCE_STATUS_EXTRACTED,
    SOURCE_STATUS_FAILED,
)
from backend.domain.candidate_evidence import CandidateEvidence, compute_content_hash


class TestSourceProcessingPipeline(unittest.TestCase):
    """Tests for process_sources_and_extract_evidence."""

    def _mock_gemini_response(
        self,
        text="Extracted text content.",
        confidence=0.92,
        *,
        experience_details=None,
        evidence_items=None,
    ):
        j = json.dumps({
            "extracted_text": text,
            "layout_sections": [],
            "experience_details": experience_details or [],
            "evidence_items": evidence_items or [],
            "confidence": confidence,
            "warnings": [],
        })
        m = MagicMock()
        m.text = j
        return m

    def test_text_source_processed_and_evidence_extracted(self):
        mr = self._mock_gemini_response(
            "John Doe\nSoftware Engineer at Acme Corp\n"
            "Increased revenue by 30% through process automation.\n",
            0.93,
        )
        with patch("backend.profiles.gemini_extraction._build_client") as cb:
            c = MagicMock()
            cb.return_value = c
            c.models.generate_content.return_value = mr
            result = process_sources_and_extract_evidence([
                {"asset_id": "txt_1", "file_name": "resume.txt",
                 "file_bytes": b"John Doe\nSoftware Engineer at Acme Corp\n"}
            ])
        self.assertEqual(result["status"], SOURCE_BATCH_STATUS_COMPLETED)
        self.assertEqual(result["summary"]["total_sources"], 1)
        self.assertGreater(len(result["evidence"]), 0)
        for ev_dict in result["evidence"]:
            self.assertTrue(ev_dict.get("content_hash"))
            self.assertEqual(ev_dict["status"], "needs_review")

    def test_structured_gemini_output_excludes_cv_chrome_and_maps_real_experience(self):
        mr = self._mock_gemini_response(
            "Erlangen, Germany\nahmed@example.com\nWORK EXPERIENCE\n"
            "Operations Analyst at Acme GmbH\n"
            "Automated monthly reporting and reduced preparation time by 40%.",
            0.97,
            experience_details=[{
                "employer": "Acme GmbH",
                "role": "Operations Analyst",
                "location": "Erlangen, Germany",
                "start_date": "2022-01",
                "end_date": "2024-06",
                "bullets": [
                    "Automated monthly reporting and reduced preparation time by 40%.",
                ],
            }],
            evidence_items=[{
                "text": "Automated monthly reporting and reduced preparation time by 40%.",
                "evidence_type": "metric",
                "inferred_employer": "Acme GmbH",
                "inferred_role": "Operations Analyst",
                "dates": ["2022-01", "2024-06"],
                "location": "Erlangen, Germany",
                "source_section": "Work Experience",
            }],
        )
        with patch("backend.profiles.gemini_extraction._build_client") as cb:
            client = MagicMock()
            cb.return_value = client
            client.models.generate_content.return_value = mr
            result = process_sources_and_extract_evidence([{
                "asset_id": "cv_1",
                "file_name": "resume.txt",
                "file_bytes": b"real cv content",
            }])

        self.assertEqual(len(result["evidence"]), 1)
        self.assertEqual(len(result["experiences"]), 1)
        evidence = result["evidence"][0]
        experience = result["experiences"][0]
        self.assertNotIn("Erlangen, Germany", [item["text"] for item in result["evidence"]])
        self.assertEqual(evidence["experience_mapping"]["experience_id"], experience["experience_id"])
        self.assertEqual(experience["employer"], "Acme GmbH")



    def test_pdf_source_multimodal_processed(self):
        mr = self._mock_gemini_response("Jane Smith, Product Manager.", 0.90)
        with patch("backend.profiles.gemini_extraction._build_client") as cb:
            c = MagicMock()
            cb.return_value = c
            c.models.generate_content.return_value = mr
            result = process_sources_and_extract_evidence([
                {"asset_id": "pdf_1", "file_name": "cv.pdf", "file_bytes": b"%PDF-1.4 data"}
            ])
        self.assertEqual(result["status"], SOURCE_BATCH_STATUS_COMPLETED)
        src = result["sources"][0]
        self.assertEqual(src["method"], "gemini")
        self.assertEqual(src["provider"], "gemini")
        self.assertGreater(len(result["evidence"]), 0)

    def test_image_source_multimodal_processed(self):
        mr = self._mock_gemini_response("Screenshot: Submit button visible.", 0.88)
        with patch("backend.profiles.gemini_extraction._build_client") as cb:
            c = MagicMock()
            cb.return_value = c
            c.models.generate_content.return_value = mr
            sig = b'\x89PNG\r\n\x1a\n'
            ihdr_d = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
            ihdr_c = zlib.crc32(b'IHDR' + ihdr_d)
            ihdr = struct.pack('>I', 13) + b'IHDR' + ihdr_d + struct.pack('>I', ihdr_c)
            idat_d = zlib.compress(b'\x00\xff\xff\xff')
            idat_c = zlib.crc32(b'IDAT' + idat_d)
            idat = struct.pack('>I', len(idat_d)) + b'IDAT' + idat_d + struct.pack('>I', idat_c)
            iend_c = zlib.crc32(b'IEND')
            iend = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_c)
            result = process_sources_and_extract_evidence([
                {"asset_id": "img_1", "file_name": "ss.png",
                 "file_bytes": sig + ihdr + idat + iend}
            ])
        self.assertEqual(result["status"], SOURCE_BATCH_STATUS_COMPLETED)
        self.assertEqual(result["sources"][0]["method"], "gemini")

    def test_empty_file_bytes_produces_empty_status(self):
        result = process_sources_and_extract_evidence([
            {"asset_id": "empty_1", "file_name": "e.txt", "file_bytes": b""}
        ])
        self.assertEqual(result["sources"][0]["status"], SOURCE_STATUS_EMPTY)
        self.assertEqual(len(result["evidence"]), 0)

    def test_gemini_unavailable_does_not_create_unstructured_evidence(self):
        with patch(
            "backend.profiles.gemini_extraction.extract_with_gemini",
            side_effect=RuntimeError("API key not configured"),
        ):
            result = process_sources_and_extract_evidence([
                {"asset_id": "fb_1", "file_name": "notes.txt",
                 "file_bytes": b"Fallback content.\n"}
            ])
        src = result["sources"][0]
        self.assertEqual(src["status"], SOURCE_STATUS_FAILED)
        self.assertIn("Gemini structured extraction", src["error"])
        self.assertEqual(result["evidence"], [])

    def test_idempotent_no_duplicate_evidence(self):
        mr = self._mock_gemini_response("Delivered migration project on time.", 0.91)
        with patch("backend.profiles.gemini_extraction._build_client") as cb:
            c = MagicMock()
            cb.return_value = c
            c.models.generate_content.return_value = mr
            r1 = process_sources_and_extract_evidence([
                {"asset_id": "id_1", "file_name": "a.txt", "file_bytes": b"Delivered migration."}
            ])
            r2 = process_sources_and_extract_evidence([
                {"asset_id": "id_2", "file_name": "b.txt", "file_bytes": b"Delivered migration."}
            ])
        self.assertEqual(len(r1["evidence"]), len(r2["evidence"]))
        self.assertEqual(
            {e["content_hash"] for e in r1["evidence"]},
            {e["content_hash"] for e in r2["evidence"]},
        )

    def test_multiple_sources_batch(self):
        mr = self._mock_gemini_response("Team leader with agile experience.", 0.89)
        with patch("backend.profiles.gemini_extraction._build_client") as cb:
            c = MagicMock()
            cb.return_value = c
            c.models.generate_content.return_value = mr
            result = process_sources_and_extract_evidence([
                {"asset_id": "a1", "file_name": "d1.txt", "file_bytes": b"Team leader."},
                {"asset_id": "a2", "file_name": "d2.pdf", "file_bytes": b"%PDF-1.4"},
            ])
        self.assertEqual(result["status"], SOURCE_BATCH_STATUS_COMPLETED)
        self.assertEqual(result["summary"]["total_sources"], 2)

    def test_build_state_none_returns_queued(self):
        state = build_source_processing_state(None)
        self.assertEqual(state["state"], "queued")
        self.assertEqual(state["retry_allowed"], False)

    def test_build_state_completed(self):
        result = {
            "status": "completed",
            "sources": [{"status": "extracted", "extracted_count": 3}],
            "summary": {"total_sources": 1},
        }
        state = build_source_processing_state(result)
        self.assertEqual(state["state"], "completed")
        self.assertEqual(state["extracted_count"], 3)

    def test_build_state_failed_with_retry(self):

        result = {
            "status": SOURCE_BATCH_STATUS_FAILED,
            "sources": [{"status": SOURCE_STATUS_FAILED, "extracted_count": 0}],
            "summary": {"total_sources": 1},
        }
        state = build_source_processing_state(result)
        self.assertEqual(state["state"], SOURCE_BATCH_STATUS_FAILED)
        self.assertEqual(state["error"], "Source processing failed.")
        self.assertTrue(state["retry_allowed"])


class TestSourceProcessingPipelineAPIIntegration(unittest.TestCase):
    """Integration tests with a real BackendApplication (mocking only Gemini)."""

    def setUp(self):
        from backend import create_backend
        import shutil
        self.temp_dir = Path.cwd() / ".backend_test_tmp" / f"pipeline_api_{self._testMethodName}"
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))

        self.deepseek_patch = patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}, clear=False)
        self.deepseek_patch.start()
        self.addCleanup(self.deepseek_patch.stop)

        self.storage_patch = patch.dict(os.environ, {
            "RUNR_ENV": "development", "DATABASE_BACKEND": "sqlite",
            "TURSO_DATABASE_URL": "", "TURSO_AUTH_TOKEN": "",
            "OBJECT_STORAGE_BACKEND": "local", "OBJECT_STORAGE_LOCAL_ROOT": "",
        }, clear=False)
        self.storage_patch.start()
        self.addCleanup(self.storage_patch.stop)

        self.quota_patch = patch.dict(os.environ, {"RUNR_DISABLE_QUOTAS": "1"}, clear=False)
        self.quota_patch.start()
        self.addCleanup(self.quota_patch.stop)

        self.app = create_backend(self.temp_dir)
        self.user = self.app.upsert_user({
            "email": "pipeline@example.com",
            "display_name": "Pipeline Test",
            "role": "viewer",
        })
        _, self.access_token = self.app.issue_api_token(
            user_id=self.user.user_id, name="pipeline-test")

    def _request(self, method, path, payload=None):
        from http.client import HTTPConnection
        from threading import Thread
        from backend.api.server import build_handler
        from http.server import ThreadingHTTPServer

        server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            build_handler(self.app, allowed_origins={"http://127.0.0.1:4173"}),
        )
        port = server.server_address[1]
        t = Thread(target=server.serve_forever, daemon=True)
        t.start()
        self.addCleanup(server.shutdown)

        conn = HTTPConnection("127.0.0.1", port, timeout=10)
        headers = {"Authorization": f"Bearer {self.access_token}"}
        body = None
        if payload is not None:
            body = json.dumps(payload)
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8")
        conn.close()
        return resp.status, json.loads(raw) if raw else {}

    def test_process_sources_endpoint_text(self):
        mr = json.dumps({
            "extracted_text": "Alice\nData Scientist\nBuilt ML pipeline.",
            "layout_sections": [], "experience_details": [],
            "confidence": 0.94, "warnings": [],
        })
        with patch("backend.profiles.gemini_extraction._build_client") as cb:
            c = MagicMock()
            cb.return_value = c
            c.models.generate_content.return_value = MagicMock(text=mr)
            file_b64 = base64.b64encode(b"Alice\nData Scientist\n").decode("utf-8")
            status, payload = self._request("POST", "/evidence-items/process-sources", {
                "profile_id": "prof_test",
                "sources": [{"asset_id": "api_1", "file_name": "a.txt", "file_bytes": file_b64}],
            })
        self.assertEqual(status, 200, payload)
        self.assertEqual(payload["status"], SOURCE_BATCH_STATUS_COMPLETED)
        self.assertGreater(len(payload["evidence"]), 0)
        self.assertIn("state", payload)

    def test_process_sources_endpoint_image(self):
        mr = json.dumps({
            "extracted_text": "Application screenshot: Upload CV button.",
            "layout_sections": [], "experience_details": [],
            "confidence": 0.85, "warnings": [],
        })
        with patch("backend.profiles.gemini_extraction._build_client") as cb:
            c = MagicMock()
            cb.return_value = c
            c.models.generate_content.return_value = MagicMock(text=mr)
            sig = b'\x89PNG\r\n\x1a\n'
            ihdr_d = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
            ihdr_c = zlib.crc32(b'IHDR' + ihdr_d)
            ihdr = struct.pack('>I', 13) + b'IHDR' + ihdr_d + struct.pack('>I', ihdr_c)
            idat_d = zlib.compress(b'\x00\xff\xff\xff')
            idat_c = zlib.crc32(b'IDAT' + idat_d)
            idat = struct.pack('>I', len(idat_d)) + b'IDAT' + idat_d + struct.pack('>I', idat_c)
            iend_c = zlib.crc32(b'IEND')
            iend = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_c)
            png = sig + ihdr + idat + iend
            file_b64 = base64.b64encode(png).decode("utf-8")
            status, payload = self._request("POST", "/evidence-items/process-sources", {
                "sources": [{"asset_id": "img_1", "file_name": "ss.png", "file_bytes": file_b64}],
            })
        self.assertEqual(status, 200, payload)
        self.assertEqual(payload["status"], SOURCE_BATCH_STATUS_COMPLETED)
        self.assertEqual(payload["sources"][0]["method"], "gemini")

    def test_process_sources_empty_payload_rejected(self):
        status, payload = self._request("POST", "/evidence-items/process-sources", {})
        self.assertEqual(status, 422)

    def test_process_sources_idempotent(self):
        mr = json.dumps({
            "extracted_text": "Bob\nEngineering Manager\nManaged team of 12.",
            "layout_sections": [], "experience_details": [],
            "confidence": 0.93, "warnings": [],
        })
        with patch("backend.profiles.gemini_extraction._build_client") as cb:
            c = MagicMock()
            cb.return_value = c
            c.models.generate_content.return_value = MagicMock(text=mr)
            file_b64 = base64.b64encode(b"Bob\nEngineering Manager\n").decode("utf-8")
            s1, p1 = self._request("POST", "/evidence-items/process-sources", {
                "profile_id": "prof_test",
                "sources": [{"asset_id": "id1", "file_name": "a.txt", "file_bytes": file_b64}],
            })
            s2, p2 = self._request("POST", "/evidence-items/process-sources", {
                "profile_id": "prof_test",
                "sources": [{"asset_id": "id2", "file_name": "b.txt", "file_bytes": file_b64}],
            })
            self.assertEqual(s1, 200, p1)
            self.assertEqual(s2, 200, p2)
            self.assertEqual(len(p1["evidence"]), len(p2["evidence"]))

    def test_confirm_is_persisted_and_next_authenticated_request_advances(self):
        from backend.domain.candidate_evidence import CandidateEvidence

        first = CandidateEvidence.create(
            text="Automated reporting and reduced preparation time by 40%.",
            evidence_type="metric",
            source_id="cv_1",
            inferred_employer="Acme GmbH",
            inferred_role="Operations Analyst",
            experience_mapping={
                "experience_id": "exp_acme",
                "company": "Acme GmbH",
                "role": "Operations Analyst",
            },
        )
        second = CandidateEvidence.create(
            text="Coordinated five stakeholders and delivered the launch on schedule.",
            evidence_type="stakeholder",
            source_id="cv_1",
            inferred_employer="Acme GmbH",
            inferred_role="Operations Analyst",
            experience_mapping={
                "experience_id": "exp_acme",
                "company": "Acme GmbH",
                "role": "Operations Analyst",
            },
        )
        persisted = self.app.repositories.auth_repository.get_user(self.user.user_id)
        persisted.metadata = {
            **dict(persisted.metadata or {}),
            "candidate_evidence": [first.to_dict(), second.to_dict()],
            "work_experiences": [{
                "experience_id": "exp_acme",
                "employer": "Acme GmbH",
                "job_title": "Operations Analyst",
                "start_date": "2022-01",
                "end_date": "2024-06",
            }],
        }
        self.app.repositories.auth_repository.upsert_user(persisted)

        status, response = self._request("POST", "/evidence-items/confirm-inspect", {
            "evidence_id": first.evidence_id,
            "mapping": first.experience_mapping,
        })
        self.assertEqual(status, 200, response)

        reloaded = self.app.repositories.auth_repository.get_user(self.user.user_id)
        statuses = {
            item["evidence_id"]: item["status"]
            for item in (reloaded.metadata or {}).get("candidate_evidence", [])
        }
        self.assertEqual(statuses[first.evidence_id], "confirmed")

        status, journey = self._request("GET", "/evidence-items/journey-state")
        self.assertEqual(status, 200, journey)
        self.assertEqual(
            journey["next_review"]["evidence"]["evidence_id"],
            second.evidence_id,
        )

    def test_legacy_extraction_is_reprocessed_instead_of_reviewed(self):
        legacy = CandidateEvidence.create(
            text="Erlangen, Germany",
            source_id="cv_legacy",
        )
        persisted = self.app.repositories.auth_repository.get_user(self.user.user_id)
        persisted.metadata = {
            **dict(persisted.metadata or {}),
            "candidate_evidence": [legacy.to_dict()],
            "_evidence_processing_state": {
                "state": "completed",
                "batch_id": "legacy",
            },
        }
        self.app.repositories.auth_repository.upsert_user(persisted)

        status, journey = self._request("GET", "/evidence-items/journey-state")
        self.assertEqual(status, 200, journey)
        self.assertEqual(journey["state"], "processing")
        self.assertTrue(journey["requires_reprocessing"])
        self.assertEqual(journey["evidence_items"], [])


if __name__ == "__main__":
    unittest.main()
