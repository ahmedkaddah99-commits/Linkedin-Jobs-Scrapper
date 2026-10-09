# Catalog storage reduction implementation

The owner approved the measured `data/audit/job_storage_2026-10-08/REDUCTION_PLAN.md`
and explicitly requested implementation, commit, sync and deployment. Execute in
an isolated worktree, preserving unrelated local files. Python is 3.12.7.

1. Test and implement the compact storage projection; preserve public field
   values/states and conflicting source evidence. Strip only proven duplicates.
2. Test and implement compressed content-addressed source evidence storage and
   explicit reprocessing hydration. Verify archive durability before SQL removal.
3. Integrate bulk/legacy durable writers, prevent compact rows from triggering
   false repair versions, skip empty per-field records, and update current
   rejection state across cycles instead of copying it indefinitely.
4. Append migration 075 for retention checkpoints/indexes and removal of retired
   FTS structures. Preserve all existing migration checksums.
5. Implement bounded resumable hourly retention, pin head/rollback/checkpoint and
   in-progress recovery publications, cap successful snapshot history, and
   remove obsolete rejection/no-evidence history without deleting user data.
6. Implement historical backfill with verified cold archives, optimistic
   storage-only updates and exact immutability-trigger restoration in each
   transaction. Keep a database-bound checkpoint and verify ambiguous retries.
7. Validate current paid derived outputs and source/version/publication links;
   compact redundant rule/quality audit representations without provider calls.
8. Run focused and full verification, request independent review, resolve
   important findings, document operating policies and commit the exact changes.
9. Push the verified release to the authorized deployment branch. Verify Render
   API/worker live commits and health. Install the exact committed archive in an
   isolated VPS release; verify hashes, entrypoints, timer and Python identity.
10. Run bounded historical cleanup under serialized acquisition maintenance;
    preserve recoverability and required immutability guards. Resolve prior
    write stalls rather than assuming a bigger timeout fixes them.
11. Reclaim physical database pages through a verified supported mechanism or
    a compact replacement database with a coordinated API/worker/VPS cutover.
    Keep an explicit bounded rollback window and account for its storage.
12. Observe real collection/publication and maintenance cycles, record actual
    allocated bytes and growth, and report unresolved provider restrictions
    without claiming they were fixed.

Acceptance: materially lower actual Turso storage, compact new writes, bounded
history across cycles, successful resumable retention, preserved customer data
and paid outputs, no cold downloads/cleanup writes in ordinary GETs, and matching
deployed code/database identities. The 8–12 GB figure is an engineering target,
not a completion claim until measured.
