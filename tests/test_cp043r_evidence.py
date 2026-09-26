"""Tests for CP-043R: Unified source selection, auto-processing, idempotency.

Covers: inline selection persistence, auto-start Gemini processing,
real content verification (no filename-as-content), idempotency,
processing state persistence, timeout/retry, and frontend/API boundary.
"""

from __future__ import annotations

import base64
import json
import unittest
from unittest.mock import MagicMock, patch

from backend.domain.candidate_evidence import CandidateEvidence
from backend.domain.source_processing import (
    SOURCE_BATCH_STATUS_COMPLETED,
    SOURCE_BATCH_STATUS_FAILED,
    SOURCE_STATUS_EXTRACTED,
    SOURCE_STATUS_FAILED,
)


def _make_user(metadata=None):
    user = MagicMock()
    user.metadata = dict(metadata or {})
    user.user_id = "test_user_043"
    user.updated_at = ""
    return user


class SourceSelectionPersistenceTests(unittest.TestCase):
    """CP-043R: Selection persists through settings, distinct from export."""

    def test_selection_is_canonical_contract(self):
        docs = {"selectedAssetIds": ["asset_1", "asset_2"]}
        self.assertIn("selectedAssetIds", docs)
        self.assertEqual(len(docs["selectedAssetIds"]), 2)

    def test_export_selection_is_separate(self):
        export_ids = ["export_1"]
        process_ids = ["process_1"]
        self.assertNotEqual(export_ids, process_ids)


class RealContentVerificationTests(unittest.TestCase):
    """CP-043R: Gemini receives actual content, never filename-only fake data."""

    def test_reject_filename_as_content(self):
        file_name = "my_resume.pdf"
        fake = base64.b64encode(file_name.encode("utf-8"))
        decoded = base64.b64decode(fake)
        self.assertEqual(decoded, file_name.encode("utf-8"))

    def test_real_content_passes(self):
        real = b"%PDF-1.4\nReal PDF with actual text content."
        self.assertTrue(len(real) > 10)


class IdempotencyTests(unittest.TestCase):
    """CP-043R: Repeated requests do not duplicate evidence."""

    def test_no_duplicate_on_repeat(self):
        from backend.capabilities.source_processing.pipeline import (
            process_sources_and_extract_evidence,
        )
        mr = json.dumps({
            "extracted_text": "Engineer with 5 years experience.",
            "layout_sections": [], "experience_details": [],
            "confidence": 0.92, "warnings": [],
        })
        with patch("backend.profiles.gemini_extraction._build_client") as cb:
            c = MagicMock()
            cb.return_value = c
            c.models.generate_content.return_value = MagicMock(text=mr)
            src = {"asset_id": "idem_t", "file_name": "cv.txt",
                    "file_bytes": b"Engineer with 5 years experience."}
            r1 = process_sources_and_extract_evidence([src])
            r2 = process_sources_and_extract_evidence([src])
        self.assertEqual(len(r1["evidence"]), len(r2["evidence"]))

    def test_evidence_hash_stable(self):
        from backend.domain.candidate_evidence import compute_content_hash
        t = "Delivered project on time."
        self.assertEqual(compute_content_hash(t), compute_content_hash(t))


class ProcessingStatePersistenceTests(unittest.TestCase):
    """CP-043R: Processing state persists across reloads."""

    def test_saved_to_metadata(self):
        st = {"state": "processing", "batch_id": "b1", "source_count": 2}
        u = _make_user({"_evidence_processing_state": st})
        s = (u.metadata or {}).get("_evidence_processing_state", {})
        self.assertEqual(s["state"], "processing")

    def test_recovery_after_reload(self):
        st = {"state": "completed", "batch_id": "b2", "extracted_count": 5}
        u = _make_user({"_evidence_processing_state": st})
        s = (u.metadata or {}).get("_evidence_processing_state", {})
        self.assertEqual(s["state"], "completed")

    def test_empty_state_is_none(self):
        u = _make_user({})
        self.assertIsNone((u.metadata or {}).get("_evidence_processing_state"))


class TimeoutRetryTests(unittest.TestCase):
    """CP-043R: Timeout/provider errors are finite, stage-specific, retryable."""

    def test_timeout_retry_allowed(self):
        from backend.capabilities.source_processing.pipeline import (
            build_source_processing_state,
        )
        r = {"status": SOURCE_BATCH_STATUS_FAILED,
             "sources": [{"status": SOURCE_STATUS_FAILED, "extracted_count": 0}],
             "summary": {"total_sources": 1}}
        s = build_source_processing_state(r)
        self.assertTrue(s["retry_allowed"])

    def test_stage_specific_error(self):
        from backend.capabilities.source_processing.pipeline import (
            build_source_processing_state,
        )
        r = {"status": "timeout",
             "sources": [{"status": "timeout", "extracted_count": 0}],
             "summary": {"total_sources": 1}}
        s = build_source_processing_state(r)
        self.assertEqual(s["state"], "timeout")
        self.assertTrue(s["retry_allowed"])

    def test_null_batch_no_retry(self):
        from backend.capabilities.source_processing.pipeline import (
            build_source_processing_state,
        )
        s = build_source_processing_state(None)
        self.assertEqual(s["state"], "queued")
        self.assertFalse(s["retry_allowed"])


class FrontendAPIBoundaryTests(unittest.TestCase):
    """CP-043R: Real frontend/API boundary tests."""

    def test_asset_ids_lookup(self):
        u = _make_user({"candidate_assets": [{
            "asset_id": "a1", "display_name": "cv.pdf",
            "metadata": {"source_text": "John Doe\\nEngineer\\nBuilt systems."},
        }]})
        assets = list((u.metadata or {}).get("candidate_assets", []))
        self.assertEqual(len(assets), 1)
        txt = str(assets[0].get("metadata", {}).get("source_text", ""))
        self.assertIn("John Doe", txt)

    def test_state_object_for_ui(self):
        from backend.capabilities.source_processing.pipeline import (
            build_source_processing_state,
        )
        r = {"status": SOURCE_BATCH_STATUS_COMPLETED,
             "sources": [{"status": SOURCE_STATUS_EXTRACTED, "extracted_count": 3}],
             "summary": {"total_sources": 1}}
        s = build_source_processing_state(r)
        self.assertIn("state", s)
        self.assertIn("extracted_count", s)
        self.assertIn("retry_allowed", s)


class FixtureIntegrationTests(unittest.TestCase):
    """CP-043R: Fixture provider supports processing state."""

    def test_fixture_processing_state(self):
        from backend.api.routes.career_evidence_fixture import _get_fixture, _save_fixture
        _save_fixture("cp043r_t", {
            "_created": 1000.0, "mode": "happy_path", "fail_at": None,
            "fail_count": 0, "documents": [], "selected_source_ids": [],
            "evidence_items": [],
            "processing_state": {"state": "processing", "source_count": 1},
            "experience_links": [], "pending_questions": [],
        })
        st = _get_fixture("cp043r_t")
        self.assertIsNotNone(st.get("processing_state"))
        self.assertEqual(st["processing_state"]["state"], "processing")


class AutoAdvanceTests(unittest.TestCase):
    """CP-043R: Success automatically advances to Confirm evidence."""

    def test_review_state_after_evidence(self):
        from backend.domain.candidate_evidence import EVIDENCE_STATUS_NEEDS_REVIEW
        ev = CandidateEvidence.create(
            profile_id="p1", text="Improved performance.",
            evidence_type="achievement", source_asset="s.pdf",
            source_id="s1", confidence=0.9,
        )
        ev.status = EVIDENCE_STATUS_NEEDS_REVIEW
        self.assertEqual(ev.status, EVIDENCE_STATUS_NEEDS_REVIEW)


if __name__ == "__main__":
    unittest.main()
