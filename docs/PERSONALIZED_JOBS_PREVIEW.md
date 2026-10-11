# Personalized jobs preview (historical)

> Historical record: this document describes the earlier frontend-only preview
> slice. It is not the current personalized-jobs operating contract.

The current baseline uses the personalized-jobs backend and API over the
published catalog, and its deployment sets `VITE_PERSONALIZED_JOBS_DATA_MODE=real`.
See the [authoritative personalized-jobs and customer app services record](reverse-engineering/05-subsystems/personalized-jobs-and-customer-app-services.md)
for the current behavior.

## Historical preview setup

In `frontend/.env.local`:

```dotenv
VITE_PERSONALIZED_JOBS_EXPERIENCE=1
```

At the time of this preview, Vite had to be restarted after changing the value.
Disabling it with `0`, or removing the variable, left the old navigation
unchanged. The former `/dashboard` redirect reference is retired and is not a
current route contract.

When enabled, the preview Jobs navigation item was available while the existing
workspace, run, tracker, CV, Career Evidence, billing, and Assisted Apply routes
remained available.

## Historical preview boundaries

- The preview job cards, feed totals, profile defaults, onboarding extraction, and value metrics came from `frontend/src/lib/personalizedJobs.js` and were marked `Preview data`.
- Preview onboarding answers, save/hide/restore dispositions, and upgrade-prompt dismissal were stored in local browser storage only; they did not update production profile fields.
- Preview restore never called `/rejected-jobs/requeue`.
- Preview analytics used the existing `logEvent` client and sent route, feature, preview job ID, filter, onboarding step, and `data_mode`; it did not send CV contents, application answers, salary expectations, language details, or work authorization details.
- The canonical job repository, matching API, eligibility API, analytics metrics endpoint, tailored-document flow, scheduled-search API, and Assisted Apply entitlement flow were backend work for a later slice; current ownership and behavior are documented in the authoritative subsystem record.

