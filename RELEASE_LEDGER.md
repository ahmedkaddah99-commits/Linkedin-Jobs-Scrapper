# Runr Wave 1 Integration Ledger

Base: `0068a5f740d379e896d8f6831c3fa5fc63d434b9`
Integrator branch: `integration/wave-1`

## Recovery verification

All six expected recovery commits exist, are reachable from their named
branches, match their `origin/recovery/*` refs, and their dedicated worktrees
were clean at inspection time.

| Unit | Recovery branch | Commit | Push status | Provisional migration | Final reservation | Worktree |
| --- | --- | --- | --- | --- | --- | --- |
| 01 collection controls | `recovery/01-collection-controls` | `6b2e59aaf5b0f7588b53426c62e2e5a4492cf840` | Pushed; origin matches | `050_collection_controls` | `050_collection_controls` | clean |
| 02 enrichment operations | `recovery/02-enrichment-operations` | `00dfb95e7611277cbcccbce5277c5b7e7131f225` | Pushed; origin matches | `050_enrichment_operations` | `051_enrichment_operations` | clean |
| 03 deterministic evaluation | `recovery/03-deterministic-evaluation` | `e77add5036cca5c4561cd78305a61afe35f19127` | Pushed; origin matches | none | none | clean |
| 04 publication rollback | `recovery/04-publication-rollback` | `054b713e3a8e6ee0d2d82008a50d0aee73a943b5` plus `d571d63b011996abce24b43a03ca314ad79262a5` | Pushed; origin matches | `050_publication_policy_history` | `052_publication_policy_history` | clean |
| 05 audit permissions | `recovery/05-audit-permissions` | `0344dd452e2af0136a16dce0e97941825639bd9f` | Pushed; origin matches | `053_acquisition_audit_permissions` | `053_acquisition_audit_permissions` | clean |
| 06 company reconciliation | `recovery/06-company-reconciliation` | `5e4b846f148f0eefe5aacfd97c2f4a8da5950cfe` | Pushed; origin matches | `054_company_identity_reconciliation` | `054_company_identity_reconciliation` | clean |

## Dependency order

1. `050_collection_controls`: bounds acquisition requests/jobs and persists
   collection closure metadata.
2. Unit 03 deterministic evaluation: offline-only and migration-free; it
   extends the 049 enrichment contracts/fixtures without runtime activation.
3. `051_enrichment_operations`: depends on 049 enrichment evidence/cache state;
   remains report-only with zero external budgets.
4. `052_publication_policy_history`: depends on the acquisition publication
   surfaces and must preserve the current publication head.
5. `053_acquisition_audit_permissions`: wraps acquisition mutation surfaces
   with granular authorization and immutable audit recording.
6. `054_company_identity_reconciliation`: changes canonical company identity
   and reconciliation state after the authorization/audit surfaces are present.

## Integration acceptance rules

- Do not merge from recovery branches directly into production.
- Keep providers, AI, external datasets, and paid services disabled.
- Do not change publication heads or published jobs unless explicitly required;
  none of Wave 1 authorizes an automatic publication.
- After each unit: focused tests, combined regression tests, migration registry
  uniqueness/order checks, then an integration commit when repairs are needed.

