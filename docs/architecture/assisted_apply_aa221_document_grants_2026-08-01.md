# Assisted Apply AA-221 — session-bound document grants and upload intents

Status: implemented on `deployment/render-turso-r2`.

The existing one-time, session-bound, hash-verified document grant is now
bound to an adapter-declared upload-field intent. Greenhouse and Lever declare
exact resume, cover-letter, and supporting-document intents from stable upload
control attributes. The browser requests a grant with the package document,
adapter, and declared intent; the backend validates the immutable package
document, object bytes, MIME/filename pair, adapter intent, size, and hash.

Each retry requests a new grant. Consumed, expired, session-mismatched,
wrong-intent, and content-mismatched grants fail with sanitized errors. Grant
records contain hashes and metadata only; raw document bytes and grant tokens
are not logged or persisted in extension session storage.

The content runner requires exactly one inspected file control with the
declared intent, then verifies retained filename/type and browser validity.
Zero or multiple matching controls remain rejected/manual; document kind is
never used to guess a DOM target. Existing occupied portal/user files remain
preserved. Upload code does not navigate or submit.

Evidence:

- Backend grant lifecycle and migration: `backend/application/assisted_apply_package_service.py`, `backend/repositories/sqlite_migrations.py`, and `backend/api/routes/assisted_apply_packages.py`.
- Adapter declarations and exact target verification: `packages/ats-core/src/index.ts`.
- Extension grant binding and sanitized dispatch: `apps/browser-extension/entrypoints/background.ts` and `application-form.ts`.
- Unit coverage: `apps/browser-extension/tests/unit/aa221-upload-intent.test.ts`.
- Backend expiry, hash mismatch, consumption, retry, and forged-intent coverage: `tests/test_assisted_apply_document_grants.py`.
- Fixture coverage: `apps/browser-extension/tests/e2e/assisted-apply.spec.ts`.

Limitations: closed shadow-root, cross-origin, unsupported, and non-declared
upload widgets remain manual boundaries. No ATS navigation or final submission
is part of this ticket.
