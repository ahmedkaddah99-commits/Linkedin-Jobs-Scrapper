> Source: deployment/render-turso-r2 | SHA: 58a96674 | Verified: 2026-09-14

# Billing and Creem (WS-6 secondary)

This doc covers the Creem slice of WS-6. The primary doc, [../01-architecture/security-and-auth.md](../01-architecture/security-and-auth.md), covers identity, webhook routing posture, env handling and the agent context packet. HTTP plumbing belongs to WS-1 ([../01-architecture/backend-api.md](../01-architecture/backend-api.md)). Quota enforcement and Pro feature gating inside customer services belong to WS-4 ([personalized-jobs-and-customer-app-services.md](personalized-jobs-and-customer-app-services.md)). Tables belong to WS-5 ([../03-data/schema-and-migrations.md](../03-data/schema-and-migrations.md)).

Env var **names** only. No API keys, webhook secrets, product ID values, Render IDs or hosts appear here.

## 1. Purpose and user-facing capabilities

- **One paid plan, Runr Pro (`runr_pro`)**, plus `free` (`backend/config/plans.py:8–10`). Pro is sold as three duration offers (`plans.py:12–43`):

| `offer_id` | Display | Amount (USD cents) | Creem billing | Product ID env name |
|---|---|---:|---|---|
| `one_week` | 1 week | 1999 | one-time | `CREEM_RUNR_PRO_WEEKLY_PRODUCT_ID` |
| `one_month` | 1 month | 3999 | recurring monthly | `CREEM_RUNR_PRO_MONTHLY_PRODUCT_ID` (fallback `CREEM_RUNR_PRO_PRODUCT_ID`) |
| `three_months` | 3 months | 8999 | recurring every 3 months | `CREEM_RUNR_PRO_QUARTERLY_PRODUCT_ID` |

- **Pricing page / upgrade flows** call `/billing/plans`, `/billing/subscription`, `/billing/checkout`, `/billing/checkout/confirm` and `/billing/portal` (`frontend/src/pages/PricingPage.jsx:66,76,137,184,206`, `frontend/src/components/UpgradeModal.jsx:61`, `frontend/src/components/personalized/PostOnboardingProOffer.jsx:257,266,356`, `frontend/src/pages/ProfilePage.jsx:26`).
- **Entitlements.** Free quotas are all `0`; Pro quotas and limits are all `-1` (unlimited) (`plans.py:45–83`). Match scores are free; resume rewriting and tailored documents are Pro (`backend/application/personalized_jobs_service.py:1193`, tested in `tests/test_phase_h_runr_pro.py:126`). Assisted Apply packages require Pro (`backend/api/routes/assisted_apply_packages.py:112–120`).
- **Legacy compatibility.** Plan names `launch`, `momentum`, `scale`, `pro` and `business` map to `runr_pro` (`plans.py:95–103`). Legacy product env names `CREEM_LAUNCH_PRODUCT_ID`, `CREEM_MOMENTUM_PRODUCT_ID` and `CREEM_SCALE_PRODUCT_ID` (`plans.py:89–93`) still resolve to Pro (`get_plan_for_product_id` L161–169).

## 2. Owned paths and governing docs

- Owned: `backend/integrations/creem.py` (361 lines). The file counts for `backend/integrations/**` are in the primary doc §2.
- Consumed: `backend/config/plans.py`, `backend/api/routes/admin.py`, `backend/api/server.py` (L7441–7449, L7935–7987, L8175–8576), `backend/application/production_rollout.py`, `backend/application/quota.py`, `backend/repositories/sqlite_backed.py` (L1896–2069).
- Existing docs checked against code:
  - [../../deployment/creem.md](../../deployment/creem.md): the endpoints (`/billing/checkout`, `/billing/portal`, `/webhooks/creem`), checkout metadata keys, the email fallback and the env names all **match** code (`admin.py:261–345`, `server.py:8408–8417`, `plans.py`). Its subscribed-event list omits `subscription.trialing`/`renewed`/`resumed`, which the handler also accepts (`server.py:8433–8446`). It is a setup runbook, not proof of provider configuration.
  - [../../deployment/creem_phase_h_audit.md](../../deployment/creem_phase_h_audit.md): the compatibility mapping, the grant/retain/revoke state table and "no handler calls Creem cancel" all **match** code (`server.py:8513–8574`; no cancel call in `creem.py`). It is a dated documentary record (2026-08-07). Its external checkout loop was recorded as pending.
  - [../../legal/RUNR_USER_AGREEMENT.md](../../legal/RUNR_USER_AGREEMENT.md) §7 and [../../legal/RUNR_TERMS_AND_CONDITIONS.md](../../legal/RUNR_TERMS_AND_CONDITIONS.md) (L105–109, appendix L193): payment and refund text is generic, with unfilled placeholders and a note that legal review of the checkout flow is incomplete. Not verifiable against code.

## 3. Entry points and registered routes

Registered in `backend/api/routes/admin.py:23–33`:

| Route name | Registration | Handler branch | Auth |
|---|---|---|---|
| `admin.billing.plans` | exact GET `('billing','plans')`, `auth_required=False` (L24) | L42: `list_plans()` | public |
| `admin.billing` | prefix GET `('billing',)`, True (L26) | L70: `billing/subscription` → `_subscription_response_payload` | bearer |
| `admin.billing.post` | prefix POST `('billing',)`, True (L31) | L261 `billing/checkout`; L325 `billing/checkout/confirm`; L336 `billing/portal` | bearer |
| `admin.webhooks.creem` | exact POST `('webhooks','creem')`, **False** (L30) | L218–237 | `creem-signature` HMAC; origin policy skipped (`server.py:9232–9234`) |
| `admin.webhooks.clerk` | exact POST `('webhooks','clerk')`, **False** (L29) | L213–216 | Svix (primary doc §5.3). Relevant here because `user.deleted` cancels local subscriptions (`server.py:8162–8170`). |

Also relevant: `admin.account.delete` (L33, handler L454–492) deactivates the user and calls `cancel_subscriptions_for_user` (local only). There is no CLI entry point for billing.

## 4. Inputs, outputs, storage, dependencies

**Env names** (`backend/config/env_schema.py:133–182`; `render.yaml:132–149`, all `sync: false`):
`CREEM_API_KEY`, `CREEM_WEBHOOK_SECRET`, `CREEM_API_BASE_URL` (optional; schema only, not in `render.yaml`), and the product IDs. `grep -c "key: CREEM_.*PRODUCT_ID" render.yaml` = **7**:
`CREEM_RUNR_PRO_PRODUCT_ID`, `CREEM_RUNR_PRO_WEEKLY_PRODUCT_ID`, `CREEM_RUNR_PRO_MONTHLY_PRODUCT_ID`, `CREEM_RUNR_PRO_QUARTERLY_PRODUCT_ID`, `CREEM_LAUNCH_PRODUCT_ID`, `CREEM_MOMENTUM_PRODUCT_ID`, `CREEM_SCALE_PRODUCT_ID` (`render.yaml:136–148`). The same 7 are in `env_schema.py:148–182`. `APP_FRONTEND_ORIGIN`/`FRONTEND_ORIGIN` set the checkout `success_url` origin (`server.py:8966–8970`). The Clerk Backend API (`CLERK_SECRET_KEY`) is used to write plan metadata.

**Provider base URL:** `CREEM_API_BASE_URL` if set; otherwise test keys (by prefix) use the test API and other keys use the live API (`creem.py:28–34`). HTTP timeout is 20 s (L98).

**Storage** (WS-5 owns schema):
- `subscriptions`, `subscription_events` and `quota_usage` are created in the base migration (`sqlite_migrations.py:141–178`, with `lemonsqueezy_*` columns left over from the earlier provider).
- `012_creem_billing` (L3278; `_apply_creem_billing_migration` L183–196) adds `billing_provider`, `creem_subscription_id`, `creem_customer_id`, `creem_order_id` and `provider_event_name`, plus a partial index on `creem_subscription_id`.
- Repository methods: `get_current_subscription_by_user_id` (`sqlite_backed.py:1896`), `upsert_subscription` (1912), `cancel_subscriptions_for_user` (1953), `insert_subscription_event` (1969, `INSERT OR REPLACE` keyed by `event_id`), `list_quota_usage` (2016), `increment_quota_usage` (2027), `reset_quota_usage` (2069).
- **Clerk `publicMetadata`**: `plan_id` and `quota_overrides` are written by `update_user_plan_in_clerk` (`creem.py:113–125` → `clerk.update_user_metadata`). They flow back into the session JWT through the template (`env_schema.py:8–14`).
- **Analytics events** (`application.emit_event`): `checkout_started` (with `promo_code_present` boolean only, `admin.py:308–321`), `subscription_started`, `subscription_changed`, `subscription_cancelled`, `quota_limit_hit` (`quota.py:130–143`).

## 5. Call/data flows

### 5.1 Checkout (`admin.py:261–323`)
1. `_auth_context`. `plan_id` is normalized and must not be `free` (L264–266).
2. **Rollout gate:** `phase_i_config(config_store, "checkout_gate_enabled", False)` must be truthy, otherwise `PermissionError` → 403 (L267–270; default off at `production_rollout.py:58`; set on completion at L616).
3. Optional promo code must match `^[A-Z0-9]{3,256}$` (`server.py:195,7981–7987`).
4. Offer lookup: `get_runr_pro_offer(offer_id)`, default `one_month`, with a compatibility shim for the older single-product plan shape (L276–289). A missing product ID raises `ValueError` → 400.
5. `creem.get_checkout_url` (`creem.py:275–316`) → POST `/checkouts` with `product_id`, `request_id = runr_<user_id>_<12 hex>`, `metadata` {`user_id`, `plan_id`, `offer_id`, `product_id`, `source_page`, `clerk_user_id`}, `customer.email` only (name omitted; test `tests/test_creem_integration.py:9`), optional `discount_code`, and `success_url = <frontend>/pricing?checkout=success&plan_id=…&offer_id=…`.
6. Returns `{checkout_url}` and emits `checkout_started`.

### 5.2 Signed return confirmation (`admin.py:325–334` → `server.py:_confirm_creem_checkout_redirect` L8300–8386)
1. `creem.verify_redirect_signature` (`creem.py:49–75`): drop `signature` and empty/`null` values, then check SHA-256 of `k=v|k=v|…|salt=<CREEM_API_KEY>` in constant time. If that fails, retry using only the Creem-signed keys (`request_id`, `checkout_id`, `order_id`, `customer_id`, `subscription_id`, `product_id`) so UI query params can be present (test `tests/test_creem_integration.py:33`).
2. Plan comes from `get_plan_for_product_id(product_id)` and must be paid and equal to the requested `plan_id`.
3. If a `subscription_id` is present, `upsert_subscription` (status `active`, Creem IDs). Always insert a `checkout_completed` subscription event (`provider_event_name=checkout.redirect_confirmed`). Update Clerk plan metadata. On upgrade, reset the current-period quota usage (`compare_plan_tiers` `plans.py:195–198`).

### 5.3 Webhook (`admin.py:218–237` → `server.py:_handle_creem_webhook_event` L8389–8576)
1. `creem.verify_webhook_signature` (`creem.py:37–46`): hex HMAC-SHA256 of the **raw body** with `CREEM_WEBHOOK_SECRET`, compared in constant time against the `creem-signature` header. Missing secret → `RuntimeError` (500); missing or invalid signature → `ValueError` (400).
2. Body must be a JSON object with `eventType`/`event_type`.
3. Envelope parsing: `object` or `data`; nested `subscription`/`checkout`/`order`; merged `metadata` (L8396–8400).
4. **User resolution:** metadata `user_id`/`userId`/`reference_id`/`referenceId`, else a local user by customer email (L8408–8417), else `ValueError`.
5. **Plan:** metadata `plan_id` → product-ID mapping → existing record → `free` (L8421–8426).
6. **Status:** the subscription `status`, or the per-event default (L8433–8446). Unknown event names → `{"status":"ignored"}` (L8495–8496) before any write.
7. Upsert the subscription when a subscription ID exists, and always record a `subscription_events` row keyed by the provider event `id` (L8498–8511).
8. Entitlement side effects (L8513–8574):

| Events | Clerk `plan_id` | Other |
|---|---|---|
| `checkout.completed`, `subscription.active`, `.trialing`, `.paid`, `.renewed`, `.resumed` | set to resolved plan | quota reset on upgrade; `subscription_started` for active/trialing/checkout |
| `subscription.update`, `.scheduled_cancel`, `.past_due` | updated only if plan changed | `subscription_changed` if plan changed; access retained |
| `subscription.paused`, `.expired`, `.canceled` | set to `free` | `subscription_cancelled` for expired/canceled |

### 5.4 Subscription read (`server.py:_subscription_response_payload` L7935–7978)
Effective plan = stored record `plan_id` (or the caller's plan). It is downgraded to `free` when the stored status is not in {`active`,`trialing`,`scheduled_cancel`,`past_due`}. The response includes plan details (with runtime offer product IDs), the Creem IDs, period dates, the `_quota_usage_snapshot` (L7906–7932) and the ScrapeOps user usage summary.

### 5.5 Portal (`admin.py:336–345`)
Uses the stored `creem_customer_id`, else resolves the customer through `retrieve_subscription`, then POSTs `/customers/billing` and returns `{portal_url}` (`creem.py:339–361`).

### 5.6 Quota linkage (WS-4 owns enforcement)
- The request-time plan is `context.plan_id`. For Clerk sessions it comes from the **JWT `publicMetadata.plan_id`** (`server.py:7662`). For legacy tokens it comes from the stored subscription record (`server.py:7691–7692`).
- `_quota_limit_for_user` (`server.py:7416–7424`): `RUNR_DISABLE_QUOTAS` → unlimited; then `quota_overrides`; then `get_quota`. `backend/application/quota.py` raises `QuotaExceededError` (L144, L223) after emitting `quota_limit_hit`. The HTTP layer maps it through `_send_quota_exceeded` (`server.py:9212–9213`).
- Readiness gate `creem_products_configured` (`production_rollout.py:355–362`): `CREEM_API_KEY` and `CREEM_WEBHOOK_SECRET` set, `CREEM_RUNR_PRO_PRODUCT_ID` set, and the distinct Pro product count equals the offer count (3). It is part of the `pro_checkout` and `complete` stage requirements (L570–571).

## 6. Invariants, failure handling, recovery

- No entitlement change without a verified signature, either webhook HMAC or redirect SHA-256 salted with the API key.
- Provider subscription and customer IDs are preserved across state changes. No code cancels, upgrades or deletes a Creem subscription (`creem.py` has no such call).
- Canonical entitlement is only `free` or `runr_pro`; unknown plan IDs normalize to `free` (`plans.py:130–133`).
- A missing product env var makes that offer non-purchasable (400) and fails the readiness gate. It does not crash startup (product IDs are `required: False`, `env_schema.py:148–182`).
- Creem HTTP errors raise `RuntimeError` with the provider body, and a special message for `403 browser_signature_banned` (`creem.py:100–109`). Handlers surface these as 500 with the message text.
- A webhook for an unresolvable user returns 400. Creem retry behaviour on non-2xx is provider-side and not recorded.
- Recovery: re-deliver the webhook from the Creem dashboard (the `event_id` row is replaced, side effects re-run), or have the user repeat the signed redirect confirmation. There is no admin billing tool at baseline (retired admin surfaces, C7).

## 7. Tests and safe verification commands

| Test | Covers |
|---|---|
| `tests/test_creem_integration.py` | checkout payload omits customer name (L9); redirect signature with UI params (L33) |
| `tests/test_phase_h_runr_pro.py` | canonical plan/offer catalog (L35); legacy names/products → Pro (L50); webhook state sequence preserves subscription IDs (L68); Phase I Creem gate (L114); free scores vs Pro documents (L126) |
| `tests/test_backend_api.py` | subscription includes ScrapeOps usage (L2693); account delete cancels subscription (L2719); checkout promo code not logged (L4305); checkout disabled by default gate (L4355); invalid promo (L4367); signed redirect confirm (L4391); webhook active subscription (L4426) |

No test found for: an invalid or missing `creem-signature` returning 400; the webhook email-fallback user resolution; the portal URL flow.

Not executed in Phase 2:

```bash
python -m pytest tests/test_creem_integration.py tests/test_phase_h_runr_pro.py -q
python -m pytest tests/test_backend_api.py -q -k "billing or creem or subscription or account_delete"
grep -c "key: CREEM_.*PRODUCT_ID" render.yaml   # expect 7
```

## 8. Historical commits

`git log --oneline 58a96674 -- backend/integrations/creem.py backend/config/plans.py`:
`334bb9b0` Clerk IAM, MoR, Subscribtions · `c7bf7cbd` deoployment prep initial setup · `4bc108b0` Creem MoR Initial Setup · `b0359e4d` Creem Bug Fixes and Improvements · `86a41ab1` sig. unblock · `7991c805` Creems new json correction · `1a5dead5` Sync Creem checkout and show subscription state · `5e674e1e` fix: migrate Creem billing to Runr Pro (canonical `runr_pro`, three offers, legacy aliases).

The `lemonsqueezy_*` columns in the base schema (`sqlite_migrations.py:146–161`) show that an earlier provider was replaced by Creem in migration `012_creem_billing`.

## 9. Current implementation status

| Capability | Classification |
|---|---|
| Plan catalog endpoint | VERIFIED (scope: static. `admin.billing.plans` is registered at `admin.py:24`; branch L42 → `list_plans` `plans.py:201`.) |
| Checkout creation | VERIFIED (scope: static. `admin.billing.post` is registered at L31; branch L261 → `get_creem_checkout_url` (`server.py:184`) → `creem.get_checkout_url`. Reachability depends on the `checkout_gate_enabled` config value, which is UNKNOWN in any deployment.) |
| Signed redirect confirmation | VERIFIED (scope: static. Branch L325 → `server.py:8300` → `verify_redirect_signature`.) |
| Creem webhook with HMAC verification | VERIFIED (scope: static. `admin.webhooks.creem` is registered at L30; branch L218–221 verifies before `_handle_creem_webhook_event`.) |
| Subscription status + usage payload | VERIFIED (scope: static. Prefix `admin.billing` L26; branch L70 → `server.py:7935`.) |
| Customer portal link | VERIFIED (scope: static. Branch `admin.py:336` → `creem.get_customer_portal_url`.) |
| Runr Pro entitlements / quota linkage | IMPLEMENTED-UNVERIFIED (WS-4 owns enforcement sites) |
| Legacy plan/product compatibility | IMPLEMENTED-UNVERIFIED |
| Creem discount management (`list_discounts`, `create_discount`, `delete_discount`) and `retrieve_customer` | IMPLEMENTED-UNVERIFIED with **no caller** outside `backend/integrations/` at baseline (re-exported only; likely retired admin residue, C7) |
| Provider-side subscription cancellation on account deletion | PLANNED-NOT-IMPLEMENTED? Not planned in any cited doc. Recorded as a gap (WS6-B4), classified **UNKNOWN**. |
| Creem products / webhook configured with the provider | UNKNOWN |

### Deployment evidence (documentary only)

- `render.yaml` declares `CREEM_API_KEY`, `CREEM_WEBHOOK_SECRET` and 7 `CREEM_*PRODUCT_ID` keys on the API service with `sync: false` (L132–149). Values are not in Git.
- `docs/deployment/creem_phase_h_audit.md` (2026-08-07) records test-mode products only, zero subscriptions, and the external checkout/webhook/portal loop **pending**.
- LAST-RECORDED production Render `5dfdd106` (`docs/RUNR_PRODUCTION_COMPLETION_HANDOFF.md`). Live billing state = UNKNOWN (U1).

## 10. Gaps and unresolved questions

| ID | Gap |
|---|---|
| WS6-B1 | Webhook has no timestamp or replay window and no ordering check. `INSERT OR REPLACE` by `event_id` (`sqlite_backed.py:1976`) means re-delivery re-runs Clerk updates, quota resets and analytics events. An older validly signed grant event replayed after cancellation would re-grant Pro. Confirm Creem's signature/timestamp semantics. |
| WS6-B2 | `checkout/confirm` grants the plan to the **calling** user from any validly signed query. `request_id` (`runr_<user_id>_…`) and metadata are not compared with the caller (`server.py:8300–8381`). Needs review of whether a signed success URL can be reused by another account. |
| WS6-B3 | Webhook user resolution falls back to customer email lookup (`server.py:8410–8415`). A mismatched email could attach a subscription to a different local user. |
| WS6-B4 | Account deletion and Clerk `user.deleted` cancel only local subscription rows (`admin.py:469–471`, `server.py:8167–8169`). No Creem cancellation, so recurring billing may continue. Needs an owner/legal decision (links to the legal-doc placeholders). |
| WS6-B5 | Two sources of truth: request-time plan comes from the JWT `publicMetadata` (Clerk) while `/billing/subscription` comes from the DB record plus status. A failed Clerk metadata update after a DB write leaves them divergent. There is no reconciliation job. |
| WS6-B6 | `/billing/checkout` is off unless the Phase I `checkout_gate_enabled` config is set. Deployed value UNKNOWN. |
| WS6-B7 | Provider error bodies can reach API clients through 500 messages (`creem.py:107`, `server.py:9224`). |
| WS6-B8 | `docs/deployment/creem.md` event list omits the trialing/renewed/resumed events that the handler accepts. |
| — | Primary-doc gaps WS6-G1…G11, C7 (retired admin billing tools), U1, T08, T10 are recorded in [../01-architecture/security-and-auth.md](../01-architecture/security-and-auth.md) §10. |

Agent context, registry row and ticket candidates are in the primary doc's "Agent context and remaining work". Billing-specific ticket candidates: WS6-B1 replay/ordering protection; WS6-B2 bind confirmation to the checkout `request_id`/user; WS6-B4 provider cancellation on account deletion; WS6-B5 plan reconciliation between Clerk metadata and subscriptions.
