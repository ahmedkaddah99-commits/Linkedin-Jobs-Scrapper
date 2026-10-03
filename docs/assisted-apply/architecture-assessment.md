# Assisted Apply architecture assessment

Current repository assessment for RUN-52 (T52), based on the integrated T47–T51 code and deterministic fixtures. The historical assessment in commit `0d7f2b5c` predates the reviewed integration; its label-only navigation proposal is superseded by T51.

| Boundary | Current implementation | Evidence and limit |
| --- | --- | --- |
| Host registration | The service worker registers the in-page assistant for granted HTTPS origins and excludes Runr-owned origins. The manifest has no static content script. | T50 completion record; `wxt.config.ts`, `background.ts`, and `src/panel/script-registration.ts`. This is an install-time capability, not proof of a published Web Store build. |
| Application detection | A page classifier combines provider and form evidence; a recognized URL alone does not make a job posting an application form. | `aa301-application-context.test.ts`, `aa309-provider-matrix.test.ts`, and the Avature browser fixture. |
| Data flow | The service worker holds the session token, requests an approved profile package, and returns validated facts to the panel. The panel plans and verifies field writes. | T49 and T50 completion records. Missing or ambiguous facts remain for user review. |
| Upload | Intent resolution chooses a unique document field. Greenhouse/Lever have browser fixture upload evidence; the generic matrix resolves a CV target in unit fixtures. | `assisted-apply.spec.ts`, `assisted-apply.edge.spec.ts`, `aa309-provider-matrix.test.ts`. Generic target resolution alone does not prove extension-mediated browser upload on each provider. |
| Intermediate step | T51 permits one structurally verified Next/Continue activation and requires proof that the ordered stepper advanced. | `aa302-auto-panel.spec.ts` Avature fixture. Other provider multi-step flows are unverified. |
| Terminal boundary | The type constraint, static scans, runtime guard, fixed message types, and executor refuse automated terminal submission. | T47/T51 records and Chromium/Edge fixture checks. Page-owned network/navigation effects remain an open limit (WS9-G6). |

No live ATS sample or Web Store publication is claimed by this assessment. The historical AA-226 pilot had zero accessible live forms. Current provider support and remaining gaps are enumerated in [the capability matrix](simplify-parity-matrix.md).
