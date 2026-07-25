
import json, tempfile, unittest, os, io, struct, zlib
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.capabilities.source_processing.extraction import (
    process_source, process_source_bytes,
    run_source_processing_pipeline, build_source_processing_summary,
)
from backend.domain.source_processing import (
    SOURCE_STATUS_EXTRACTED, SOURCE_STATUS_FAILED,
    SOURCE_STATUS_NEEDS_REVIEW, SOURCE_STATUS_PROCESSING,
    EXTRACTION_METHOD_GEMINI, SourceTextRecord,
)

class TestSourceProcessingIntegration(unittest.TestCase):
    def _mock_response(self, text="Extracted text", confidence=0.92):
        j = json.dumps({"extracted_text": text, "layout_sections": [],
                         "experience_details": [], "confidence": confidence, "warnings": []})
        m = MagicMock()
        m.text = j
        return m

    def _tmp(self, suffix, data):
        fd, p = tempfile.mkstemp(suffix=suffix)
        os.write(fd, data)
        os.close(fd)
        return p


    # -- Multimodal: PDF/image via Gemini --
    def test_pdf_via_gemini_multimodal(self):
        mr = self._mock_response("John Doe, Software Engineer", 0.95)
        with patch("backend.profiles.gemini_extraction._build_client") as cb:
            c = MagicMock()
            cb.return_value = c
            c.models.generate_content.return_value = mr
            t = self._tmp(".pdf", b"%PDF-1.4 data")
            try:
                r = process_source("s1", t, allow_ocr=True)
            finally:
                Path(t).unlink(missing_ok=True)
        self.assertEqual(r.status, SOURCE_STATUS_EXTRACTED)
        self.assertEqual(r.method, EXTRACTION_METHOD_GEMINI)
        self.assertEqual(r.provider, "gemini")
        self.assertEqual(r.model, "gemini-2.5-flash-lite")
        self.assertIn("John Doe", r.text)
        self.assertGreaterEqual(r.confidence, 0.9)
        self.assertTrue(r.processed_at)
        self.assertTrue(len(r.pages) >= 1)

    def test_image_via_gemini_multimodal(self):
        mr = self._mock_response("Screenshot with Apply button", 0.88)
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
            t = self._tmp(".png", sig + ihdr + idat + iend)
            try:
                r = process_source("s2", t, allow_ocr=True)
            finally:
                Path(t).unlink(missing_ok=True)
        self.assertEqual(r.status, SOURCE_STATUS_EXTRACTED)
        self.assertEqual(r.method, EXTRACTION_METHOD_GEMINI)
        self.assertEqual(r.provider, "gemini")


    # -- Text formats parsed locally, sent to Gemini as text --
    def test_docx_parsed_then_gemini_text(self):
        mr = self._mock_response("Acme Corp Engineer 2020-2023", 0.90)
        with patch("backend.profiles.gemini_extraction._build_client") as cb:
            c = MagicMock()
            cb.return_value = c
            c.models.generate_content.return_value = mr
            from docx import Document
            buf = io.BytesIO()
            doc = Document()
            doc.add_paragraph("Acme Corp Engineer 2020-2023")
            doc.save(buf)
            t = self._tmp(".docx", buf.getvalue())
            try:
                r = process_source("s3", t, allow_ocr=True)
            finally:
                Path(t).unlink(missing_ok=True)
        self.assertEqual(r.status, SOURCE_STATUS_EXTRACTED)
        self.assertEqual(r.method, EXTRACTION_METHOD_GEMINI)
        self.assertIn("Acme Corp", r.text)

    def test_txt_sent_to_gemini_as_text(self):
        mr = self._mock_response("Resume: Skills Python, React, AWS", 0.93)
        with patch("backend.profiles.gemini_extraction._build_client") as cb:
            c = MagicMock()
            cb.return_value = c
            c.models.generate_content.return_value = mr
            t = self._tmp(".txt", b"Python, React, AWS")
            try:
                r = process_source("s4", t, allow_ocr=True)
            finally:
                Path(t).unlink(missing_ok=True)
        self.assertEqual(r.status, SOURCE_STATUS_EXTRACTED)
        self.assertEqual(r.method, EXTRACTION_METHOD_GEMINI)
        self.assertIn("Python", r.text)

    # -- Fallback: Gemini unavailable -> local extraction --
    def test_gemini_unavailable_falls_back_local(self):
        with patch("backend.profiles.gemini_extraction.extract_with_gemini",
                   side_effect=RuntimeError("API key not configured")):
            t = self._tmp(".txt", b"Fallback extraction")
            try:
                r = process_source("s5", t, allow_ocr=True)
            finally:
                Path(t).unlink(missing_ok=True)
        self.assertEqual(r.status, SOURCE_STATUS_EXTRACTED)
        self.assertNotEqual(r.method, EXTRACTION_METHOD_GEMINI)
        self.assertIn("Fallback", r.text)

    def test_gemini_returns_failed_status_falls_back(self):
        with patch("backend.profiles.gemini_extraction.extract_with_gemini") as gem:
            gem.return_value = {"text": "", "char_count": 0, "method": "gemini",
                                "provider": "gemini", "model": "gemini-2.5-flash-lite",
                                "confidence": 0.0, "status": "failed",
                                "warnings": [], "pages": [],
                                "extracted_at": "2026-01-01T00:00:00Z",
                                "layout_sections": [], "experience_details": []}
            t = self._tmp(".pdf", b"%PDF-1.4 fallback")
            try:
                r = process_source("s6", t, allow_ocr=True)
            finally:
                Path(t).unlink(missing_ok=True)
        self.assertNotEqual(r.method, EXTRACTION_METHOD_GEMINI)


    # -- process_source_bytes --
    def test_process_source_bytes_from_memory(self):
        mr = self._mock_response("From memory", 0.91)
        with patch("backend.profiles.gemini_extraction._build_client") as cb:
            c = MagicMock()
            cb.return_value = c
            c.models.generate_content.return_value = mr
            r = process_source_bytes("b1", "resume.pdf", b"%PDF-1.4 memory")
        self.assertEqual(r.source_id, "b1")
        self.assertEqual(r.method, EXTRACTION_METHOD_GEMINI)
        self.assertIn("From memory", r.text)

    def test_process_source_bytes_temp_cleanup(self):
        mr = self._mock_response("Temp cleanup", 0.89)
        with patch("backend.profiles.gemini_extraction._build_client") as cb:
            c = MagicMock()
            cb.return_value = c
            c.models.generate_content.return_value = mr
            r = process_source_bytes("b2", "notes.txt", b"cleanup test")
        self.assertEqual(r.status, SOURCE_STATUS_EXTRACTED)
        self.assertIn("Temp cleanup", r.text)

    # -- Pipeline and summary --
    def test_pipeline_multiple_sources(self):
        mr = self._mock_response("Pipeline", 0.87)
        with patch("backend.profiles.gemini_extraction._build_client") as cb:
            c = MagicMock()
            cb.return_value = c
            c.models.generate_content.return_value = mr
            t1 = self._tmp(".pdf", b"%PDF-1.4")
            t2 = self._tmp(".txt", b"text")
            try:
                results = run_source_processing_pipeline([{"source_id":"p1","file_path":t1},{"source_id":"p2","file_path":t2}])
            finally:
                Path(t1).unlink(missing_ok=True)
                Path(t2).unlink(missing_ok=True)
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r.method, EXTRACTION_METHOD_GEMINI)

    def test_summary_reflects_state(self):
        mr = self._mock_response("Summary", 0.94)
        with patch("backend.profiles.gemini_extraction._build_client") as cb:
            c = MagicMock()
            cb.return_value = c
            c.models.generate_content.return_value = mr
            t = self._tmp(".pdf", b"%PDF-1.4")
            try:
                s = build_source_processing_summary(run_source_processing_pipeline([{"source_id":"x","file_path":t}]))
            finally:
                Path(t).unlink(missing_ok=True)
        self.assertEqual(s["total_sources"], 1)
        self.assertEqual(s["extracted"], 1)
        self.assertIn("results", s)


    # -- Screenshot annotations --
    def test_screenshot_annotations(self):
        mr = self._mock_response("Screenshot: arrow to Submit button. Annotation: attach cover letter", 0.85)
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
            t = self._tmp(".png", sig + ihdr + idat + iend)
            try:
                r = process_source("ss", t, allow_ocr=True)
            finally:
                Path(t).unlink(missing_ok=True)
        self.assertEqual(r.method, EXTRACTION_METHOD_GEMINI)
        self.assertIn("cover letter", r.text.lower())

    # -- extraction_metadata updated --
    def test_extraction_metadata_has_provider_model(self):
        from backend.profiles.document_text import extraction_metadata
        ext = {"text":"t","char_count":1,"method":"gemini","provider":"gemini",
               "model":"gemini-2.5-flash-lite","status":"ready","confidence":0.95,
               "warnings":[],"pages":[{"page_number":1,"method":"gemini","status":"ready"}],
               "is_ocr":False,"is_low_confidence_ocr":False,
               "extracted_at":"2026-07-25T00:00:00Z",
               "layout_sections":[],"experience_details":[]}
        m = extraction_metadata(ext)
        tx = m["text_extraction"]
        self.assertEqual(tx["provider"], "gemini")
        self.assertEqual(tx["model"], "gemini-2.5-flash-lite")
        self.assertFalse(tx["is_ocr"])
        self.assertEqual(tx["extracted_at"], "2026-07-25T00:00:00Z")

if __name__ == "__main__":
    unittest.main()

