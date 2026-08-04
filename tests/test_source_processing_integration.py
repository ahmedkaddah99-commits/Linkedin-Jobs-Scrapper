"""Integration tests for local document extraction and optional DeepSeek structuring."""

from __future__ import annotations

import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz

from backend.capabilities.source_processing.extraction import (
    build_source_processing_summary,
    process_source,
    process_source_bytes,
    run_source_processing_pipeline,
)
from backend.domain.source_processing import (
    SOURCE_STATUS_EXTRACTED,
    SOURCE_STATUS_FAILED,
)


class TestSourceProcessingIntegration(unittest.TestCase):
    @staticmethod
    def _deepseek_result(text: str) -> dict:
        return {
            "text": text,
            "char_count": len(text),
            "method": "deepseek",
            "provider": "deepseek",
            "model": "deepseek-chat",
            "confidence": 0.92,
            "status": "ready",
            "warnings": [],
            "pages": [],
            "layout_sections": [],
            "experience_details": [],
            "evidence_items": [],
        }

    @staticmethod
    def _tmp(suffix: str, data: bytes) -> str:
        fd, path = tempfile.mkstemp(suffix=suffix)
        os.write(fd, data)
        os.close(fd)
        return path

    @staticmethod
    def _pdf_bytes(text: str = "Searchable PDF content") -> bytes:
        document = fitz.open()
        page = document.new_page()
        page.insert_text((72, 72), text)
        data = document.tobytes()
        document.close()
        return data

    def test_text_is_extracted_locally_then_structured_by_deepseek(self):
        deepseek_result = self._deepseek_result("Alice\nOperations Analyst\nAutomated reporting.")
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}), patch(
            "backend.profiles.deepseek_extraction.extract_with_deepseek",
            return_value=deepseek_result,
        ) as deepseek, patch(
            "backend.profiles.gemini_extraction.extract_with_gemini",
            side_effect=AssertionError("Gemini must not be called by source processing"),
        ):
            path = self._tmp(".txt", b"Alice\nOperations Analyst\nAutomated reporting.")
            try:
                record = process_source("text-1", path)
            finally:
                Path(path).unlink(missing_ok=True)

        self.assertEqual(record.status, SOURCE_STATUS_EXTRACTED)
        self.assertEqual(record.provider, "deepseek")
        self.assertEqual(record.model, "deepseek-chat")
        deepseek.assert_called_once()

    def test_docx_uses_local_text_before_deepseek(self):
        from docx import Document

        document = Document()
        document.add_paragraph("Acme Corp Operations Analyst 2020-2023")
        buffer = io.BytesIO()
        document.save(buffer)
        deepseek_result = self._deepseek_result("Acme Corp Operations Analyst 2020-2023")
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}), patch(
            "backend.profiles.deepseek_extraction.extract_with_deepseek",
            return_value=deepseek_result,
        ) as deepseek:
            record = process_source_bytes("docx-1", "resume.docx", buffer.getvalue())

        self.assertEqual(record.status, SOURCE_STATUS_EXTRACTED)
        self.assertEqual(record.provider, "deepseek")
        deepseek.assert_called_once()
        self.assertIn("Acme Corp", deepseek.call_args.args[1])

    def test_pdf_without_provider_uses_local_extraction(self):
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": ""}), patch(
            "backend.profiles.gemini_extraction.extract_with_gemini",
            side_effect=AssertionError("Gemini must not be called by source processing"),
        ):
            record = process_source_bytes("pdf-1", "supporting.pdf", self._pdf_bytes())

        self.assertEqual(record.status, SOURCE_STATUS_EXTRACTED)
        self.assertEqual(record.provider, "")
        self.assertEqual(record.method, "pdf_native")
        self.assertIn("Searchable PDF content", record.text)

    def test_deepseek_failure_returns_local_extraction(self):
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}), patch(
            "backend.profiles.deepseek_extraction.extract_with_deepseek",
            side_effect=RuntimeError("DeepSeek unavailable"),
        ), patch(
            "backend.profiles.gemini_extraction.extract_with_gemini",
            side_effect=AssertionError("Gemini must not be called by source processing"),
        ):
            record = process_source_bytes("fallback-1", "notes.txt", b"Local fallback extraction")

        self.assertEqual(record.status, SOURCE_STATUS_EXTRACTED)
        self.assertEqual(record.provider, "")
        self.assertIn("Local fallback", record.text)

    def test_pipeline_and_summary_use_background_worker_extraction_contract(self):
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": ""}):
            path = self._tmp(".txt", b"Pipeline content")
            try:
                results = run_source_processing_pipeline([{"source_id": "p1", "file_path": path}])
            finally:
                Path(path).unlink(missing_ok=True)

        self.assertEqual(len(results), 1)
        summary = build_source_processing_summary(results)
        self.assertEqual(summary["total_sources"], 1)
        self.assertEqual(summary["extracted"], 1)

    def test_missing_source_is_failed_without_provider_call(self):
        record = process_source("missing", "does-not-exist.txt")
        self.assertEqual(record.status, SOURCE_STATUS_FAILED)
        self.assertIn("No such file", record.error)


if __name__ == "__main__":
    unittest.main()
