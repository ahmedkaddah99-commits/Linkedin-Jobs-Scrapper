# Profile overview correction ? October 12, 2026

The previous release simplified the form but did not reproduce the supplied
Jobright video’s profile overview and section-editing interaction.

`/profile` now displays personal details, education, work experience, skills and
job preferences as a quiet document-style overview with Runr teal accents.
Edit actions open a native modal right drawer. Fill profile opens the completion
popup; Jobs retains its inline completion popup and gains an explicit overview link.
Both editors use existing authenticated settings/preferences endpoints and refresh
saved values. Resume upload remains on the existing documents endpoint.
No new demographic questionnaire or backend schema is introduced.

Validation: frontend unit tests, lint/build, focused backend tests, desktop/mobile
overview edit/save/reload and popup completion/error browser checks.
Deployment uses the immutable frontend release script with rollback and a serialized
nginx switch. Existing unrelated checkout edits are excluded from this release.
