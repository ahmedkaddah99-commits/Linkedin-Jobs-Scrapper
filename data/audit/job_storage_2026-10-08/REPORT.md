# Scraped job storage audit — 2026-10-08

Initial read-only inspection of the configured Turso catalog and the live VPS.
Python 3.12.7 verified. Implementation and operating results follow below.
Reproduce the catalog sample with `.venv\Scripts\python.exe scripts/audit_job_storage.py`.

## Measured catalog payloads

| Table | Total rows | Latest sample | Payload bytes | Separate raw/description bytes |
|---|---:|---:|---:|---:|
| job_source_observations | 92,823 | 100 | 10,336,000 | raw: 4,080,997 |
| job_posting_versions | 55,627 | 100 | 10,345,571 | description: 230,752 |

These are samples, not a measurement of total database size. Rows may change
while the publisher runs. Sizes use SQLite UTF-8 BLOB lengths.

Observation sample's largest embedded fields:

| Field | Bytes across 100 rows | Finding |
|---|---:|---|
| source_raw_payload | 3,498,678 | Duplicates source input already saved separately; adapter additionally nests a complete observation contract containing source_record and normalized_mapping. |
| unified_mapping | 3,076,819 | Used by public field projection and acquisition; do not delete wholesale. Contains repeated description representations. |
| field_provenance | 1,427,250 | Assigned from unified_mapping.fields; duplicate where that mapping is present. Public projection already reads mapping.fields first. |
| normalized_source_metadata | 483,742 | Used by normalization and publication; preserve required fields. |
| content_fingerprint | 280,296 | Full stable-content object; no backend consumer found beyond exclusion from customer reads. Keep hashes and stop persisting this redundant object. |
| description / description_text / description_raw / description_html | 229,684 each | Equal byte sizes in sample, but some source descriptions differ by representation. Preserve canonical text and any nonidentical representation required by current processing. |

`producer_adapters._observation_to_ingest_job` adds `producer_record` and the
full `observation.to_dict()` to source_raw_payload. Runtime code does not read
the producer_record/observation_contract wrappers; tests assert historical
retention. The full contract remains necessary at the in-memory transport
boundary, but does not require another full persisted copy.

`quality.normalize_job_for_ingestion` copies the original job into
source_raw_payload, duplicates mapping.fields as field_provenance, and embeds
the stable-content object as content_fingerprint. The repository persists
the normalized job in observations and versions and the input again in
raw_payload_json. Mapping/provenance also have dedicated durable tables.

## Fields that must not be removed indiscriminately

- Raw ATS fields supply application URL, company attributes, salary, categories,
  employment/workplace metadata, and historical reprocessing inputs.
- generic_jsonld stores entire page HTML in source_raw_payload.html. Quality
  normalization reads HTML to recover application destinations, so extraction
  must run before removing it from persisted storage.
- Original descriptions still feed description intelligence, shared profile
  facts, and tailored documents even though the current customer job screen
  does not display the original description.
- IDs, URLs, ownership evidence, timestamps, source hashes, lifecycle state,
  publication checkpoints and resumable queues support current application
  behavior and collection correctness.

## Recommended implementation

1. Keep extraction inputs in memory through normalization; compact at durable
   write boundaries. Remove redundant producer/observation wrappers, the
   fingerprint object, and field_provenance when unified_mapping.fields exists.
2. Keep one required source record for reprocessing, without nested copies of
   itself. Preserve unique ATS fields until mapped or proven unused.
3. Stop persisting whole page HTML after application destination extraction;
   retain normalized destinations and necessary evidence fields.
4. Backfill existing records in bounded, resumable batches with concurrency
   guards. Preserve row IDs, job/version/hash relationships and catalog head.
5. Test ingestion, application URL fallback, publication, reprocessing,
   description intelligence, profile facts and job details before syncing.
6. Deploy Render API/worker and relevant isolated VPS acquisition releases.
   Preserve enabled collector/publisher/backup timers and verify live writes
   use the compact storage shape.

Removing just the redundant fingerprint and provenance accounts for about
16.5% of the observation payload sample. Removing redundant raw copies from
normalized payloads could save substantially more, but unique raw fields
must first be retained in the source record or normalized projection. These
are payload estimates; physical database reclamation is a separate operation.

## Live deployment facts

Render API/worker latest live revision: 60097a9838c4e3d52f119127b6cb23025e52d0da.
VPS sources execute isolated release directories rather than the shared
`/opt/runr` tree. The active producer state generation is
`/srv/runr/state/versions/t42-restored-20260923`: LinkedIn DB approximately
6.7 GiB, employer DB approximately 530 MiB. These include indexes, free pages
and operational history; no claim is made that all of that size is removable.
The older `/srv/runr/state/linkedin` DB is not the active generation.
Live collector/publisher timers were enabled and active during inspection.

## Implementation and verified results

Owner approved implementation, commit, sync and deployment in the follow-up.
Commit `b756fb554d5f77c459961ead99b01d439f4e65bf` was pushed to
`deployment/render-turso-r2`; Render API and worker both became live on that
commit and API `/health/live` returned HTTP 200. The same exact committed
archive was installed in an isolated VPS release directory. Archive SHA-256:
`ab77e7f061e4d8b891b89aa116362c420975b32673e16dc3acf1f852363ece23`.
All three source/publisher entrypoints were updated; LinkedIn, employer,
publisher and off-host backup timers remained enabled and active. Rollback
unit definitions were retained under `/srv/runr/backups/storage-release-<sha>`.

Compaction covers staged ingestion, observations, versions, employer producer
annotation and successful LinkedIn attempts. No descriptions, unique source
values, source IDs, job/version identities or content hashes are removed.
Duplicate provenance no longer triggers a new repair version. Nested whole-page
HTML is removed from retained source envelopes after destination extraction.

Focused validation: **289 passed** across storage, ingestion, publication,
producer delivery/bulk processing, employer/LinkedIn collection, source evidence,
job filters and profile matching. The older RC010 end-to-end test has an existing
total-count assertion failure reproduced on the original repository code before
these changes; it is not reported as passing.

### Producer cleanup completed

| Measurement | Bytes / rows |
|---|---:|
| Successful LinkedIn attempts inspected | 385,726 |
| Detail JSON before | 1,472,892,867 bytes |
| Detail JSON after | 14,657,588 bytes |
| Duplicate payload bytes removed | **1,458,235,279 bytes** |

The systemd maintenance unit exited successfully. It first created an intact
SQLite backup beside the active producer state, with suffix
`.before-storage-cleanup.db`. This measures logical payload removal: the SQLite
file has not been vacuumed and the backup remains for rollback. Freed pages can
be reused by future writes.

The first LinkedIn run using the new isolated release exited zero. An employer
run again reached the existing 900-second timeout (exit 124); complete employer
scan coverage is not claimed. The publisher entered the new release but real
post-release compact catalog writes have not yet been established.

### Historical catalog cleanup is blocked, not complete

Turso's immutable-history guards rejected the first unprivileged update. The
maintenance command now has a tested storage-only operator path: metadata guard
setup occurs separately, and a bounded DML transaction authorizes only its table
and row interval. Every non-payload column and rowid remains protected; the flag
is deleted before commit. HTTP steps commit only after all previous statements
succeed and roll back on failures. Original guard SQL is retained in the
database-bound checkpoint and restored on exit.

Actual existing-row changes repeatedly timed out at 60 and 180 seconds,
including a single 17,318-byte observation. A scoped-flag alternative also timed
out. Metadata restoration subsequently completed: both original immutability
guards were verified, and the temporary maintenance table was verified absent.
No permanent bypass or authorization flag remains. The checkpoint reached only
rowid 300 with zero measured catalog savings. The latest 100 catalog rows still
contain the historical fingerprint/provenance copies. Therefore this report
does **not** claim that existing catalog cleanup is finished or that all future
live publications have been verified compact.

The VPS and local database bindings were verified equal by SHA-256 identity
`387ee209fb0cf5623d04a2864becf791865b81c52b5dcdbcfb8aefad73eca98a`.
Only the database URL/auth token are configured; Turso account/admin diagnostics
are unavailable. Browser dashboard access was rejected because the
admin-enforced browser policy could not be verified. Admin visibility is needed
to diagnose the outstanding write stalls; no browser security workaround was
attempted.
