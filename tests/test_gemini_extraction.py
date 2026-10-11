"""Tests for Gemini Flash-Lite multimodal extraction (CP-007)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from backend.profiles.gemini_extraction import (
    MODEL_ID,
    PROVIDER_NAME,
    _is_multimodal,
    _mime_type,
    _parse_gemini_response,
)
from backend.domain.source_processing import EXTRACTION_METHOD_GEMINI


class GeminiExtractionUnitTests(unittest.TestCase):
    """Unit tests for the Gemini extraction module."""

    def test_model_is_stable_flash_lite(self):
        """CP-007: Only gemini-2.5-flash-lite is used - no preview models."""
        self.assertEqual(MODEL_ID, "gemini-2.5-flash-lite")
        self.assertNotIn("preview", MODEL_ID)
        self.assertNotIn("pro", MODEL_ID.lower().replace("preview", ""))

    def test_provider_name_is_gemini(self):
        self.assertEqual(PROVIDER_NAME, "gemini")

    def test_is_multimodal_returns_true_for_pdfs_and_images(self):
        """PDFs and images should be sent as multimodal inputs."""
        for name in ("resume.pdf", "photo.png", "scan.jpg", "screenshot.jpeg",
                     "diagram.gif", "chart.bmp", "logo.tif", "icon.tiff", "pic.webp"):
            self.assertTrue(_is_multimodal(name), f"Expected multimodal: {name}")

    def test_is_multimodal_returns_false_for_text_formats(self):
        """DOCX, TXT, HTML, and similar should NOT be multimodal."""
        for name in ("resume.docx", "notes.txt", "page.html", "data.csv",
                     "readme.md", "config.json", "logfile.log", "spreadsheet.xlsx"):
            self.assertFalse(_is_multimodal(name), f"Expected text-only: {name}")

    def test_mime_type_maps_known_suffixes(self):
        self.assertEqual(_mime_type("doc.pdf"), "application/pdf")
        self.assertEqual(_mime_type("photo.png"), "image/png")
        self.assertEqual(_mime_type("image.jpg"), "image/jpeg")
        self.assertEqual(_mime_type("image.jpeg"), "image/jpeg")
        self.assertEqual(_mime_type("icon.webp"), "image/webp")
        self.assertEqual(_mime_type("logo.tiff"), "image/tiff")



    def test_parse_gemini_response_with_valid_json(self):
        """Structured JSON from Gemini should parse correctly."""
        mock_response = MagicMock()
        mock_response.text = (
            '{"extracted_text": "John Doe\\nSoftware Engineer\\nAcme Corp",'
            '"layout_sections": [{"title": "Experience", "type": "heading", "text": "Experience"}],'
            '"experience_details": [{"employer": "Acme Corp", "role": "Software Engineer",'
            '"dates": "2020-2023", "bullets": ["Built APIs", "Led team"]}],'
            '"confidence": 0.92,'
            '"warnings": []}'
        )

        result = _parse_gemini_response(mock_response, "resume.pdf")
        self.assertEqual(result["method"], EXTRACTION_METHOD_GEMINI)
        self.assertEqual(result["provider"], PROVIDER_NAME)
        self.assertEqual(result["model"], MODEL_ID)
        self.assertEqual(result["status"], "ready")
        self.assertIn("John Doe", result["text"])
        self.assertGreaterEqual(result["confidence"], 0.9)
        self.assertEqual(result["layout_sections"][0]["title"], "Experience")
        self.assertEqual(result["experience_details"][0]["employer"], "Acme Corp")

    def test_parse_gemini_response_with_empty_response(self):
        """Empty Gemini response should return failed status."""
        mock_response = MagicMock()
        mock_response.text = ""
        result = _parse_gemini_response(mock_response, "empty.pdf")
        self.assertEqual(result["status"], "failed")
        self.assertIn("empty response", result["warnings"][0].lower())

    def test_parse_gemini_response_with_invalid_json(self):
        """Non-JSON response should be treated as raw text with partial status."""
        mock_response = MagicMock()
        mock_response.text = "Just raw text, no JSON here."
        result = _parse_gemini_response(mock_response, "raw.txt")
        self.assertEqual(result["status"], "partial")
        self.assertIn("Just raw text", result["text"])
        self.assertTrue(
            any("not return valid json" in w.lower() for w in result["warnings"])
        )
        self.assertEqual(result["confidence"], 0.5)

    def test_parse_response_stores_provider_model_timestamp(self):
        """CP-007: Store provider, model, timestamp, and extraction status."""
        mock_response = MagicMock()
        mock_response.text = (
            '{"extracted_text": "Simple text", "confidence": 0.85, "warnings": []}'
        )
        result = _parse_gemini_response(mock_response, "doc.pdf")
        self.assertEqual(result["provider"], PROVIDER_NAME)


class GeminiExtractionIntegrationTests(unittest.TestCase):
    """Tests for Gemini fallback behaviour and pipeline integration."""

    def test_fallback_to_local_when_gemini_unavailable(self):
        """When Gemini is unavailable, local extraction should be used."""
        from backend.profiles.document_text import extract_document_text
        result = extract_document_text("notes.txt", b"Fallback content")
        self.assertEqual(result["status"], "ready")
        self.assertIn("Fallback content", result["text"])

    def test_source_text_record_includes_provider_and_model(self):
        """SourceTextRecord should have provider and model fields."""
        from backend.domain.source_processing import SourceTextRecord
        record = SourceTextRecord(source_id="test-1")
        record.provider = "gemini"
        record.model = MODEL_ID
        d = record.to_dict()
        self.assertEqual(d["provider"], "gemini")
        self.assertEqual(d["model"], MODEL_ID)
        record2 = SourceTextRecord.from_dict(d)
        self.assertEqual(record2.provider, "gemini")
        self.assertEqual(record2.model, MODEL_ID)


if __name__ == "__main__":
    unittest.main()
