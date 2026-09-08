# Personalized jobs preview

The first personalized jobs vertical slice is frontend-only and is protected by the Vite flag `VITE_PERSONALIZED_JOBS_EXPERIENCE`.

## Enable locally

In `frontend/.env.local`:

```dotenv
VITE_PERSONALIZED_JOBS_EXPERIENCE=1
```

Restart Vite after changing the value. Disable it with `0`, or remove the variable. When disabled, `/onboarding`, `/jobs`, `/jobs/hidden`, and `/jobs/:jobId` redirect to the existing dashboard and the existing navigation is unchanged.

When enabled, the new Jobs navigation item is available, while all existing workspace, run, tracker, CV, Career Evidence, billing, and Assisted Apply routes remain available.

## Preview boundaries

- Job cards, feed totals, profile defaults, onboarding extraction, and value metrics come from `frontend/src/lib/personalizedJobs.js` and are marked `Preview data`.
- Onboarding answers, save/hide/restore dispositions, and upgrade-prompt dismissal are stored in local browser storage only. They do not update production profile fields.
- Preview restore never calls `/rejected-jobs/requeue`.
- Analytics uses the existing `logEvent` client. It sends route, feature, preview job ID, filter, onboarding step, and `data_mode`; it does not send CV contents, application answers, salary expectations, language details, or work authorization details.
- The missing canonical job repository, matching API, eligibility API, analytics metrics endpoint, tailored-document flow, scheduled-search API, and Assisted Apply entitlement flow remain backend work for a later slice.

