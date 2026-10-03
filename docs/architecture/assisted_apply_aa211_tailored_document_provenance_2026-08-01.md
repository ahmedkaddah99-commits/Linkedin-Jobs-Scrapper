# AA-211 tailored-document provenance baseline

Status: implemented in the existing tailored CV pipeline; no browser filling,
bullet generation, or application-package v2 behavior was added.

## Propagation path

`backend/capabilities/tailored_documents/cv_structuring.py` preserves
`source_experience_id` through structured normalization, deduplication, and
the final `cv_professional_experience` record. Bullet mappings preserve
`approved_text` and existing metadata. When a source experience ID exists,
`backend/capabilities/tailored_documents/provenance.py` assigns a deterministic
`bullet_id` from source ID, bullet position, and approved text, and adds the
source experience ID to the bullet mapping.

`backend/adapters/stage_adapters.py` already captures immutable profile/CV
versions and generation provenance. AA-211 copies those existing references
onto the generated record and each identified experience/bullet through
`propagate_tailored_provenance`: selected CV asset/version, generation
provenance ID/run/job/pipeline/fingerprint/renderer, and any existing package
version are retained as data. No schema or application-package v2 change is
made.

## Text and legacy behavior

Approved bullet text is copied without normalization into both `approved_text`
and the renderer-facing `text` field. Existing document renderers read the
renderer-facing text and continue producing the same visible text/layout. The
structured text renderers also understand bullet mappings, so metadata is never
rendered as Python dictionary text.

Records without source experience IDs remain readable. They receive
`provenance_confidence: "reduced"` and record-level
`provenance_status: "legacy_reduced_confidence"`; legacy string bullets remain
strings and are not given fabricated IDs. Identified records receive
`provenance_confidence: "full"` and deterministic bullet IDs.

## Evidence

`tests/test_tailored_document_generation.py` covers source-ID propagation,
stable bullet IDs, byte-preserving approved text, selected CV/package versions,
generation provenance, JSON serialization, explicit legacy fallback, and DOCX
render regression. Existing tailored-document tests continue to cover the
renderer's normal and malformed-experience paths.
