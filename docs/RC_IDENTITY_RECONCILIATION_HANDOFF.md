# RC-001–RC-009 identity reconciliation handoff

Date: 2026-09-07
Target checkout: `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview`
Target branch: `deployment/render-turso-r2`
HEAD: `e7662c63082d605d8ae6de090d3a04a55bba6556`
Python: `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe` — Python 3.12.7

This is an offline reconciliation handoff. The target worktree was already
dirty and all existing tracked and untracked work was preserved. No reset,
clean, pull, merge, commit, push, deployment, production migration, live
request, browser/provider request, or paid enrichment was performed.

## Actual status

| Ticket | Status at this handoff | Meaning |
| --- | --- | --- |
| RC-001 | verified offline | The transfer/evidence work is present; deployed-state verification remains external. |
| RC-002 | verified offline | `BASELINE_METRICS.md/.json` records offline throughput, cost, reliability, recovery, storage, and workload measurements/limits. It makes no unmeasured capacity claim. |
| RC-003 | verified offline; external/data action pending | The read-only reconciliation and conflict packet are complete. An application-registry export and reviewer ownership decisions are still missing. |
| RC-004 | verified offline; external/data action pending | The full-list mapping is a dry run only. No approved mapping was supplied and no output copy was applied. |
| RC-005 | verified offline; runtime integration pending | The versioned manifest, raw sidecar, and wrappers are verified. No inspected scheduler/runtime path proves that raw producer CLIs have been replaced by the wrappers. |
| RC-006a | verified offline | Resolver safety, contradictory-ID handling, budgets, cooldowns, circuit state, and recovery-probe behavior pass offline. |
| RC-006b | external/provider authorization pending; not started | The exact bounded pilot is prepared below. It was not executed and is not a prerequisite for verified-company acquisition. |
| RC-007 | verified offline | Employer, LinkedIn, and combined exports are independently controlled. |
| RC-008 | verified offline | Both producer adapters and final snapshot controls pass offline. |
| RC-009 | verified offline; staging/live evidence pending | Normalization, strong-evidence matching, publication safety, and rollback behavior pass synthetic/offline tests. |

## RC-003 and RC-004 reconciliation

The relevant evidence files are `COMPANY_REGISTRY_RECONCILIATION.md/.json` and
`RC004_BACKFILL_REPORT.md/.json`. Their source snapshot is the external local
master recorded in the reports:

`C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\Company-Urls\Master-Company-Url\cleaned\Master-Company-Url-canonical_cleaned_linkedin_ids.csv`

Its verified shape is 17,601 rows and 118 columns with SHA-256
`7f416ec6ebbcb936a42061ef0adaa07e4a6c04d2959d0eb579779126682440d9`.

### Counts and disposition

| Measure | Verified count | Interpretation |
| --- | ---: | --- |
| Existing master IDs | 7,513 | Preserved as master external references; no application IDs were allocated. |
| Missing/placeholder master IDs | 10,088 | Accounted for by the RC-004 dry run. |
| RC-003 rows with durable identity evidence | 17,121 | Evidence state only; it does not imply application ownership or acquisition eligibility. |
| RC-003 rows missing durable identity evidence | 400 | Remain reviewable/provisional. |
| RC-004 existing rows retained | 7,438 | Eligible in the proposed mapping unless later policy/evidence blocks them. |
| RC-004 existing rows in conflict quarantine | 75 | Their original IDs remain present; they are not silently rewritten. |
| Missing rows matched to an existing ID | 128 | Proposal only; not approved/applied. |
| Missing rows with deterministic new-ID proposals | 9,554 | Proposal only; not approved/applied. |
| Missing rows provisional | 400 | Not eligible; requires review/enrichment. |
| Missing rows quarantined | 6 | Not eligible; requires review. |
| Missing rows rejected | 0 | No row was silently discarded. |
| Missing-ID rows with an eligible dry-run proposal | 9,682 | `128 + 9,554`; this is the reported approval queue, not applied data. |
| Shared LinkedIn organization groups | 37 | Every group remains `unresolved_conflict`. |
| Rows with unresolved shared-organization ownership | 80 | All are blocked from acquisition/publication. |

The `37 / 80` and `37 / 75` values describe different views in the old
artifacts. RC-003 counts 80 rows whose current ownership state is conflicted.
The original RC-005 `ownership_review` subrecords listed only the 75 rows that
already had canonical IDs; five additional rows shared those organizations but
had no ID. The reconciled RC-005 cycle below includes all 80 rows in its review
packet. No ownership decision was inferred from row order, company name, or
fan-out.

### Application state and proposed-ID safety

The reports explicitly record:

- `application_registry_supplied=false` for the full RC-003 run;
- `application_companies_matched=0`, which means no application registry was
  supplied to that run, not that the target application has zero companies;
- `approved_mapping_supplied=false`;
- `approved_identity_keys=[]` and `approved_row_fingerprints=[]`;
- `application_tables_written=false`;
- `automatic_merge=false`, `automatic_publication=false`, and
  `allocates_application_ids=false`.

The current reconciled manifest has only `canonical_id_state=input` for the
7,513 existing-ID rows and `canonical_id_state=missing` for the 10,088
missing-ID rows. The 9,682 pending proposals have no effective canonical ID,
zero of them produce a collector task, and all 7,407 materialized source tasks
have one nonempty existing canonical ID. Therefore a deterministic proposed
ID cannot silently enter acquisition eligibility.

Every source row remains accounted for: 17,601 manifest row records and
17,601 sidecar records, with `all_input_rows_mapped_or_blocked=true`.

### Required reviewer/application packet

No one should approve mappings in this handoff. A reviewer must return a
versioned packet keyed to the unchanged source hash. Each row-level entry must
contain:

```text
row_fingerprint
source_row_number
original_canonical_CompanyID
proposed_canonical_company_id
decision: retain_existing | match_existing | approve_new | provisional | quarantine | reject
evidence_refs
reason
reviewer
reviewed_at
```

For each of the 37 LinkedIn organization groups, the packet must list the
numeric organization ID, all 80 applicable source row numbers across the
groups, all observed existing canonical IDs, and one explicit disposition:
`same_entity_alias`, `distinct_related_employers`, or
`unresolved_conflict`. It must include evidence references (official site,
LinkedIn organization page, registry relationship, or equivalent) and reviewer
identity/time. `unresolved_conflict` remains the safe disposition when the
evidence does not establish ownership.

After review, the existing guarded copy procedure remains the only application
path:

```powershell
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' scripts\backfill_company_ids.py `
  --input <unchanged-master.csv> `
  --output RC004_APPLY_REPORT.json `
  --approved-mappings <reviewed-approved-mappings.json> `
  --apply-output <new-master-copy.csv> `
  --manifest-output <mapping-manifest.json>
```

That command must recheck the input hash, require coverage and explicit
approval for every new anchor, write the mapping manifest before the new copy,
refuse to overwrite the source, and create `<new-master-copy.csv>.before-rc004.bak`
only when replacing an intentionally selected prior output. It was not run in
this pass. It does not write application tables; an application-registry import
and any application-side mapping remain separate authorized actions.

## RC-005 manifest and collector gate

The original immutable artifacts remain untouched:

- `SOURCE_ELIGIBILITY_MANIFEST_RC005.json` — original manifest hash recorded in
  its evidence: `92186e75e30534f5bb4e1e206e3c5c2d0ce333d8c35f04ccce1ee7d6f3997a34`;
- `SOURCE_ELIGIBILITY_RAW_RC005.jsonl` — sidecar SHA-256
  `cda46fee441e2e6e02d52ffe2fc86ae33121c82edc9f0636562367b63cbb5ef7`.

The corrected immutable cycle is:

- `SOURCE_ELIGIBILITY_MANIFEST_RC005_RECONCILED.json`;
- `SOURCE_ELIGIBILITY_RAW_RC005_RECONCILED.jsonl`;
- cycle `rc005-reconciled-20260907`;
- manifest hash `6bfcba5c01985402d2d1278e8b726baa8e4ac3332e6527be40bc433ab663e447`;
- sidecar SHA-256
  `cda46fee441e2e6e02d52ffe2fc86ae33121c82edc9f0636562367b63cbb5ef7`.

The corrected bundle retains the same source hash, header hash
`28f68ab82a4710575f0a0c7fd43992e121fa45b0f1fd150e37c73a83f0ea2460`, 118 raw
columns, 17,601 source rows, 7,513 mapped rows, and 9,682 pending missing-ID
proposals. Its counts are:

- 7,407 source associations/tasks: 5,135 employer-site and 2,272 LinkedIn;
- initial dual-source pilot: 3,148 tasks, exactly 1,574 per source;
- later controlled single-source population: 4,259 entities;
- blocked rows/entities: 11,768;
- duplicate rows/associations: 0 / 0;
- ownership review: 37 groups and 80 rows, all `unresolved_conflict` and
  `review_required=true`;
- `source_untouched=true`, `application_tables_written=false`,
  `historical_absence_closure_authorized=false`, and
  `eligible_tasks_have_one_canonical_id=true`.

Both supported wrappers call `require_eligibility_manifest()`, verify the
manifest and sidecar hashes, materialize a source-specific input outside the
master snapshot, and pass only validated task representatives to the producer
runner:

- `scripts/run_manifested_employer.py`;
- `scripts/run_manifested_linkedin.py`.

Both default to `pilot_only=True` and switch to source-specific expansion only
when `--include-single-source` is explicitly supplied. The default pilot is
therefore the 3,148 dual-source tasks, not all employer-only or LinkedIn-only
tasks. The low-level producer CLIs remain source-owned and can still be
invoked directly by an operator; the inspected target contains no proven
scheduler/Render command wiring that forces the wrappers. Chat B must close
that runtime integration gap before a scheduled run is authorized.

## RC-006a and bounded RC-006b preparation

RC-006a remains complete offline. Its existing evidence records 66 passing
tests, Ruff success, compilation success, and zero network calls. It proves
separate queues, evidence precedence, contradictory-ID quarantine,
restart-persistent cooldown/budgets, circuit opening, one recovery probe, and
the mostly-blocked request bound.

RC-006b was not started. It requires explicit provider/account authorization
and is not a dependency for acquisition of already verified companies.

### Exact proposed pilot packet (not executed)

The operator must first create `RC006B_REVIEWED_INPUT.csv` offline from the
reconciled manifest. It must contain at most 25 unique normalized LinkedIn
organization URLs, one representative row per URL, selected by a reviewer
from currently blocked rows whose remaining work is numeric-ID evidence. Do
not select unresolved ownership-conflict rows, use name-only matching, or
include already dual-ready rows. Record the selected row fingerprints and the
manifest ID/hash alongside the input. Validate before any provider call:

- input rows `<= 25` and unique normalized LinkedIn organization URLs `<= 25`;
- source/manifest hash and raw sidecar hash match the reviewed packet;
- no selected row has an approved backfill ID or unresolved ownership
  disposition;
- output path is not the input path;
- no application-table or master-copy write is part of the run.

The conservative first pass is Webshare-only and non-paid. Required provider
settings are one authorized Webshare account and one configured proxy endpoint
(`WEBSHARE_PROXY_URL`, or the approved username/password plus host/port
settings). Do not rotate proxies, start a browser, or enable ScrapeOps in this
pass. Never put provider secrets in the command line, report, or request log.

The exact command shape is:

```powershell
$py = 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe'
& $py scripts\run_linkedin_company_id_resolution.py `
  --input RC006B_REVIEWED_INPUT.csv `
  --output RC006B_RESOLVED.csv `
  --state-dir RC006B_STATE `
  --report RC006B_REPORT.json `
  --markdown-report RC006B_REPORT.md `
  --request-log RC006B_REQUESTS.jsonl `
  --workers 1 `
  --webshare-only `
  --webshare-timeout 10 `
  --scrapeops-timeout 30 `
  --scrapeops-budget 0 `
  --max-requests-total 25 `
  --max-requests-per-provider 25 `
  --rolling-budget-window-seconds 86400 `
  --retry-cooldown-seconds 30 `
  --retry-cooldown-max-seconds 900 `
  --circuit-failure-threshold 3 `
  --circuit-open-seconds 300 `
  --checkpoint-every 1 `
  --checkpoint-seconds 10
```

Do not pass `--retry-unresolved`, `--browser-first`, or
`--webshare-rotate-each-request` on the first pass. The enforced ceiling is at
most 25 outbound requests in the rolling 24-hour window, at most 25 Webshare
requests, zero ScrapeOps requests, and zero paid ScrapeOps credits. The
resolver’s two-request Webshare sequence remains subject to the global cap.

Stop the pilot immediately if any of the following occurs: a 403/429/challenge
or blocked response; a provider configuration or account mismatch; any request
or credit reservation beyond the configured caps; source-hash drift; an
unexpected provider billing signal; a worker exception; an ambiguous response
containing more than one contextual LinkedIn ID; or any attempted source,
application-table, or input overwrite. `AMBIGUOUS`, `UNRESOLVED`, and
`CREDIT_BUDGET_EXHAUSTED` are honest terminal/review outcomes, not reasons to
guess an ID or widen the pilot.

Expected evidence, if this separately authorized pilot is later run:

1. reviewed input row/URL list, manifest ID/hash, source hash, and output hash;
2. resolver report, markdown report, request log, resolver SQLite state, and
   separate `resolver_safety.sqlite3` state;
3. request count by provider/stage/status, latency, retry/cooldown/circuit
   events, actual/estimated/billing-unknown credits, and cap reservations;
4. resolved/ambiguous/unresolved counts with every contextual ID retained;
5. proof that the source CSV, master copy, application tables, and existing
   acquisition eligibility were unchanged; and
6. a new reviewed manifest diff if any verified ID is later considered for
   eligibility.

A later ScrapeOps fallback is a separate authorization decision. If approved,
it must use an explicitly supplied `SCRAPEOPS_API_KEY`, retain the same
one-worker/25-request/24-hour ceiling, and set a numeric native-credit cap no
higher than 25 (`basic=1`, `residential=10`, `render_js_residential=25` per
request). It is not part of this handoff’s executed work.

## RC-007–RC-009 and RC-017 reconciliation

The older evidence remains valid as offline evidence and was not overwritten:

- RC-007: 114 producer/export tests passed; source-specific export failure and
  combined-projection controls remain separate.
- RC-008: 7 adapter/integration tests passed; intermediate delivery remains
  non-closure-safe and `send_final()` requires a complete source inventory.
- RC-009: 45 tests and 4 subtests passed; strong application-URL/requisition
  matching, raw/provenance retention, invalid-apply reporting, and publication
  rollback remain intact.

The current matcher in `backend/repositories/sqlite_acquisition.py` was not
weakened. Signature matching still requires shared direct application URL or
requisition evidence; same-title/same-location observations from different
sources remain separate without that evidence. The RC-017 fixture was adjusted
only to provide an explicit shared `REQ-1` requisition for the test that
expects a newer employer version to supersede an older cross-source version.
The deterministic task SQL ordering remains:

```text
n26_greenhouse, qonto_lever, then created_at, target_id, task_id for the rest
```

An isolated temporary SQLite probe returned exactly
`['n26_greenhouse', 'qonto_lever', 'other_fixture']` when tasks were inserted in
reverse order. No repository database was used.

## Changed files in this reconciliation pass

- `backend/application/source_eligibility_manifest.py` — include every current
  source row for a conflicting organization in its review subrecord, not only
  rows that already have a canonical ID.
- `tests/test_source_eligibility_manifest.py` — regression for an unmapped row
  sharing a conflicted organization; it remains blocked and is included in the
  review packet.
- `tests/test_phase_a_rc017.py` — explicit requisition evidence in the stale
  fixture expectation; the newer strong-evidence matcher is preserved.
- `SOURCE_ELIGIBILITY_MANIFEST.md` — records the immutable-cycle discrepancy
  and corrected cycle.
- `SOURCE_ELIGIBILITY_MANIFEST_RC005_RECONCILED.json` and
  `SOURCE_ELIGIBILITY_RAW_RC005_RECONCILED.jsonl` — new immutable corrected
  evidence; the original RC-005 files were not overwritten.
- `docs/RC_IDENTITY_RECONCILIATION_HANDOFF.md` — this handoff.

No employer producer or LinkedIn producer implementation was edited in this
pass. Existing dirty exporter, producer, application, migration, storage, and
later-ticket changes were not reset, cleaned, or rolled back.

## Commands and results

Interpreter verification:

```text
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' --version
Python 3.12.7
```

RC-005 corrected bundle generation (offline; source read only):

```text
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' scripts/build_source_eligibility_manifest.py --input 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\Company-Urls\Master-Company-Url\cleaned\Master-Company-Url-canonical_cleaned_linkedin_ids.csv' --output SOURCE_ELIGIBILITY_MANIFEST_RC005_RECONCILED.json --raw-sidecar SOURCE_ELIGIBILITY_RAW_RC005_RECONCILED.jsonl --cycle-id rc005-reconciled-20260907 --as-of 2026-09-06T00:00:00Z --max-evidence-age-days 30 --registry-report COMPANY_REGISTRY_RECONCILIATION.json --backfill-report RC004_BACKFILL_REPORT.json
```

Result: 17,601 rows, 118 columns, 7,513 mapped rows, 9,682 pending missing-ID
proposals, 7,407 tasks, 3,148 pilot tasks, 37 conflict groups, and 80 review
rows. Source unchanged; application tables untouched.

Bounded reconciliation/regression suite:

```text
& $py -m pytest -q tests/test_company_registry_reconciliation.py tests/test_company_id_backfill.py tests/test_source_eligibility_manifest.py tests/test_rc006_resolution_safety.py tests/test_producer_adapters.py tests/test_phase_b_catalog.py tests/test_rc009_normalization_publication.py tests/test_phase_a_rc017.py
```

Result after the fixture reconciliation: **52 passed in 23.61s**. The first
run exposed one stale RC-017 assertion; it failed because the fixture had no
strong cross-source evidence. After adding `REQ-1` to that fixture, the same
bounded command passed. No live/provider calls were made.

Static validation:

```text
& $py -m ruff check backend/application/source_eligibility_manifest.py tests/test_source_eligibility_manifest.py tests/test_phase_a_rc017.py backend/repositories/sqlite_acquisition.py tests/test_rc009_normalization_publication.py scripts/run_manifested_employer.py scripts/run_manifested_linkedin.py scripts/run_linkedin_company_id_resolution.py
```

Result: **All checks passed!**

```text
& $py -m py_compile backend/application/source_eligibility_manifest.py tests/test_source_eligibility_manifest.py tests/test_phase_a_rc017.py backend/repositories/sqlite_acquisition.py tests/test_rc009_normalization_publication.py scripts/run_manifested_employer.py scripts/run_manifested_linkedin.py scripts/run_linkedin_company_id_resolution.py
```

Result: exit code 0.

## Handoff to Chat B

Chat B should review this packet without approving identity ownership or
editing the employer/LinkedIn producer implementations:

1. confirm the scheduled/Render worker entrypoints invoke the two manifest
   wrappers and cannot receive a raw master CSV;
2. review the 37-group/80-row ownership packet and return reviewer evidence,
   not inferred assignments;
3. provide any separately authorized provider/account/quota settings needed
   for RC-006b, without executing a request in this handoff; and
4. preserve the original RC-005 cycle and all dirty worktree changes while
   consuming the reconciled cycle only after its hash and review status are
   accepted.

The application/data owner must separately supply an application-registry
export and an approved mapping packet before any RC-004 copy application. No
later acquisition ticket should treat the dry-run proposals as ownership
decisions.

## Targeted rollback

No data rollback is required: this pass wrote no source master, application
table, acquisition database, provider state, or production artifact.

If the corrected RC-005 evidence must be withdrawn, stop using the reconciled
cycle and retain the original immutable `SOURCE_ELIGIBILITY_MANIFEST_RC005.*`
files. Archive or remove only the two explicitly named reconciled files after
confirming their absolute paths; do not use `git clean` or a broad cleanup.

If the code change must be withdrawn, remove only the
`organization_row_numbers` review-packet hunk and its focused test with
`apply_patch`, then rerun the version check, focused tests, Ruff, compilation,
and `git diff --check`. Do not revert the RC-009 strong-evidence matcher or
whole-file dirty SQLite/exporter changes. Keep the RC-017 requisition fixture
aligned with the current matcher unless the matcher itself is explicitly
changed and retested.

For a later authorized RC-004 copy rollback, stop consumers of the generated
copy, preserve its report/manifest, verify the prior output and
`<output>.before-rc004.bak` hashes, and restore only that targeted output after
authorization. The original source master remains the rollback source.

Stop after this handoff. RC-006b and any later ticket require their own
explicit scope and evidence.
