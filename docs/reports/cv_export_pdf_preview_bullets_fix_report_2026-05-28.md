# CV Export, Bullet Points, and Experience Fix Report - 2026-05-28

## Simple explanation

The exported CV was not matching what you expected because the AI-generated CV text and the structured CV data got out of sync.

The AI had generated role-specific experience bullets in the stored `tailored_cv` text, but the structured field used by the DOCX/PDF renderer, `cv_professional_experience`, had empty `bullets` arrays for several jobs. That is why the exported CV showed job headers but no experience under each job.

There was also a rendering problem: the DOCX renderer used Word's hidden `List Bullet` style. Some exports/viewers do not expose that as an actual bullet character. The new renderer writes a real visible bullet character (`•`) into the document text.

The current generated CV files have been repaired and regenerated. The tracker should now download the PDF version of the tailored CV, and the CV should contain the same AI-tailored experience bullets that were already present in the generated tailored text.

## What I changed

- Fixed the CV parser so it understands `Experience`, `Work Experience`, `Professional Experience`, split date lines, and Word-style bullet paragraphs that do not include a visible bullet character in extracted text.
- Added recovery logic so if `cv_professional_experience` has empty bullets, the system recovers the bullets from the AI-generated `tailored_cv` text instead of exporting blank experience sections.
- Preserved the richer AI-generated role headers when the fallback parser only had weak headers like company/location/date.
- Changed DOCX rendering to write visible `•` bullet characters instead of relying on Word list styling.
- Added a renderer fingerprint so cached CV files are regenerated when the renderer/content changes, instead of keeping stale DOCX/PDF files.
- Repaired the current generated files in `stage4_documents.json`, `stage4_checkpoint.json`, and the matching files under `generated_docs/`.

## Technical details

Changed files:

- `backend/capabilities/tailored_documents/cv_structuring.py`
  - More robust experience extraction.
  - AI `tailored_cv` fallback recovery.
  - Structured `tailored_cv` text rebuilt after normalization.

- `backend/capabilities/tailored_documents/rendering.py`
  - Replaced Word `List Bullet` paragraphs with literal visible `•` bullet paragraphs.

- `backend/capabilities/tailored_documents/documents.py`
  - Added `CV_RENDERER_VERSION`.
  - Added `_cv_renderer_fingerprint(...)`.
  - Existing generated records now re-render DOCX/PDF when rendering/content is outdated.

- `tests/test_tailored_document_generation.py`
  - Added regression tests for plain `Experience` parsing.
  - Added regression test for recovering AI bullets when structured experience is empty.
  - Added regression test proving exported DOCX text contains a visible bullet prefix.

## Current data repair

I repaired the active generated outputs without calling the AI again. I used the already-stored AI-tailored CV text to refill the structured experience data.

Verification after repair:

- `stage4_documents.json`: 11 records, 0 records with empty experience bullets.
- `stage4_checkpoint.json`: 19 records, 0 records with empty experience bullets.
- Checked regenerated DOCX files for:
  - Product Marketing Manager (WebStorm) at JetBrains
  - Product Support Specialist at Bruker Corporation
  - Senior Product Manager, B2B at GetYourGuide

Each checked DOCX now contains role-specific experience lines under every job and visible `•` bullets.

## Verification commands

- `.\.venv\Scripts\python.exe -m pytest tests/test_tailored_document_generation.py -q`
- `.\.venv\Scripts\python.exe -m pytest tests/test_tailored_document_generation.py tests/test_backend_api.py::BackendApiTests::test_bulk_export_prefers_generated_cv_pdf_when_docx_is_also_selected tests/test_backend_api.py::BackendApiTests::test_documents_endpoint_bulk_export_and_candidate_assets tests/test_backend_api.py::BackendApiTests::test_ats_gate_blocks_final_cv_export_until_override_after_warning tests/test_backend_api.py::BackendApiTests::test_tracker_api tests/test_stage_adapters.py::StageAdapterTests::test_tailored_document_artifacts_emit_per_file_cv_entries_with_ats_metadata -q`
- `npm --prefix frontend run build`

Result:

- Backend targeted tests: passed.
- Frontend production build: passed.

## Important finding

The current root `user_config/cv_master.txt` is a very small placeholder-style CV using `Example GmbH`. Workspace-based tailored-document runs should keep using the selected workspace CV snapshot. If a local CLI run is started without the workspace CV override, it may use that placeholder file as the source CV.
