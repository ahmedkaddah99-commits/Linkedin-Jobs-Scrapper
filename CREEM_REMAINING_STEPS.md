# Creem Remaining Steps

Delete this file once every item below is complete and verified.

## 1. Create Creem Test Products

- Open Creem in developer/test mode.
- Create a recurring SaaS product for `Pro`.
  - Price: `EUR 29/month`
  - Copy the test product ID.
- Create a recurring SaaS product for `Business`.
  - Price: `EUR 79/month`
  - Copy the test product ID.

## 2. Configure Local Environment

Add the test values to `user_config/.env` or your active local env file:

```env
CREEM_API_KEY=creem_test_...
CREEM_WEBHOOK_SECRET=...
CREEM_PRO_PRODUCT_ID=prod_...
CREEM_BUSINESS_PRODUCT_ID=prod_...
```

Do not use live Creem values until the full test checkout and webhook loop works.

## 3. Apply Database Migration

From PowerShell in the repo root:

```powershell
cd "C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper"
.venv\Scripts\python.exe -m backend.database.migrate
```

Optional status check:

```powershell
.venv\Scripts\python.exe -m backend.database.migrate --status
```

Confirm migration `012_creem_billing` is applied.

## 4. Expose API For Webhook Testing

Creem needs a public HTTPS URL for webhooks.

Use either:

- Render staging API URL, if deployed.
- A tunnel such as ngrok/cloudflared pointing to the local API.

Webhook URL:

```text
https://<your-api-host>/v1/webhooks/creem
```

## 5. Register Creem Webhook

In Creem test mode, register the webhook URL above and subscribe to:

- `checkout.completed`
- `subscription.active`
- `subscription.paid`
- `subscription.update`
- `subscription.scheduled_cancel`
- `subscription.canceled`
- `subscription.expired`
- `subscription.past_due`
- `subscription.paused`

Copy the webhook signing secret into `CREEM_WEBHOOK_SECRET`.

## 6. Test Checkout End To End

- Start the app/API normally.
- Sign in as a test user.
- Start checkout for `Pro`.
- Use Creem test card:

```text
4242 4242 4242 4242
```

After payment, verify:

- The user is redirected back to the app.
- The pricing page shows a payment-success message with the subscribed plan.
- `/billing/subscription` shows `billing_provider=creem`.
- `plan_id` is `pro` or `business`.
- `creem_customer_id` is present.
- Clerk user metadata reflects the paid plan.

## 7. Test Portal And Cancellation

- Open the customer billing portal from the app.
- Confirm Settings shows the subscribed plan and a `Manage billing` button.
- Confirm the portal loads for the Creem customer.
- Cancel the test subscription.
- Confirm webhook handling downgrades the user back to `free`.
- Confirm local subscription status updates.

## 8. Run Verification Commands

Use PowerShell from the repo root:

```powershell
$env:TURSO_DATABASE_URL=""
$env:TURSO_AUTH_TOKEN=""
.venv\Scripts\python.exe -m pytest tests/test_backend_api.py -k "promo_code or billing_checkout or creem_webhook" -q
.venv\Scripts\python.exe -m pytest tests/test_database_migrations.py tests/test_env_config.py -q
npm --prefix frontend run check
```

## 9. Production Cutover

Only do this after all test-mode checks pass.

- Create or confirm live Creem `Pro` and `Business` products.
- Set live Render env vars:

```env
CREEM_API_KEY=creem_...
CREEM_WEBHOOK_SECRET=...
CREEM_PRO_PRODUCT_ID=prod_...
CREEM_BUSINESS_PRODUCT_ID=prod_...
```

- Register the production webhook:

```text
https://api.<your-domain>/v1/webhooks/creem
```

- Run one small live checkout before submitting business details.

## 10. Before Submitting Business Details

Confirm these are ready:

- Pricing is final and matches the app.
- Refund/cancellation policy is public and accurate.
- Terms and privacy policy are public and accurate.
- Production webhook is registered and tested.
- Live checkout, paid plan sync, billing portal, and cancellation all work.

After this checklist is complete, delete `CREEM_REMAINING_STEPS.md`.
