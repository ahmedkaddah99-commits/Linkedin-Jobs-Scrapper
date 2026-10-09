# Assisted Apply workspace API and release notes

Extension version: **0.3.1**. API implementation: `backend/api/routes/assisted_apply_workspace.py`, registered by the existing Assisted Apply package route module.

All workspace operations are body-bearing POSTs under `/v1/assisted-apply/extension/workspace/`. They require an active extension session, exact extension origin, and Runr Pro access. Tokens remain in the service worker. Request objects reject unknown keys. Library/document responses expose no storage keys or filesystem paths.

| Action | Body | Result |
|---|---|---|
| `library` | `{}` | `documents: [{id,name,role,updatedAt}], answers: [{question,text}]` |
| `document` | `document_id` | Owned, export-ready PDF/DOCX bytes as base64 plus ID and filename, maximum 20 MB |
| `draft` | `kind: cv/cover_letter/answer`, `description`, `question`, `instructions` | Editable plain-text draft from confirmed server-side profile facts |
| `save-document` | `kind: cv/cover_letter`, `name`, `text` | Reviewed DOCX saved in existing candidate assets; fixed asset ID returned |
| `save-answer` | `question`, `text` | Reviewed reusable answer; exact question replaces its prior saved version |
| `report` | `description`, `hostname`, `provider`, `role` | Durable account report plus `issue_…` receipt |

`GET /v1/assisted-apply/support-reports` requires admin authentication and returns the report inbox with account IDs. It does not restore retired admin dashboards or users APIs. No email delivery is configured.

Asset downloads reuse existing ownership/export resolvers. Private assets and assets not marked for applications are excluded. Saved reviewed answers are kept separate from automatic profile facts; they are copied explicitly. Selection is scoped to the exact application URL in the tab's session. Drafts remain mounted when switching in-page tabs, and attachment rechecks the application URL after downloading. Existing attachments are preserved unless the candidate selects replacement.

## Release dependency

Release the new backend module and its registration in `assisted_apply_packages.py` together with extension 0.3.1. Existing `DEEPSEEK_API_KEY`, object storage, and account metadata storage are reused. No schema migration, new secret, or new extension permission is needed. Generation runs synchronously with a bounded provider timeout; unavailable service responses remain retryable in the panel.

Production API deployment is not part of the local verification recorded here. An extension-only reload against an older API will show an error on the new workspace operations. Profile copying, existing package review, and local document attachment remain available independently.

## Verification

- `tests/test_assisted_apply_workspace_routes.py` and existing package route tests: 11 passed. Includes real local object storage, real DOCX bytes, owned library retrieval, cross-account denial, private-file exclusion, strict inputs, reviewed-answer persistence, receipt persistence, and admin inbox gating.
- Focused extension unit checks: six passed across four files.
- Expanded Chromium scenario: saved document selection/attachment, existing-file preservation/replacement, resume and cover-letter generation/edit/save/attach, tab-switch draft preservation, answer draft/reuse, support receipt, and existing navigation passed.
- TypeScript, production packaging, manifest and boundary checks passed for 0.3.1.
- Required API/CLI regression suite (`test_backend_api`, `test_customer_route_surface`, `test_workspace_runner`, `test_phase_a_routes`): 129 tests and 19 subtests passed. Five dependency deprecation warnings were reported.

Tests use sanitized fixtures and mock model responses. They do not assert live ATS support or production generation availability.
