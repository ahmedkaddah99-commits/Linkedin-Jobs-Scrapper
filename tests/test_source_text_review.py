"""Tests for source text review and correction workflow (CP-008)."""

import unittest

from backend.domain.source_text_review import (
    SOURCE_REVIEW_STATUS_CONFIRMED,
    SOURCE_REVIEW_STATUS_IN_PROGRESS,
    SOURCE_REVIEW_STATUS_PENDING,
    SOURCE_REVIEW_STATUS_REJECTED,
    SourceTextReview,
)
from backend.domain.source_processing import (
    SOURCE_STATUS_EXTRACTED,
    SOURCE_STATUS_NEEDS_REVIEW,
    SourceTextRecord,
)
from backend.capabilities.source_text_review import (
    confirm_review,
    count_pending_reviews,
    get_or_create_review,
    get_source_review,
    get_verified_texts,
    list_reviews,
    reject_review,
    save_correction,
)


class SourceTextReviewModelTests(unittest.TestCase):
    """Unit tests for SourceTextReview domain model."""

    def test_default_status_is_pending(self):
        review = SourceTextReview(source_id="src_1")
        self.assertEqual(review.status, SOURCE_REVIEW_STATUS_PENDING)
        self.assertEqual(review.corrected_text, "")
        self.assertEqual(review.original_text, "")
        self.assertEqual(review.correction_history, [])

    def test_effective_text_returns_corrected_when_present(self):
        review = SourceTextReview(
            source_id="src_1", original_text="original",
            corrected_text="corrected",
        )
        self.assertEqual(review.effective_text, "corrected")

    def test_effective_text_falls_back_to_original(self):
        review = SourceTextReview(source_id="src_1", original_text="only original")
        self.assertEqual(review.effective_text, "only original")

    def test_requires_review_for_low_confidence_ocr(self):
        review = SourceTextReview(source_id="src_1", is_low_confidence_ocr=True)
        self.assertTrue(review.requires_review)

    def test_confirmed_does_not_require_review(self):
        review = SourceTextReview(
            source_id="src_1", status=SOURCE_REVIEW_STATUS_CONFIRMED,
        )
        self.assertFalse(review.requires_review)
        self.assertTrue(review.is_verified)

    def test_apply_correction_records_history(self):
        review = SourceTextReview(source_id="src_1", original_text="hello world")
        review.apply_correction("hello corrected world")
        self.assertEqual(review.corrected_text, "hello corrected world")
        self.assertEqual(review.status, SOURCE_REVIEW_STATUS_IN_PROGRESS)
        self.assertEqual(len(review.correction_history), 1)
        entry = review.correction_history[0]
        self.assertEqual(entry["previous_text"], "hello world")
        self.assertEqual(entry["new_text"], "hello corrected world")
        self.assertTrue(entry["timestamp"])

    def test_multiple_corrections_preserve_full_history(self):
        review = SourceTextReview(source_id="src_1", original_text="line 1")
        review.apply_correction("line 1 fixed")
        review.apply_correction("line 1 fixed again")
        self.assertEqual(len(review.correction_history), 2)
        self.assertEqual(review.correction_history[0]["previous_text"], "line 1")
        self.assertEqual(review.correction_history[1]["previous_text"], "line 1 fixed")


    def test_confirm_changes_status(self):
        review = SourceTextReview(source_id="src_1")
        review.confirm()
        self.assertEqual(review.status, SOURCE_REVIEW_STATUS_CONFIRMED)
        self.assertTrue(review.is_verified)

    def test_reject(self):
        review = SourceTextReview(source_id="src_1")
        review.reject()
        self.assertEqual(review.status, SOURCE_REVIEW_STATUS_REJECTED)

    def test_roundtrip(self):
        review = SourceTextReview(
            source_id="src_1", original_text="Extracted.",
            corrected_text="Corrected.", status=SOURCE_REVIEW_STATUS_IN_PROGRESS,
            correction_history=[{"timestamp": "2026-01-01",
                                 "changed_by": "user",
                                 "previous_text": "old", "new_text": "new"}],
        )
        payload = review.to_dict()
        restored = SourceTextReview.from_dict(payload)
        self.assertEqual(restored.source_id, "src_1")
        self.assertEqual(restored.original_text, "Extracted.")
        self.assertEqual(restored.corrected_text, "Corrected.")
        self.assertEqual(len(restored.correction_history), 1)

    def test_high_confidence_auto_confirms(self):
        record = SourceTextRecord(
            source_id="src_hc", text="clear", confidence=0.95,
            method="native", status=SOURCE_STATUS_EXTRACTED,
            is_low_confidence_ocr=False,
        )
        review = SourceTextReview.from_source_record("src_hc", record)
        self.assertEqual(review.status, SOURCE_REVIEW_STATUS_CONFIRMED)

    def test_low_confidence_stays_pending(self):
        record = SourceTextRecord(
            source_id="src_lc", text="unclear", confidence=0.55,
            method="pdf_ocr", is_ocr=True, is_low_confidence_ocr=True,
            status=SOURCE_STATUS_NEEDS_REVIEW,
        )
        review = SourceTextReview.from_source_record("src_lc", record)
        self.assertEqual(review.status, SOURCE_REVIEW_STATUS_PENDING)


class SourceTextReviewServiceTests(unittest.TestCase):
    def _record(self, sid="src_1", **kw):
        return {
            "source_id": sid,
            "file_name": kw.get("fn", "t.pdf"),
            "text": kw.get("text", "sample"),
            "confidence": kw.get("c", 0.9),
            "method": kw.get("m", "native"),
            "is_ocr": kw.get("ocr", False),
            "is_low_confidence_ocr": kw.get("lc", False),
            "warnings": kw.get("w", []),
            "pages": kw.get("p", []),
            "status": kw.get("s", SOURCE_STATUS_EXTRACTED),
        }

    def test_get_or_create_new_review(self):
        r = get_or_create_review("p1", "s1", self._record())
        self.assertEqual(r.source_id, "s1")
        self.assertEqual(r.profile_id, "p1")

    def test_get_or_create_existing(self):
        rec = self._record()
        a = get_or_create_review("p1", "s1", rec)
        b = get_or_create_review("p1", "s1", rec)
        self.assertIs(a, b)

    def test_get_unknown_returns_none(self):
        self.assertIsNone(get_source_review("pu", "su"))

    def test_save_correction(self):
        get_or_create_review("p1", "s1", self._record())
        u = save_correction("p1", "s1", "fixed")
        self.assertEqual(u.corrected_text, "fixed")
        self.assertEqual(u.status, SOURCE_REVIEW_STATUS_IN_PROGRESS)

    def test_confirm_review(self):
        get_or_create_review("p1", "s1", self._record())
        c = confirm_review("p1", "s1")
        self.assertEqual(c.status, SOURCE_REVIEW_STATUS_CONFIRMED)

    def test_reject_review(self):
        get_or_create_review("p1", "s1", self._record())
        r = reject_review("p1", "s1")
        self.assertEqual(r.status, SOURCE_REVIEW_STATUS_REJECTED)

    def test_list_reviews_by_profile(self):
        get_or_create_review("pa", "s1", self._record("s1"))
        get_or_create_review("pb", "s2", self._record("s2"))
        self.assertEqual(len(list_reviews("pa")), 1)

    def test_count_pending(self):
        get_or_create_review("p1", "s1", self._record("s1", lc=True))
        get_or_create_review("p1", "s2", self._record("s2"))
        self.assertEqual(count_pending_reviews("p1"), 1)

    def test_verified_texts(self):
        get_or_create_review("p1", "s1", self._record("s1"))
        confirm_review("p1", "s1")
        v = get_verified_texts("p1")
        self.assertEqual(len(v), 1)
        self.assertEqual(v[0]["source_id"], "s1")


class SourceTextReviewIntegrationTests(unittest.TestCase):
    def test_full_review_flow(self):
        rec = {
            "source_id": "sf", "file_name": "scan.pdf",
            "text": "OCR errors here", "confidence": 0.55,
            "method": "pdf_ocr", "is_ocr": True,
            "is_low_confidence_ocr": True,
            "warnings": ["Low confidence OCR"],
            "pages": [], "status": SOURCE_STATUS_NEEDS_REVIEW,
        }
        r = get_or_create_review("pf", "sf", rec)
        self.assertTrue(r.requires_review)
        self.assertEqual(r.status, SOURCE_REVIEW_STATUS_PENDING)

        save_correction("pf", "sf", "User fixed text")
        save_correction("pf", "sf", "Final corrected text")
        r = get_source_review("pf", "sf")
        self.assertEqual(len(r.correction_history), 2)
        self.assertEqual(r.original_text, "OCR errors here")

        self.assertEqual(len(get_verified_texts("pf")), 0)
        confirm_review("pf", "sf")
        v = get_verified_texts("pf")
        self.assertEqual(len(v), 1)
        self.assertEqual(v[0]["text"], "Final corrected text")

    def test_high_confidence_skips_review(self):
        rec = {
            "source_id": "sh", "file_name": "resume.pdf",
            "text": "Perfect text", "confidence": 0.98,
            "method": "gemini", "is_ocr": False,
            "is_low_confidence_ocr": False,
            "warnings": [], "pages": [],
            "status": SOURCE_STATUS_EXTRACTED,
        }
        r = get_or_create_review("ph", "sh", rec)
        self.assertTrue(r.is_verified)
        self.assertFalse(r.requires_review)

    def test_reject_excludes_from_evidence(self):
        rec = {
            "source_id": "sr", "file_name": "broken.pdf",
            "text": "garbled", "confidence": 0.2,
            "method": "pdf_ocr", "is_ocr": True,
            "is_low_confidence_ocr": True,
            "warnings": [], "pages": [],
            "status": SOURCE_STATUS_NEEDS_REVIEW,
        }
        get_or_create_review("pr", "sr", rec)
        reject_review("pr", "sr")
        self.assertEqual(len(get_verified_texts("pr")), 0)


if __name__ == "__main__":
    unittest.main()

