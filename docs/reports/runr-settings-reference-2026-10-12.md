# Settings reference correction — 12 October 2026

Owner-directed correction of the first settings release. The October 12 Jobright
video guides the modal proportions, left menu, compact subscription card,
instant/digest alert rows and adjacent paid-duration/free-plan comparison.

- Removed the legacy profile card, full account editor, photo-upload controls and
  extension card from Login & Security. Compact rows open real Clerk account
  management; the native settings dialog closes first so it cannot cover Clerk.
- Removed Contact Support and its invented destination. Subscription refresh uses
  the existing authenticated billing endpoint and refreshes the session.
- Coming soon appears in pale yellow bordered boxes. Automatic emails and
  providers remain disabled. Pricing omits legacy runs, workspaces and credits;
  offer prices/IDs still come from the backend catalog.
- Customer messages omit provider configuration and raw payment error bodies.
  Public plan responses omit product IDs and environment-variable names.

Release `a8dd4735` was pushed and deployed to the serving frontend and API using
`deploy/deploy-settings-reference.sh`. Public frontend metadata matched the commit,
API readiness returned ready with SQLite/R2, and the live public catalog returned
two plans and three offers without provider configuration. API working directory
confirmed the same release. Rollback configuration was retained.

Validation: 198 frontend unit tests, ESLint, production build, eight focused
backend tests and desktop/mobile settings/pricing checks. Browser mocks verify
subscription refresh, offer selection, safe checkout errors, disabled email
controls, absence of legacy/support content, yellow badge styling, Escape and
focus restoration. Test teardown drains proxy routes to avoid an in-flight
version check failing after the context closes.

Payment setup is deferred by the owner. The existing test key can read the
legacy product catalog but lacks product-write scope; all three canonical Pro
product mappings are absent. A creation attempt was rejected with 403 and did
not create a product. No key, mapping, provider catalog or payment was changed.
This release does not establish working payment checkout, webhook delivery or a
live authenticated Clerk security flow. These require the later provider setup.
