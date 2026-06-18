from __future__ import annotations

import io
from pathlib import Path
from typing import Any


_IMAGE_SUFFIXES = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
_PLAIN_TEXT_SUFFIXES = {".csv", ".json", ".log", ".md", ".rtf", ".text", ".txt", ".xml", ".yaml", ".yml"}


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return ""


def _extract_docx_text(data: bytes) -> str:
    try:
        from docx import Document

        document = Document(io.BytesIO(data))
        paragraphs = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
        table_rows = [
            " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            for table in document.tables
            for row in table.rows
        ]
        return "\n".join(paragraphs + [row for row in table_rows if row]).strip()
    except Exception:
        return ""


def _extract_xlsx_text(data: bytes) -> str:
    try:
        from openpyxl import load_workbook

        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        lines: list[str] = []
        for worksheet in workbook.worksheets:
            lines.append(worksheet.title)
            for row in worksheet.iter_rows(values_only=True):
                values = [str(value).strip() for value in row if value not in (None, "")]
                if values:
                    lines.append(" | ".join(values))
        return "\n".join(lines).strip()
    except Exception:
        return ""


def _ocr_image(image: Any) -> str:
    import pytesseract

    return str(pytesseract.image_to_string(image) or "").strip()


def _extract_image_text(data: bytes) -> str:
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as image:
            return _ocr_image(image)
    except Exception:
        return ""


def _extract_pdf_text(data: bytes) -> tuple[str, str]:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        native_text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        if native_text:
            return native_text, "pdf_native"
    except Exception:
        pass

    try:
        import fitz
        from PIL import Image

        document = fitz.open(stream=data, filetype="pdf")
        pages = []
        for page in document:
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            pages.append(_ocr_image(image))
        return "\n".join(page for page in pages if page).strip(), "pdf_ocr"
    except Exception:
        return "", "none"


def extract_document_text(filename: str, data: bytes) -> dict[str, Any]:
    suffix = Path(filename or "").suffix.lower()
    warnings: list[str] = []
    text = ""
    method = "none"

    if suffix == ".docx":
        text, method = _extract_docx_text(data), "docx"
    elif suffix == ".pdf":
        text, method = _extract_pdf_text(data)
    elif suffix in _IMAGE_SUFFIXES:
        text, method = _extract_image_text(data), "image_ocr"
    elif suffix == ".xlsx":
        text, method = _extract_xlsx_text(data), "xlsx"
    elif suffix in _PLAIN_TEXT_SUFFIXES or not suffix:
        text, method = _decode_text(data), "plain_text"
    else:
        decoded = _decode_text(data)
        if decoded and "\x00" not in decoded:
            text, method = decoded, "plain_text_fallback"

    if not text:
        if suffix in _IMAGE_SUFFIXES or suffix == ".pdf":
            warnings.append("OCR produced no text. Verify that Pillow, pytesseract, PyMuPDF, and Tesseract OCR are installed.")
        else:
            warnings.append(f"No text extractor is available for '{suffix or 'unknown'}' files.")
    return {"text": text.strip(), "char_count": len(text.strip()), "method": method, "warnings": warnings}


def create_word_companion_bytes(text: str, *, title: str = "") -> bytes:
    try:
        from docx import Document
    except Exception as exc:
        raise RuntimeError("python-docx is required to create Word CV companions.") from exc

    document = Document()
    if title:
        document.core_properties.title = title
    for line in str(text or "").splitlines():
        document.add_paragraph(line)
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


def extraction_metadata(extraction: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_text": str(extraction.get("text") or ""),
        "source_char_count": int(extraction.get("char_count") or 0),
        "text_extraction": {
            "method": str(extraction.get("method") or "none"),
            "warnings": list(extraction.get("warnings") or []),
        },
    }


__all__ = ["create_word_companion_bytes", "extract_document_text", "extraction_metadata"]
