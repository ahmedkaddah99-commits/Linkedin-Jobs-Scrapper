# Premium Upgrade Placement Proposal

## Goal

Make the upgrade path visible exactly where limits affect the user's workflow, without implementing the paywall in this pass.

## Recommended Placements

1. Workspace run setup
   - Show upgrade messaging near the Run action when the selected sources exceed plan limits.
   - Best triggers: company-site caps, runner-credit budget, monthly run quota, or premium-only sources.

2. Run Review
   - Show upgrade messaging when the run review shows capped coverage or skipped sources caused by plan limits.
   - This is the highest-value placement because the user can immediately see that fewer jobs were scraped than expected.

3. Tracker documents area
   - Show upgrade messaging beside bulk document export, ZIP download, and high-volume application package actions.
   - Best trigger: when exportable documents exist but the user's plan limits the export action.

4. CV Studio
   - Show upgrade messaging beside premium templates, multi-format re-export, and saved design presets.
   - Do not block basic CV editing; only premium-only design/export capabilities should open the paywall.

## Independent Paywall Modal

Create one reusable paywall modal that can be opened from any premium trigger. It should receive:

- `featureId`: the premium feature being requested.
- `context`: workspace, run, tracker, or CV Studio.
- `limitDetails`: current plan limit, usage, and required plan.
- `returnAction`: the action to retry after upgrade.

## Non-Goals For This Pass

- No payment provider changes.
- No plan enforcement changes.
- No new UI implementation yet.

## Suggested First Implementation Slice

Start with Run Review capped coverage because it is the clearest user-facing pain point: the user sees skipped/capped scraping results and can understand why upgrading matters.
