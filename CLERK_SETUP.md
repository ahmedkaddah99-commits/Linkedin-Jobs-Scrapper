# Clerk JWT Template Setup

This must be done once manually in the Clerk dashboard before the 
backend quota and role enforcement works.

## Steps
1. Go to https://dashboard.clerk.com
2. Select the Runr application
3. Go to Configure → JWT Templates
4. Click "New template" → choose "Blank"
5. Set the name to exactly: runr_backend
6. Replace the default claims with:

{
  "publicMetadata": {
    "role": "{{user.public_metadata.role}}",
    "plan_id": "{{user.public_metadata.plan_id}}",
    "quota_overrides": "{{user.public_metadata.quota_overrides}}"
  }
}

7. Leave the token lifetime at default (60 seconds)
8. Click Save

## Verification
After setup, sign in as a user and check the browser network tab.
Find a request to your backend with an Authorization: Bearer <token> header.
Paste the token into https://jwt.io and verify the payload contains:
{
  "publicMetadata": {
    "role": "user",
    "plan_id": "free",
    "quota_overrides": null
  }
}

If publicMetadata is missing, the template name does not match or 
getToken({ template: "runr_backend" }) is not being called.

## What breaks without this
- Backend always sees plan_id as null → treats everyone as free plan
- Role checks always fail → no admin access
- Quota enforcement uses wrong plan → wrong limits applied
