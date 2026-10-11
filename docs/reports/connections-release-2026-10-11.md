# Connections release — 2026-10-11

Frontend production revision: `e0e4549652f1e6e94b96dfb8c32bd016b3f83cfc`.
Branch: `release/connections-2026-10-11`, based on the prior live revision
`96868ca039ca74ab4b3ee5d2da29d275993cc343` so the retired Render endpoint
correction remains present. Unfinished CV customization work is excluded.

## Delivered

- Connection navigation label with no dropdown arrow.
- Full-width directory with separate name, job title, company and strength.
- Combined name, job-title and company filters, applied before pagination.
- Add/edit fields for LinkedIn profile, job title, company, notes and strength.
- Independent note/strength metadata, import provenance and additional company
  records retained through the existing referral API.
- Conservative display repair for old joined names and removal of Message from
  imported dates. Updated extension extraction separates nested name/headline
  elements and excludes action text. Sync invalidates the directory cache.

## Verification

- 28 focused frontend/API utility tests passed on the release worktree.
- ESLint passed for modified frontend JavaScript/JSX.
- 3 extension parser tests passed after WXT type preparation.
- 2 existing referral API regression tests passed using Python 3.12.7.
- Desktop and mobile Playwright tests passed on an isolated build/port. They
  exercise combined filters, add/save payloads, profile/notes/strength fields,
  separate directory columns and absence of horizontal overflow.
- Production build passed on the VPS.
- Public `/refer` returns 200. Public release metadata reports the revision above.
- Served `ReferralsPage-C-bi8esP.js` and `index-BKXvj4El.css` hashes match the
  immutable build. API readiness passed; API and worker remain active.
- Read-only application of the display mapper to 1,693 contacts across the live
  accounts repaired 4 corroborated names and exposed 1,651 job titles and 1,646
  companies from existing fields. Unknown details are not fabricated.

## Deployment and limits

Archive SHA-256:
`2228bc21247d5fb5d54401671eab3d5ce1b54976239fc8e3b05a99d59df0f076`.
Immutable frontend: `/srv/runr/releases/connections-e0e45496/frontend/dist`.
Receipts and nginx rollback copy: `/srv/runr/ops/connections-e0e45496`.

The first activation rolled back because the immediate Nginx check saw the old
worker's release metadata. The operator script now polls for the expected
revision and supports resuming a build whose metadata matches the exact commit.
The verified staged build was then activated successfully. API, worker and
acquisition code were not redeployed.

No connected browser session was available, so authenticated live visual
verification remains outstanding; local desktop/mobile browser verification and
public served-asset verification passed. The extension source correction is
committed and tested but is not automatically installed by a frontend deployment.
Future native extraction requires an extension update; the web compatibility
layer handles corroborated legacy records immediately. Ambiguous old names can
be corrected through Edit without guessing from a headline.
