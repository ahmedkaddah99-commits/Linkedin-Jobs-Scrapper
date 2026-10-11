# RC-009 — Normalization and publication integration

Status: COMPLETE — offline evidence only
Validated: 2026-09-07
Target branch: deployment/render-turso-r2
Validation worktree HEAD: e7662c63082d605d8ae6de090d3a04a55bba6556

## Result

Employer and LinkedIn observations use the existing acquisition ingestion,
canonical company/job, posting-version, staging-publication, and user Jobs
read paths. The adapter transport preserves the source observation contract
and raw producer record while sending bounded, idempotent deliveries to
SqliteAcquisitionStore.ingest_snapshot().

The RC-009 audit found that the existing signature fallback could merge
same-title/same-location postings from different sources without sufficient
evidence. The matcher now permits signature-based reuse only when the candidate
shares a canonical application URL or requisition identifier. Exact source URL
identity remains supported, and ambiguous/different openings stay separate.

## Files

RC-009 change delta:

- backend/repositories/sqlite_acquisition.py
  - requires shared direct application URL or requisition ID for signature-based
    cross-source canonical reuse;
  - keeps closed postings out of the active signature lookup.
- tests/test_phase_b_catalog.py
  - updates cross-source duplicate fixtures to include the strong evidence they
    assert.
- tests/fixtures/rc009_cross_source_identity.json
  - synthetic same-source, cross-source, ambiguous, application-match, and
    requisition-match records.
- tests/test_rc009_normalization_publication.py
  - integration proof for identity safety, raw/provenance retention, invalid
    apply reporting, canonical employer normalization, and Easy Apply exclusion.
- docs/RC009_NORMALIZATION_PUBLICATION.md
- docs/RC009_NORMALIZATION_PUBLICATION.json

Preserved dirty integration surface audited for this ticket:

- backend/acquisition/producer_adapters.py
- backend/acquisition/quality.py
- backend/acquisition/phase_b.py
- backend/repositories/sqlite_acquisition.py
- backend/repositories/sqlite_personalized_jobs.py
- backend/application/services.py
- tests/test_observation_store_integration.py
- tests/test_rc010_first_acquisition_slice.py
- tests/test_publication_policy_rollback.py
- tests/test_acquisition_mapping_contract.py
- tests/test_acquisition_quality.py
- tests/test_producer_adapters.py

No employer producer or LinkedIn producer collector was edited. Existing dirty
exporter and unrelated worktree changes were preserved. No commit was made.

## Acceptance evidence

- Both source adapters deliver to the same SQLite ingestion contract. The
  staging read model contains canonical company/job fields, and the existing
  Jobs route reads the published head without creating acquisition requests.
- A 26-observation company proves the >25 boundary: intermediate delivery is
  non-final/non-closure-safe; the final delivery carries the complete external
  ID inventory; replay returns the same receipt and leaves 26 observations and
  26 active source states rather than duplicating them.
- Same-title/same-location employer openings with different application URLs
  remain separate. A LinkedIn observation merges only when it shares the
  employer's canonical application URL or requisition ID.
- Raw producer data, source metadata, source IDs, scan IDs, and the observation
  contract remain queryable after canonical publication.
- A foreign source employer label is normalized to the configured canonical
  employer while the original producer label remains in retained raw evidence.
- An invalid application URL remains unresolved and is surfaced in staging
  preflight as broken_apply_destinations; it is not represented as a verified
  direct-apply URL. The existing publication policy remains report-only for
  missing/broken apply data.
- Existing Phase B policy rejects an Easy Apply-only record as
  unsupported_application_method.
- A failed/partial source sends valid_snapshot=False and closure_safe=False; it
  changes that source to unknown and does not replace the previous valid public
  publication with an empty catalog.
- Publication promotion and stale-head rollback behavior remain covered by the
  existing publication-policy tests.

## Commands and results

All Python commands used the repository virtual environment required by
AGENTS.md:

~~~powershell
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' --version
~~~

Result: Python 3.12.7.

~~~powershell
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m pytest tests/test_phase_b_catalog.py tests/test_rc009_normalization_publication.py tests/test_observation_store_integration.py tests/test_rc010_first_acquisition_slice.py tests/test_publication_policy_rollback.py tests/test_acquisition_mapping_contract.py tests/test_acquisition_quality.py tests/test_producer_adapters.py -q
~~~

Result: 45 passed, 4 subtests passed in 27.77s.

~~~powershell
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m ruff check backend/repositories/sqlite_acquisition.py backend/acquisition/producer_adapters.py backend/acquisition/phase_b.py tests/test_phase_b_catalog.py tests/test_rc009_normalization_publication.py tests/test_observation_store_integration.py tests/test_rc010_first_acquisition_slice.py tests/test_publication_policy_rollback.py
~~~

Result: All checks passed!.

~~~powershell
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m py_compile backend/repositories/sqlite_acquisition.py backend/acquisition/producer_adapters.py backend/acquisition/phase_b.py tests/test_phase_b_catalog.py tests/test_rc009_normalization_publication.py tests/test_observation_store_integration.py tests/test_rc010_first_acquisition_slice.py tests/test_publication_policy_rollback.py
~~~

Result: exit code 0, no compiler output.

~~~powershell
git diff --check
~~~

Result: no whitespace errors. Git emitted only existing LF/CRLF conversion
warnings for the dirty worktree.

## Limitations

- This is synthetic/offline evidence using temporary SQLite databases and
  in-process route dispatch. It is not proof of a live Render, Turso, R2,
  employer, or LinkedIn run.
- No network, provider, credential, deployment, production, or browser-visual
  test was run, per ticket scope.
- The default publication policy intentionally records broken/missing apply
  destinations as report-only staging warnings. Easy/Quick Apply-only input is
  rejected by the existing Phase B policy before normal acquisition publication.
- RC-010's separate dual-source staging/product-slice ticket is not started.

## Rollback

No rollback was needed. The worktree was not reset, cleaned, merged, pushed, or
deployed.

If this RC-009 delta must be reverted before commit:

1. Preserve the unrelated dirty changes and inspect only the RC-009 hunks with
   git diff -- backend/repositories/sqlite_acquisition.py tests/test_phase_b_catalog.py.
2. Use apply_patch to remove the added evidence-gated matcher parameters and
   restore the prior call/SQL only if explicitly directed; do not revert the
   whole already-dirty SQLite repository file.
3. Remove only the RC-009-only files after confirming their absolute paths:
   tests/fixtures/rc009_cross_source_identity.json,
   tests/test_rc009_normalization_publication.py, and the two RC-009 evidence
   documents. Do not run git clean.
4. Re-run the Python-version check, focused pytest command, Ruff, py_compile, and
   git diff --check.

## Next gate

RC-009 is complete. Stop here. RC-010 may begin only in a subsequent scoped
ticket after this evidence is reviewed.
