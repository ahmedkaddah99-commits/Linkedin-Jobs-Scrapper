# AA-212 immutable application-package baseline

Status: implemented as a backend-domain and serialization extension. No
browser filling, transport handler, UI, database schema, or application
package v2 was added.

## Package contents

Repository-confirmed: `backend/domain/application_package.py` defines the
immutable nested records `ApplicationPackageCandidate`,
`ApplicationPackageExperience`, `ApplicationPackageBullet`,
`ApplicationPackageEducation`, and `ApplicationPackageFact`. `ApplicationPackage`
now carries candidate contact fields, experiences, education, skills,
languages, `standard_answers`, document references, package `version`, and
section-level `content_hashes`. `ApplicationPackageDocumentRef` retains
document metadata and its existing `sha256_hex` field.

Repository-confirmed: `ApplicationPackage.to_dict`, `from_payload`, and
`new_application_package` serialize and restore these sections. The existing
payload store remains the persistence boundary: `backend/application/
assisted_apply_package_service.py` stores the serialized package in the
existing payload JSON path; no migration or new table was introduced.

## Approval, hashing, and version transitions

Repository-confirmed: `ApplicationPackage.compute_content_hashes` hashes
canonicalized content sections, excluding nested hash fields from the
package-level digest. `refresh_content_hashes` records those hashes and
`assert_content_hashes` rejects tampered content. `mark_approved` records the
approval time and a package-wide approved-content hash. The service invokes
`mark_approved` in `AssistedApplyPackageService.bind_package` before producing
the bound payload.

Repository-confirmed state transitions:

1. A created v1 package can be populated and its section hashes refreshed.
2. Approval records `approved_at` and `approved_content_hash`; binding and
   consumed states also make replacement unavailable.
3. `replace_content` rejects changes after approval/binding/consumption.
4. `new_version` copies the package, increments `version`, clears approval and
   binding state, and reparses/revalidates the new content. This is a new
   package revision, not an in-place edit.

Approved tailored bullet text is preserved by `ApplicationPackageBullet`:
when approved, `text` must equal `approved_text`; serialization does not
normalize or rewrite it. Source experience ID, stable bullet/provenance ID,
selected CV version, and generation provenance are explicit fields on the
experience/bullet records.

## Deterministic precedence and safety

Repository-confirmed: `resolve_approved_value` applies exactly this order:
approved job-specific value, approved structured selected-CV value, confirmed
Career Memory value, then `unresolved`. Unapproved or empty candidates are
skipped; no fallback invents a value. The resolver returns source and
provenance, and `sensitive=True` always sets `requires_review`.

Repository-confirmed: `ApplicationPackageAnswer.from_payload` cannot clear
the review gate for personal, demographic, or legal answers, even when the
payload says `approved: true` and `requires_review: false`. Standard answers
are therefore explicit approved records, not generated browser values.

Proposed boundary retained: `to_extension_payload` remains the existing
minimal legacy browser payload and does not expose the new structured sections
or add filling behavior. Browser orchestration remains reserved for later
tickets.

## v1 compatibility and evidence

Repository-confirmed: `ApplicationPackage.from_payload` defaults absent new
sections and hashes safely for legacy payloads. Legacy experiences without a
source ID and legacy string bullets remain readable; they receive reduced
provenance confidence and no fabricated IDs. New identified records retain
full provenance. Existing answer/document/package fields remain compatible.

Tests: `tests/test_aa03_application_package.py` covers round-trip hashes and
provenance, exact approved bullet text, approval-time mutation rejection and
new-version creation, deterministic precedence, sensitive-answer review
gating, and a v1 payload with legacy experience/bullet data. Existing package
binding and document-grant tests remain unchanged by AA-212 behavior.

Limitations: the browser-facing protocol does not consume these new sections;
no live ATS submission or browser mutation is part of this ticket. Content
hashes provide tamper detection at parse/approval boundaries; callers must use
`replace_content`/`new_version` rather than directly assigning mutable package
attributes.
