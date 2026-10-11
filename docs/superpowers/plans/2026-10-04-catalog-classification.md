# Full catalog classification implementation plan

**Goal:** Classify every job in the starting published Turso snapshot, allow multiple job functions, enrich supported filter facts, exclude confirmed blue collar work, and report per-function counts.

**Design:** The existing version-bound `job_filter_intelligence` table remains the storage boundary. Add `roles`, `collar`, evidence and accepted numeric/header fields to its JSON. A shared taxonomy supplies the frontend and prompt. White collar jobs must have a suitable existing role or a specific added role. Failed/uncertain classifications remain visible until resolved. Source rows are preserved. Snapshot and model results allow resuming without paying twice.

**Constraints:** Use Mistral Nemo. Preserve the earlier $5 model budget by tracking actual provider cost and stopping before exceeding it. Multiple labels count a job in multiple rows. Existing source metadata takes precedence over inferred optional fields. Unsupported numerical output is hidden. Changes apply only to the matching posting version and content hash. Cleanup is limited to identified disposable session artifacts; preserve private configuration, reports, and unrelated work.

- [x] Share complete taxonomy and add missing white collar functions; verify frontend/model agreement.
- [x] Add multi-role matching and version-aware blue collar exclusion; test unfiltered, filtered and detail queries.
- [x] Implement resumable paginated snapshot, concurrent bounded Nemo extraction, evidence validation, budget ledger and rollback snapshot.
- [x] Process the full snapshot; resolve white collar classification gaps; count overlapping roles and rejected/absent fields.
- [x] Publish matching current versions, deploy and verify live query behavior and counts.
- [x] Commit production code and report; preserve unrelated changes, remove confirmed test artifacts, sync the primary checkout.

Ruling: User explicitly authorized implementation and production deployment; continue inline without repeating approval of the already specified rollout. Add specific missing functions as the user requested, while retaining accurate existing matches.

Ruling: Supply original language to this extraction round to verify exact evidence and avoid translation changing obligation strength. These calls classify and extract facts; they do not rewrite employer descriptions. The accepted metadata feeds the same header used by the existing description pilot.

Evidence: 29,217 employer postings pinned from production Turso. Small batches exposed unsupported enums/quotes; functions and metadata now use separate prompts, with exact enum/schema validation and source-backed field guards. Frontend: 168 tests pass and Vite build passes. Repository/validator: 12 focused tests pass. Fresh review identified contract/manager guards, persistent budget reservations and reporting/rollback gaps; fixes implemented before publication. Full model round completed: 29,494 current employer postings; 22,007 white collar, 7,485 blue collar and two unresolved source records. All 29,492 validated versions saved to Turso with no changed-version skips. Total budget ledger $2.53548. Final transport/rollback/validator/repository regression suite: 32 tests pass; live filter verification follows publication.

Final evidence: all 160 live function counts and memberships passed; 20 field/filter selections exercised. Source cache retains scraped precedence without large payload scans. 35 focused regression tests passed. Two insufficient source records remain visible and unresolved.
