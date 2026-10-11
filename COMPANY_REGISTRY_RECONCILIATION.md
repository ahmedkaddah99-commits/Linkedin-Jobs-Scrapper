# RC-003 company registry reconciliation

Status: complete locally on 2026-09-06. This is an offline, read-only
reconciliation evidence record for `deployment/render-turso-r2`.

Starting target revision: `e7662c63082d605d8ae6de090d3a04a55bba6556`.
The target worktree was already dirty. The modified exporter/producer files
were not edited:

- `scripts/build_master_jobs_catalog.py`
- `scripts/master_employer_jobs_catalog.py`
- `scripts/master_linkedin_jobs_catalog.py`
- `tests/test_master_employer_jobs_catalog.py`
- `tests/test_master_linkedin_jobs_catalog.py`

No reset, clean, pull, merge, push, deployment, live request, browser launch,
or network test was performed. RC-004 stable-ID allocation/backfill and RC-005
eligibility-manifest work were not started.

## Result

The new reconciliation path is deliberately non-mutating. It reads an
explicit master CSV and an optional exported application registry, then emits a
reviewable crosswalk proposal. It does not insert/update
`canonical_companies`, `company_identity_keys`, `company_identity_evidence`,
`canonical_company_aliases`, `canonical_company_urls`, or jobs.

The existing application identity tables are sufficient for this ticket, so no
migration was added. The application namespace remains
`canonical_company_<uuid>`; the master `canonical_CompanyID` is represented as
the external reference `master-company:<id>`. A LinkedIn numeric organization
ID is represented as `linkedin-org:<id>` and is never emitted as a Runr
primary key.

## Full local master dry run

Command, run from the target worktree:

```powershell
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m scripts.reconcile_company_registry `
  --input 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\Company-Urls\Master-Company-Url\cleaned\Master-Company-Url-canonical_cleaned_linkedin_ids.csv' `
  --output COMPANY_REGISTRY_RECONCILIATION.json
```

Observed result:

| Measure | Result |
| --- | ---: |
| Input rows / columns | 17,601 / 118 |
| Input SHA-256 | `7f416ec6ebbcb936a42061ef0adaa07e4a6c04d2959d0eb579779126682440d9` |
| Existing master IDs retained as external references | 7,513 |
| Rows without a master ID | 10,088 |
| Rows with durable identity evidence under this report | 17,121 |
| Rows with missing durable identity evidence | 400 |
| Conflicted identity rows | 80 |
| Shared LinkedIn organization groups | 37 |
| Rows in shared-organization groups | 75 |
| Explicit unresolved shared-organization dispositions | 37 |
| Application matches in this run | 0 |
| Automatic merges / application-ID allocations | 0 / 0 |
| Acquisition/publication eligible in RC-003 | 0 |

The application-match count is zero because no application-registry export was
supplied to the full-input command. The reviewed strong-key matching path is
covered by the fixture suite below; this report does not claim that the target
has no canonical application companies.

The report's identity state is intentionally narrower than “some evidence is
present”: a master ID, a valid LinkedIn organization ID, or a reviewed
application match is durable identity evidence. A website domain,
CompanyEnrich ID, name, alias, or LinkedIn URL without a numeric organization
ID remains evidence requiring review unless a reviewed application identity
key proves the match.

## Shared-organization dispositions

The full input exposes the 37 groups below. The input has no row-level reviewed
ownership annotation, so every group receives the explicit disposition
`unresolved_conflict`. No group is assigned to the first sorted employer, and
all observations in those groups remain quarantined for acquisition/publication
ownership review.

| LinkedIn organization ID | Existing master canonical IDs | Rows | Disposition |
| --- | --- | ---: | --- |
| `10019553` | `canonical-5e9c45267d340f79`, `canonical-cb5569d738d08f8b` | 2 | unresolved_conflict |
| `10341517` | `canonical-05d76d6ed0e497d8`, `canonical-4b22d5e0867ee462` | 2 | unresolved_conflict |
| `10557454` | `canonical-0928f268bac270ef`, `canonical-0ebf3c9df40fc2a4` | 2 | unresolved_conflict |
| `112234726` | `canonical-4f1fdb3239066f9b`, `canonical-60ea39cb6a7d42db` | 2 | unresolved_conflict |
| `1181425` | `canonical-09bb173daf7f6eb8`, `canonical-0e928553071fdb0f` | 2 | unresolved_conflict |
| `11833508` | `canonical-11bffb7b655e7ce7`, `canonical-dd6173da5ae8de9c` | 2 | unresolved_conflict |
| `118759` | `canonical-0d9cb584e9847ae1`, `canonical-2692a9c245ab5778` | 2 | unresolved_conflict |
| `14795957` | `canonical-37b89bbea713deee`, `canonical-44b900058c8ed93e` | 2 | unresolved_conflict |
| `150114` | `canonical-47c510a01a3f0673`, `canonical-c8a128f67955be47` | 2 | unresolved_conflict |
| `1541519` | `canonical-948a8a0cdaafcf94`, `canonical-a214146bb65ade7e` | 2 | unresolved_conflict |
| `163562` | `canonical-09881aa7146000d9`, `canonical-e71b0624175cb354` | 2 | unresolved_conflict |
| `1638610` | `canonical-5ed5df0b67ac06fe`, `canonical-ced4923445143530` | 2 | unresolved_conflict |
| `18338740` | `canonical-1d4a38a37458cac5`, `canonical-d79cc035550893e1` | 2 | unresolved_conflict |
| `2079755` | `canonical-4b4f41e18e83ecbb`, `canonical-acd09216fa210b65` | 2 | unresolved_conflict |
| `22292078` | `canonical-5d1879fc7e177343`, `canonical-83cf1e841b3c7b25` | 2 | unresolved_conflict |
| `264462` | `canonical-0140d65de6075693`, `canonical-176bf98618184707` | 2 | unresolved_conflict |
| `32265` | `canonical-ce03f4d5a5d7f239`, `canonical-d079b8afead78d0f` | 2 | unresolved_conflict |
| `35446509` | `canonical-39b9e99bd1fde520`, `canonical-43db659f55e10520` | 2 | unresolved_conflict |
| `370470` | `canonical-9f96163fcc1b9295`, `canonical-9fa9b738dc92ba60` | 2 | unresolved_conflict |
| `37421346` | `canonical-6c0c0cd8c4cb2728`, `canonical-8d7a4649d198d423` | 2 | unresolved_conflict |
| `39162` | `canonical-388202686dd575e0`, `canonical-bdb3c2e4d6f5d875`, `canonical-f18bd49f7996a575` | 3 | unresolved_conflict |
| `41311474` | `canonical-33354594cc2ff6ff`, `canonical-bf1e8257d059c7ef` | 2 | unresolved_conflict |
| `436847` | `canonical-3e82365d154374bd`, `canonical-ca63c6b9c3718728` | 2 | unresolved_conflict |
| `49132702` | `canonical-d2dc905496999351`, `canonical-f342b3a803ebd5c1` | 2 | unresolved_conflict |
| `5037767` | `canonical-35875f8bb270cafa`, `canonical-b3a70d7e011c632e` | 2 | unresolved_conflict |
| `5340578` | `canonical-24a8660f4e119bb3`, `canonical-f9d07faaea83ea83` | 2 | unresolved_conflict |
| `54305215` | `canonical-0a3569ef3394c60b`, `canonical-f9312dc7c326b648` | 2 | unresolved_conflict |
| `6819976` | `canonical-0d1c14915534f923`, `canonical-2bb8283a5502555b` | 2 | unresolved_conflict |
| `69479174` | `canonical-ce492f04c4ddb97d`, `canonical-ef4e724c0b909706` | 2 | unresolved_conflict |
| `71684757` | `canonical-4f3b33b8236b0e29`, `canonical-9897ce57b7226b8a` | 2 | unresolved_conflict |
| `75635143` | `canonical-5229521bb1ab9b31`, `canonical-d2b9525b29621512` | 2 | unresolved_conflict |
| `80996274` | `685b353f-8add-5c3c-a485-a21f7ed926a1`, `canonical-c5555b8204e2d1c8` | 2 | unresolved_conflict |
| `817694` | `canonical-6d3d5ecff547cb21`, `canonical-75ca82643fd44e94` | 2 | unresolved_conflict |
| `84532404` | `canonical-97b86c32b9b22701`, `canonical-b0ea09048adb1df7` | 2 | unresolved_conflict |
| `9342360` | `canonical-6b6a2e19b24e7b5c`, `canonical-b5b01185addd6468` | 2 | unresolved_conflict |
| `93835160` | `canonical-1a96f166fe1f7a73`, `canonical-e38729f927550bcb` | 2 | unresolved_conflict |
| `9756990` | `canonical-b216458b76bc1e4a`, `canonical-d600998663214ce5` | 2 | unresolved_conflict |

The fixture review file demonstrates the three allowed dispositions:
`same_entity_alias`, `distinct_related_employers`, and
`unresolved_conflict`. An annotation is accepted only when its master-ID set
exactly equals the observed group; incomplete annotations remain unresolved.

## Field-level mapping and precedence

`COMPANY_REGISTRY_RECONCILIATION.json` contains one `field_mapping` entry for
each of the 118 observed input columns. The policy is:

| Master fields | Application tables/fields | Export use | Precedence |
| --- | --- | --- | --- |
| `canonical_CompanyID` | crosswalk external-reference field | `canonical_company_id` only after review | preserve existing master reference |
| `company_name` | `canonical_companies.canonical_name` | display/employer name | reviewed canonical name, then observation |
| `linkedin_slug`, renamed names | `canonical_company_aliases` | historical/display alias | append reviewed alias |
| `linkedin_company_id` and resolver status/source fields | `company_identity_keys`, `company_identity_evidence` | source organization identity | reviewed source identity, then review |
| `companyenrich_id` | identity evidence and profile provenance | enrichment provenance | reviewed external identity, then review |
| `website_url` | `canonical_company_urls`, URL occurrences | homepage/source evidence | reviewed official URL, then observed URL |
| `linkedin_company_url` | source URL and URL occurrences | source provenance | reviewed organization profile, then review |
| enrichment/profile columns | `canonical_company_profiles.profile_json` | profile fields with provenance | stronger verified field, then richer observation |
| `companyenrich_free_logo_url` | `company_logo_enrichments` provenance | logo evidence | retain reviewed logo evidence |
| `Column1`–`Column9` and any other unmapped input | raw-column sidecar/provenance | preserved input field | retain raw value |

Names and domains are candidate evidence only. A shared hosting or ATS domain
does not merge companies. Existing application IDs are reused only when a
reviewed strong identity key resolves to exactly one application company;
multiple application matches remain reviewable.

Identity and enrichment are separate: a provisional record can carry a master
reference or source evidence while `eligible_for_acquisition_or_publication`
remains false. School and showcase LinkedIn pages are retained as source URL
evidence but quarantined from employer acquisition and do not create a
LinkedIn organization identity key.

Renames create alias candidates against the same master ID. Changed websites
create URL-history candidates and are appended as occurrences after review;
they do not replace the established ID. Historical jobs and user references
therefore remain attached to the application company record.

## Verification

Python interpreter verification:

```text
Python 3.12.7
```

Focused RC-003 command:

```powershell
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m pytest -q tests/test_company_registry_reconciliation.py
```

Result: `11 passed in 2.40s`.

The tests use only local fixtures and cover reviewed strong-key matches,
master/application namespace separation, name/domain collision review, shared
organization dispositions, exact annotation validation, school/showcase quarantine,
duplicate reviewed-domain collision review,
missing identity versus enrichment, rename/website history, raw-column
mapping, and order-stable fingerprints.

The pre-existing acquisition/identity regression suite was previously
validated during RC-002 at `130 passed in 30.82s`; the RC-003 fixture suite is
additive. The full-input CLI run above returned exit code 0 and made no network
requests.

## Limitations

- The target has no application database snapshot in this checkout, so the
  full master run was not a live application crosswalk. Supply an exported
  registry with `--application-registry` for reviewed strong-key mapping.
- The 37 full-input groups have aggregate source rows but no reviewed
  row-level disposition in the supplied command; they are explicitly
  unresolved, not resolved as aliases or subsidiaries.
- The report records structural URL validity and input presence, not ownership,
  reachability, freshness, provider capacity, or live source coverage.
- No IDs were allocated, no aliases were written, no application data was
  migrated, and no acquisition/publication manifest was created. Those are
  later RC-004/RC-005 responsibilities.

## Rollback

This ticket's implementation is isolated to the new module, CLI, fixtures,
tests, and the two RC-003 evidence artifacts. Roll back by moving aside or
removing only these RC-003 additions:

- `backend/application/company_registry_reconciliation.py`
- `scripts/reconcile_company_registry.py`
- `tests/test_company_registry_reconciliation.py`
- `tests/fixtures/rc003_company_registry.csv`
- `tests/fixtures/rc003_application_registry.json`
- `tests/fixtures/rc003_shared_organization_dispositions.json`
- `COMPANY_REGISTRY_RECONCILIATION.md`
- `COMPANY_REGISTRY_RECONCILIATION.json`

No migration rollback or data repair is required because the reconciliation
path performed no application writes. Do not reset or clean the worktree:
preserve the pre-existing dirty exporter/producer changes and all earlier
RC-001/RC-002 evidence artifacts.
