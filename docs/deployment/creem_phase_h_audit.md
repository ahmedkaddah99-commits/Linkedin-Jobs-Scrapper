# Phase H Creem audit and migration record

Audit date: 2026-08-07. The audit was read-only and redacted API keys, webhook secrets, customer email addresses, subscription IDs, and other credentials.

## Provider audit

Configured local Creem mode is test mode (`CREEM_API_KEY` has the `creem_test_` prefix); the API base URL is the automatic test endpoint. The configured webhook secret is present but not recorded here.

The test product search returned three products and zero subscriptions:

| Product | Product ID | Price | Currency | Billing | State | Subscribers |
| --- | --- | ---: | --- | --- | --- | ---: |
| Runr Launch | `prod_22VcsmGgZ74Sc7DH5dqi7a` | 15.00 | EUR | one-time / once | active | 0 |
| Runr Momentum | `prod_3ROOvfZMltovO5dv0cekEq` | 25.00 | EUR | one-time / once | active | 0 |
| Runr Scale | `prod_2wk5dOF3Ta6w4oWBB5uxhh` | 79.00 | USD | one-time / once | active | 0 |

Creem returned no separate price IDs for these products. The product API exposed `id`, `mode`, `name`, `price`, `currency`, `billing_type`, `billing_period`, and `status`. Subscription search was accessible and returned `items=[]`; direct subscription retrieval without an ID was rejected as expected.

The test API allowed read access but rejected product creation with HTTP 403 and an empty response. The dashboard check reached the Creem sign-in page and had no authenticated session. No provider product was created or changed by this migration, and no live endpoint was called.

## Compatibility mapping

| Incoming identity | Canonical entitlement | Provider subscription action |
| --- | --- | --- |
| Free / `none` | `free` | none |
| New Runr Pro offer product | `runr_pro` | new checkout only |
| Legacy Launch product ID | `runr_pro` | preserve existing subscription |
| Legacy Momentum product ID | `runr_pro` | preserve existing subscription |
| Legacy Scale product ID | `runr_pro` | preserve existing subscription |
| legacy plan names `launch`, `momentum`, `scale`, `pro`, `business` | `runr_pro` | compatibility aliases only |

No handler calls Creem cancel, upgrade, replace, or delete for an existing subscription. The original Creem subscription/customer IDs remain in the local record, and the webhook event payload retains the provider product identity.

## New Runr Pro offer configuration

The one user-facing Runr Pro plan has three duration offers matching the current Simplify+ pricing: 1 week at USD 19.99 total (one-time because Creem does not expose a weekly recurring interval), 1 month at USD 39.99 recurring monthly, and 3 months at USD 89.99 recurring every three months.

Environment variable names:

- `CREEM_API_KEY`
- `CREEM_WEBHOOK_SECRET`
- `CREEM_API_BASE_URL` (optional)
- `CREEM_RUNR_PRO_PRODUCT_ID` (primary/monthly product)
- `CREEM_RUNR_PRO_WEEKLY_PRODUCT_ID`
- `CREEM_RUNR_PRO_MONTHLY_PRODUCT_ID`
- `CREEM_RUNR_PRO_QUARTERLY_PRODUCT_ID`
- `CREEM_LAUNCH_PRODUCT_ID`, `CREEM_MOMENTUM_PRODUCT_ID`, `CREEM_SCALE_PRODUCT_ID` (legacy compatibility IDs)

The canonical readiness gate requires the API key, webhook secret, primary Runr Pro product, and all three canonical offer product IDs. Legacy IDs are reported and recognized but are not required for new-product readiness.

## Checkout/webhook behavior checklist

- Checkout input: canonical `plan_id=runr_pro`, `offer_id`, optional promo code, source page; metadata includes `user_id`, `clerk_user_id`, `plan_id`, `offer_id`, and selected product ID.
- Signed return: verifies the Creem signature, product mapping, requested canonical plan, subscription/customer IDs, and upserts the local subscription.
- Webhook fields: event ID/type, object or data envelope, metadata user/reference ID and plan/offer IDs, product ID/object, customer ID/email, subscription ID/status, order ID, period start/end, timestamps, and cancellation date.
- Active, trialing, paid, renewed, and resumed: grant or restore `runr_pro`.
- Scheduled cancellation and past due: retain `runr_pro` while the provider subscription remains present.
- Paused, canceled, and expired: return the effective entitlement to `free`.
- Portal: uses the stored Creem customer/subscription identifiers and existing customer billing endpoint.

## Verification evidence

`tests/test_phase_h_runr_pro.py` covers canonical plan/offer catalog, legacy product mapping, subscriber-ID preservation across active/scheduled-cancel/past-due/pause/resume/cancel events, the Phase I gate, and Free score versus Pro document entitlements.

The external checkout/webhook/portal/cancellation loop remains pending provider setup because the available test account cannot create products or authenticate to the Creem dashboard. This is intentionally not substituted with a live charge.
