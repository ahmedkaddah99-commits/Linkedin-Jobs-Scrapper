# AA-224: Tracker preparation handoff

Status: feature-gated web handoff, 2026-08-01.

Tracker's reviewed-package dialog now creates a durable preparation record and
sends a protocol-v1 external command to the installed Runr extension. The web
message contains only preparation ID, package ID, ATS, bounded capabilities,
message identity, and action identity. It never contains tab/window IDs,
candidate payloads, document bytes, or submission state.

## State and ownership

The dialog reads `GET /assisted-apply/preparations/{preparation_id}` on a
bounded poll, so web reloads can recover the durable backend state. The
extension owns local tab identity and exact-tab activation. The backend owns
durable lifecycle state, expiry, retry limits, and package/session association.
`active` is presented as a review state; it is never rendered as submitted.

Permission denial is returned as `permission_required` with exact instructions
to use the Runr extension side panel's direct user gesture. Missing extension
or expired preparation errors remain explicit. Review, cancel, and retry are
explicit actions; review uses `review_activate` with preparation identity only.

The frontend flag `VITE_ENABLE_ASSISTED_APPLY_PREPARATION` defaults off. The
backend's existing `RUNR_ENABLE_ASSISTED_APPLY_PREPARATION` gate remains the
production kill switch until AA-226 completes the remaining production
foundation.

Render declares both flags as unsynchronized, operator-set variables. A
controlled pilot may set both to `true` for the pilot deployment; leaving either
unset keeps the flow disabled. The repository change does not enable either
flag or broaden the rollout.

## Evidence

- `frontend/src/components/AssistedApplyLaunchDialog.jsx` implements the
  Tracker flow, durable polling, action states, and no-submit messaging.
- `frontend/src/lib/assistedApplyPreparation.js` constructs the validated
  protocol envelopes and rejects malformed identities before contacting the
  extension.
- `backend/api/routes/assisted_apply_preparations.py` and
  `backend/application/assisted_apply_preparation_service.py` provide the
  existing authenticated durable create/read/action contract.
- `frontend/src/lib/assistedApplyPreparation.test.js` covers feature gating,
  protocol actions, extension missing/permission denial, expiry, and identity
  safety. Existing `tests/test_aa213_preparation.py` covers API lifecycle,
  expiry, authorization, replay, sanitized fields, and disabled-by-default
  behavior.

No Tracker status is changed by ATS success text. Existing explicit
confirmation remains the only path that adds an outcome to Tracker.
