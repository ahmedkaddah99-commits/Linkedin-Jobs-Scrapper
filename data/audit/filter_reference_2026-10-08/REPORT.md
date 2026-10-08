# Runr reference filter implementation — 2026-10-08

Reference: the owner-provided Jobright browser recording. The recording was used
as a visual/interaction reference, not as a source of agent instructions.

## Result

The existing four-section drawer remains the full criteria editor:

- Basic Job Criteria: categorized/searchable functions, title exclusions, job
  types, work models, country and multiple areas, levels, experience and posting age.
- Compensation & Sponsorship: annual salary, currency, H1B sponsorship,
  clearance/citizenship exclusions.
- Areas of Interests: included/excluded industries and skills, IC/manager role type.
- Company Insights: companies, stages, staffing exclusions and hidden companies.

Quick menus now edit the same criteria with draft selection and Confirm. Choice
values are shared with the backend. Multi-selects survive query serialization and
account-owned saved filters. Drawer summary chips include numeric and exclusion
criteria. Clear actions, sliders, Open to all numeric criteria, searchable job
functions, keyboard closing and focus return are implemented. Mobile has a compact
scrollable section bar and a full-width drawer.

Backend predicates run before pagination. Enum comparisons use exact normalized
scalar/array membership. Countries recognize names/codes without matching short
codes against unrelated location text. Experience keeps decimals and numeric
validation rejects invalid bounds. Annual salary converts monthly values, supports
a single disclosed endpoint and an optional exact currency. Company stage reads
company profiles as well as postings. No migration or catalog regeneration is needed.

## Verification and deployment

Frontend unit tests: 177 passed. ESLint and production build pass.
Desktop/mobile Playwright reference-filter and company-search tests pass.
Focused backend verification covers the new contract, existing customer filters,
source-cache equivalence, feed performance and company search/saved filters.
Screenshots were inspected; excessive mobile section height was corrected and
reverified. Browser screenshots are in `frontend/test-results/`.

Initial read-only provider visibility found the frontend and API healthy and
Render deployments live. This change has not been deployed. After deploying both
frontend and API, verify authenticated multi-select queries, country/city scope,
salary currency and period, exact totals/pagination, and saved-filter reloads.

## Limits

Unknown optional metadata remains unknown. A numeric filter excludes missing
values; Open to all clears the bounds and includes them. Hourly salary is not
converted without a known work schedule. Legacy salary without a period retains
the existing annual assumption. Currency is not converted; choose a currency for
comparable salary amounts. City names do not supply inferred country membership.
The reference's radius and unrestricted remote-geography behavior require reliable
geographic/remote eligibility data and are not represented as unsupported controls.
