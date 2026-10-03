# Creem Phase H remaining steps

The code migration is complete, but external Creem setup remains environment-specific. See [`docs/deployment/creem_phase_h_audit.md`](docs/deployment/creem_phase_h_audit.md) for the read-only audit and compatibility record.

## Test mode setup

Create these three active test products in Creem. The current test API key can list products but returned HTTP 403 for product creation, and the available browser session was not authenticated to the Creem dashboard.

| Offer | Amount | Billing | Environment variable |
| --- | ---: | --- | --- |
| Runr Pro — 1 week | USD 19.99 total | one-time | `CREEM_RUNR_PRO_WEEKLY_PRODUCT_ID` |
| Runr Pro — 1 month | USD 39.99 | recurring monthly | `CREEM_RUNR_PRO_MONTHLY_PRODUCT_ID` |
| Runr Pro — 3 months | USD 89.99 | recurring every three months | `CREEM_RUNR_PRO_QUARTERLY_PRODUCT_ID` |

Set `CREEM_RUNR_PRO_PRODUCT_ID` to the monthly product ID, and keep the legacy `CREEM_LAUNCH_PRODUCT_ID`, `CREEM_MOMENTUM_PRODUCT_ID`, and `CREEM_SCALE_PRODUCT_ID` values unchanged while existing subscribers remain active.

## Webhook and loop verification

1. Apply or verify the existing Creem billing database migration.
2. Register `https://<api-host>/v1/webhooks/creem` in Creem test mode.
3. Subscribe to `checkout.completed`, `subscription.active`, `subscription.trialing`, `subscription.paid`, `subscription.update`, `subscription.scheduled_cancel`, `subscription.past_due`, `subscription.paused`, `subscription.resumed`, `subscription.renewed`, `subscription.expired`, and `subscription.canceled`.
4. Run test checkout for each recurring offer with Creem's test card `4242 4242 4242 4242`.
5. Verify signed return, webhook sync, `/billing/subscription` (`plan_id=runr_pro`), stored customer/subscription IDs, and the portal.
6. Verify scheduled cancellation and past-due retain access, while paused/canceled/expired return the effective entitlement to `free`; verify a paid/active/resumed event restores Pro.
7. Run the focused Python and frontend checks from the project instructions.

Never configure live product IDs or create a live charge as part of this checklist without explicit approval.
