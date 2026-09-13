# CV Language Section Parser Report

Date: 2026-05-30

This report documents the work done on CV language-section extraction and preview rendering after language entries were incorrectly shown as standalone unknown/custom sections.

## Overall Status

Implemented and verified.

The CV parser now keeps language entries in the structured `languages` field instead of rendering them as separate empty custom sections. Existing uploaded CV assets that already stored language entries as empty custom sections are also corrected at preview time, so a re-upload should not be required for that specific issue.

## Original Problem

In the workspace CV preview, language entries such as:

```text
Arabic - Native
English - C1
German - B1/B2
```

were being displayed twice:

- First as separate custom/unknown sections with no details.
- Then correctly inside the `Languages` block.

The user-facing result was confusing because the language data was already structured correctly below, but the preview still showed extra empty sections above it.

## Root Cause

The CV section classifier treated short title-like lines as custom section headings. Language proficiency lines often look like headings because they are short and title-cased:

```text
Arabic - Native
English - C1
German - B1/B2
```

Because of that, these lines were moved into `custom_sections` instead of staying under the `languages` section.

## What Changed

### 1. Language entry detection

Added language-entry detection to both CV parsing paths:

- Upload-time profile extraction.
- Workspace document preview extraction.

The parser now recognizes language-looking lines by checking for known language aliases and proficiency markers such as CEFR levels or native/fluent-style labels.

Examples now handled:

```text
Arabic - Native
English - C1
German - B1/B2
Arabisch - Muttersprache
Englisch - C1
Deutsch - B1/B2
```

### 2. Custom section guard

The custom-section detector now rejects language-entry lines before deciding that a short title-like line is a custom section heading.

This prevents language entries from becoming empty custom sections in the first place.

### 3. Languages section preservation

When the parser is inside a `Languages` section, language-looking lines are explicitly kept in that section.

This keeps the intended structure:

```json
{
  "languages": ["Arabic - Native", "English - C1", "German - B1/B2"],
  "custom_sections": []
}
```

### 4. Existing asset repair in preview

Some previously uploaded CV assets may already have parsed metadata like:

```json
{
  "custom_sections": [
    { "heading": "Arabic - Native", "lines": [] }
  ]
}
```

The workspace preview now detects these empty language-like custom sections, moves them back into `languages`, and does not render them as custom sections.

### 5. Localized language headings

The parser now recognizes common localized language section headings:

- `Languages`
- `Language Skills`
- `Spoken Languages`
- `Language Proficiency`
- `Sprachen`
- `Sprachkenntnisse`
- `Fremdsprachen`
- `Sprachkompetenzen`
- `Langues`
- `Competences linguistiques`
- `Competences linguistiques` with accented spelling
- `Idiomas`
- `Conocimientos de idiomas`
- `Lingue`
- `Competenze linguistiche`

### 6. Inline language lists

The parser now handles inline language-section rows such as:

```text
Languages: Arabic - Native, English - C1, German - B1/B2
Sprachkenntnisse: Englisch - C1; Deutsch - B1/B2; Arabisch - Muttersprache
Idiomas: English - C1, German - B1/B2, Arabic - Native
```

These are split into individual language entries.

## Files Changed

- `backend/profiles/cv_profile_extraction.py`
  - Added localized language header patterns.
  - Added inline language-header parsing.
  - Added language-entry detection before custom-section classification.
  - Preserved language entries while inside the `languages` section.

- `backend/api/server.py`
  - Added the same localized and inline language parsing to workspace CV preview parsing.
  - Added repair behavior for existing empty custom sections that are actually language entries.
  - Kept preview output aligned with uploaded profile extraction.

- `tests/test_backend_api.py`
  - Updated the structured CV upload test to include `Arabic - Native`.
  - Added regression coverage for old parsed assets with language entries stored as empty custom sections.
  - Added regression coverage for localized and inline language formats.

## Supported Formats After This Change

The parser now supports these language layouts:

```text
Languages
Arabic - Native
English - C1
German - B1/B2
```

```text
Sprachen
Arabisch - Muttersprache
Englisch - C1
Deutsch - B1/B2
```

```text
Language Skills: Arabic - Native; English - C1; German - B1/B2
```

```text
Sprachkenntnisse: Englisch - C1; Deutsch - B1/B2; Arabisch - Muttersprache
```

```text
Idiomas: English - C1, German - B1/B2, Arabic - Native
```

## Verification

Ran syntax checks:

```text
python -m py_compile backend\profiles\cv_profile_extraction.py backend\api\server.py tests\test_backend_api.py
```

Ran focused backend regression tests:

```text
python -m unittest tests.test_backend_api.BackendApiTests.test_cv_upload_returns_structured_profile_fields_for_settings_population tests.test_backend_api.BackendApiTests.test_workspace_cv_preview_does_not_render_language_entries_as_custom_sections tests.test_backend_api.BackendApiTests.test_cv_language_extraction_accepts_localized_and_inline_formats
```

Result:

```text
Ran 3 tests
OK
```

Also ran direct parser checks for:

- German heading block format.
- German inline format.
- Spanish heading inline format.

All returned the expected `languages` arrays.

## Runtime Status

The local API was restarted after the change and returned a healthy response on:

```text
http://127.0.0.1:8000/health
```

The Vite UI remained available on:

```text
http://127.0.0.1:4173
```

## Remaining Limits

This hardens common text-based CV formats, but it does not solve every possible CV extraction case.

Known limits:

- Image-only or scanned PDFs still need OCR.
- Very table-heavy PDFs may extract text in a poor order before the parser sees it.
- Unknown language names outside the existing language alias list may not be recognized as language entries.
- Highly decorative CV layouts may still require manual review if text extraction produces unusual line breaks.

## Recommended Next Step

Add OCR support or a document-text extraction fallback for scanned PDFs. That is separate from language-section parsing and would improve the whole CV ingestion pipeline, not just the languages field.
