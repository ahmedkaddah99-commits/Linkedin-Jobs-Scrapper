# Assisted Apply provider capability matrix

RUN-52 / T52. This table reports **Runr fixture evidence**, not parity with Simplify or validation against live employer portals. The older Simplify screen captures (C1–C9) show one Avature session and cannot establish provider-wide parity. The historical AA-226 pilot reached zero live forms.

Evidence shorthand: **U** = deterministic unit fixture (`tests/unit/aa309-provider-matrix.test.ts` or the named application-context test); **C** = Chromium browser fixture (`tests/e2e/assisted-apply.spec.ts` or `aa302-auto-panel.spec.ts`); **E** = Edge browser fixture (`tests/e2e/assisted-apply.edge.spec.ts`). The Edge configuration selects only `*.edge.spec.ts`, so Avature panel and step behavior has no Edge browser proof. “Unverified” means no claim for that capability, even when the code has a generic path.

| Provider | Detection and fill | Upload | Multi-step | Terminal behavior and evidence |
| --- | --- | --- | --- | --- |
| Greenhouse | Fixture verified C/E through the package-backed adapter | Browser fixture verified C/E | Unverified | Zero automated submit signals in C/E fixtures; user submission is outside this matrix. |
| Lever | Fixture verified C/E through its independent adapter | Browser fixture verified C/E | Unverified | Zero automated submit signals in C/E fixtures. |
| Ashby | Fixture verified U: application classification, field intents, plan and DOM readback | CV target resolved U; browser attachment unverified | Unverified | Planner excludes terminal controls U; runtime on this provider unverified. |
| Avature | Fixture verified U/C for application detection, in-page panel and field fill; Edge browser path unverified | Browser `DataTransfer` fixture accepts an exact CV field; extension-mediated upload unverified | One verified Continue transition C on the sanitized fixture; Edge unverified | Final-step fixture refuses terminal activation C; no submit event or URL change. |
| BambooHR | Fixture verified U: classification, field intents, plan and DOM readback | CV target resolved U; browser attachment unverified | Unverified | Planner excludes terminal controls U; runtime unverified. |
| iCIMS | Fixture verified U: classification, field intents, plan and DOM readback | CV target resolved U; browser attachment unverified | Unverified | Planner excludes terminal controls U; runtime unverified. |
| Jobvite | Fixture verified U: classification, field intents, plan and DOM readback | CV target resolved U; browser attachment unverified | Unverified | Planner excludes terminal controls U; runtime unverified. |
| Recruitee | Fixture verified U: classification, field intents, plan and DOM readback | CV target resolved U; browser attachment unverified | Unverified | Planner excludes terminal controls U; runtime unverified. |
| SmartRecruiters | Fixture verified U: classification, field intents, plan and DOM readback | CV target resolved U; browser attachment unverified | Unverified | Planner excludes terminal controls U; runtime unverified. |
| Taleo | Fixture verified U: classification, field intents, plan and DOM readback | CV target resolved U; browser attachment unverified | Unverified | Planner excludes terminal controls U; runtime unverified. |
| Workday | Fixture verified U: classification, field intents, plan and DOM readback | CV target resolved U; browser attachment unverified | Unverified | Planner excludes terminal controls U; runtime unverified. |
| Unsupported or generic form | A structural form may be classified and planned without a named provider. A posting page and ordinary content are refused by the classifier. | No provider-wide browser upload claim | No provider-wide step claim | Generic planning never authorizes terminal submission. Unknown or ambiguous controls remain manual. |

The automated never-submit boundary applies to all providers, but fixture evidence covers only the cases above. It does not prove that arbitrary page-owned JavaScript cannot issue requests after a user action. The extension has not been published to the Web Store as part of T52, and no live provider or customer data was used.

## Remaining work

- Verify browser-mediated generic upload and multi-step flows for each additional ATS before claiming them as supported in production.
- Run a controlled, authorized live-form pilot with safe sample and field-level receipts; the historical AA-226 `0/10` result is still the only live pilot record.
- Resolve WS9-G6 page-owned network/navigation effects, and confirm the Web Store listing and production extension-origin binding separately.
