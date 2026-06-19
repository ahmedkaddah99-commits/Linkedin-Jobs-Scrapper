# Creem Billing Setup

Use Creem test mode until the full checkout and webhook loop passes. Test API keys are prefixed with `creem_test_`; live keys are prefixed with `creem_`.

## Code Integration

The app keeps its own billing endpoints stable:

- `POST /v1/billing/checkout` creates a Creem checkout session.
- `POST /v1/billing/portal` creates a Creem customer portal link.
- `POST /v1/webhooks/creem` receives Creem webhook events.

Creem metadata sent during checkout includes:

- `user_id`
- `plan_id`
- `source_page`
- `clerk_user_id`

The webhook handler uses that metadata first, then falls back to customer email.

## Required Creem Dashboard Setup

1. Enable test mode in Creem.
2. Create recurring SaaS products for:
   - Launch, monthly, EUR 15
   - Momentum, monthly, EUR 25
   - Scale, monthly, EUR 79
3. Copy the test product IDs into local env:

   ```env
   CREEM_API_KEY=creem_test_...
   CREEM_WEBHOOK_SECRET=...
   CREEM_LAUNCH_PRODUCT_ID=prod_...
   CREEM_MOMENTUM_PRODUCT_ID=prod_...
   CREEM_SCALE_PRODUCT_ID=prod_...
   ```

4. Add the webhook endpoint:

   ```text
   https://<api-host>/v1/webhooks/creem
   ```

5. Subscribe to these events:
   - `checkout.completed`
   - `subscription.active`
   - `subscription.paid`
   - `subscription.update`
   - `subscription.scheduled_cancel`
   - `subscription.past_due`
   - `subscription.paused`
   - `subscription.expired`
   - `subscription.canceled`

6. Run test checkout with Creem's successful test card:

   ```text
   4242 4242 4242 4242
   ```

## Production Cutover

Do not submit live business details until test mode passes end to end.

1. Confirm local or staging checkout redirects to Creem.
2. Complete a test subscription.
3. Confirm `/billing/subscription` shows `billing_provider=creem`, `plan_id=launch`, `momentum`, or `scale`, and a `creem_customer_id`.
4. Open the billing portal from the pricing page.
5. Cancel or expire a test subscription and confirm local access returns to `none`.
6. Add live Creem values to Render:

   ```env
   CREEM_API_KEY=creem_...
   CREEM_WEBHOOK_SECRET=...
   CREEM_LAUNCH_PRODUCT_ID=prod_...
   CREEM_MOMENTUM_PRODUCT_ID=prod_...
   CREEM_SCALE_PRODUCT_ID=prod_...
   ```

7. Register the production webhook URL in Creem live mode:

   ```text
   https://api.<your-domain>/v1/webhooks/creem
   ```

8. Keep test and live product IDs separate. Creem test and live environments are isolated.
