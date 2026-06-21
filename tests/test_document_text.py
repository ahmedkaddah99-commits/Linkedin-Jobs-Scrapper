import io
import unittest

from docx import Document

from backend.profiles.document_text import create_word_companion_bytes, extract_document_text, extraction_metadata


class DocumentTextTests(unittest.TestCase):
    def test_extracts_plain_text_and_builds_metadata(self):
        extraction = extract_document_text("notes.txt", b"Runr document text")

        self.assertEqual(extraction["text"], "Runr document text")
        self.assertEqual(extraction["method"], "plain_text")
        self.assertEqual(extraction_metadata(extraction)["source_char_count"], 18)

    def test_extracts_docx_tables_and_paragraphs(self):
        document = Document()
        document.add_paragraph("Candidate summary")
        table = document.add_table(rows=1, cols=2)
        table.cell(0, 0).text = "Skill"
        table.cell(0, 1).text = "Python"
        output = io.BytesIO()
        document.save(output)

        extraction = extract_document_text("resume.docx", output.getvalue())

        self.assertIn("Candidate summary", extraction["text"])
        self.assertIn("Skill | Python", extraction["text"])

    def test_word_companion_contains_extracted_text(self):
        companion = create_word_companion_bytes("First line\nSecond line", title="CV")
        document = Document(io.BytesIO(companion))

        self.assertEqual([paragraph.text for paragraph in document.paragraphs], ["First line", "Second line"])

    def test_unknown_binary_type_reports_warning(self):
        extraction = extract_document_text("archive.bin", b"\x00\x01\x02")

        self.assertEqual(extraction["text"], "")
        self.assertTrue(extraction["warnings"])

    def test_fast_pdf_extraction_skips_ocr_when_native_text_is_missing(self):
        extraction = extract_document_text("scan.pdf", b"%PDF-1.4\n", allow_ocr=False)

        self.assertEqual(extraction["text"], "")
        self.assertEqual(extraction["method"], "pdf_native")
        self.assertIn("Scanned PDFs need OCR", extraction["warnings"][0])


if __name__ == "__main__":
    unittest.main()
