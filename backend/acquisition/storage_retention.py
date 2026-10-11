"""Bounded catalog retention. Current catalog and immutable evidence stay intact.

Membership deletion is restartable: the obsolete header remains until its last
membership has gone. Pins are recomputed in every write transaction. No VACUUM
is performed here. Source pruning restores its exact DELETE guard before commit.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import time
import json
import os

from backend.database.connection import connect_database
from backend.acquisition.storage_evidence import restore_catalog_evidence, CatalogEvidenceError
from backend.storage.base import ObjectStorageError

_TERMINAL = "('completed','degraded','failed','blocked','cancelled','skipped')"
_SUCCESS = "('valid')"
_PINS = f"""
    SELECT publication_id FROM acquisition_publication_head
    UNION SELECT p.previous_publication_id FROM acquisition_publications p
      JOIN acquisition_publication_head h ON h.publication_id=p.publication_id
    UNION SELECT last_publication_id FROM acquisition_publisher_checkpoints
    UNION SELECT publication_id FROM acquisition_cycles WHERE status NOT IN {_TERMINAL}
    UNION SELECT p.publication_id FROM acquisition_publications p
      JOIN acquisition_cycles c ON c.cycle_id=p.cycle_id WHERE c.status NOT IN {_TERMINAL}
    UNION SELECT publication_id FROM (
      SELECT publication_id FROM acquisition_publications WHERE status IN {_SUCCESS}
      ORDER BY published_at DESC, publication_id DESC LIMIT 3)
"""
_CANDIDATE = f"""SELECT publication_id FROM acquisition_publications
    WHERE status='valid' AND publication_id NOT IN ({_PINS})
    ORDER BY published_at, publication_id LIMIT 1"""
_REJECTIONS = f"""SELECT rowid, length(CAST(detail_json AS BLOB)) AS logical_bytes
    FROM acquisition_job_rejections r WHERE observed_at < ?
    AND NOT EXISTS(SELECT 1 FROM acquisition_cycles c WHERE c.cycle_id=r.cycle_id
                   AND c.status NOT IN {_TERMINAL})
    ORDER BY observed_at, rowid LIMIT ?"""


_SOURCE_REFS = (
    ('job_posting_versions','source_observation_id'),
    ('acquisition_field_provenance','source_observation_id'),
    ('acquisition_rule_outputs','source_observation_id'),
    ('job_source_observation_relationships','observation_id'),
    ('job_source_observation_relationships','related_observation_id'),
    ('job_applicant_snapshots','source_observation_id'),
    ('canonical_company_urls','source_observation_id'),
    ('company_identity_evidence','source_observation_id'),
    ('company_link_candidates','source_observation_id'),
    ('canonical_company_url_occurrences','source_observation_id'),
    ('acquisition_ingest_staging','observation_id'),
)
_SOURCE_SAFE = f"""observed_at < ?
    AND EXISTS(SELECT 1 FROM job_source_observations newer
      WHERE newer.canonical_job_id=o.canonical_job_id AND newer.target_id=o.target_id
      AND (newer.observed_at > o.observed_at OR
           (newer.observed_at=o.observed_at AND newer.observation_id>o.observation_id)))
    AND NOT EXISTS(SELECT 1 FROM acquisition_cycles c WHERE c.cycle_id=o.cycle_id
      AND (c.status NOT IN {_TERMINAL} OR c.publication_id IN ({_PINS})))
    AND NOT EXISTS(SELECT 1 FROM acquisition_publications p WHERE p.cycle_id=o.cycle_id
      AND p.publication_id IN ({_PINS}))
""" + ''.join(f' AND NOT EXISTS(SELECT 1 FROM {table} ref WHERE ref.{column}=o.observation_id)' for table,column in _SOURCE_REFS)
# Failed/incomplete replay runs are resumable; preserve their source inputs.
_REPLAY_ACTIVE = "SELECT 1 FROM acquisition_reprocessing_runs WHERE status NOT IN ('completed','cancelled') LIMIT 1"


def _source_window(db, batch_size, cutoff):
    checkpoint = db.execute("SELECT last_rowid FROM runr_catalog_storage_maintenance WHERE name='source_observations'").fetchone()
    cursor = int(checkpoint[0]) if checkpoint else 0
    window = db.execute('SELECT rowid FROM job_source_observations WHERE rowid>? ORDER BY rowid LIMIT ?', (cursor,batch_size)).fetchall()
    if not window:
        return [], [], 0
    marks = ','.join('?' for _ in window)
    rows = db.execute(f'SELECT rowid,payload_json FROM job_source_observations o WHERE rowid IN ({marks}) AND {_SOURCE_SAFE} AND CASE WHEN json_valid(payload_json) THEN json_extract(payload_json,\'$.catalog_storage_version\')=1 ELSE 0 END ORDER BY rowid', (*[row[0] for row in window],cutoff)).fetchall()
    return window, rows, max(row[0] for row in window)


def _current_field_states(db, job_ids):
    """Read only field states for <=50 indexed current-version jobs per query."""
    states, queries = {}, 0
    for start in range(0, len(job_ids), 50):
        chunk = job_ids[start:start+50]
        marks = ','.join('?' for _ in chunk)
        sql = f"""SELECT j.canonical_job_id,
            (SELECT json_group_object(field.key,json_extract(field.value,'$.state'))
             FROM json_each(CASE WHEN json_valid(v.payload_json) THEN
                 coalesce(json_extract(v.payload_json,'$.unified_mapping.fields'),
                          json_extract(v.payload_json,'$.normalized_mapping.fields'),'{{}}')
                 ELSE '{{}}' END) field WHERE field.type='object') AS states_json
            FROM canonical_jobs j JOIN job_posting_versions v ON v.version_id=j.current_version_id
            WHERE j.canonical_job_id IN ({marks})"""
        for row in db.execute(sql,tuple(chunk)).fetchall():
            decoded = json.loads(row[1] or '{}')
            states[row[0]] = decoded if isinstance(decoded,dict) else {}
        queries += 1
    return states, queries


def _pages(connection):
    result = {}
    for key in ('page_count', 'freelist_count', 'page_size'):
        try:
            row = connection.execute(f'PRAGMA {key}').fetchone()
            result[key] = int(row[0]) if row else None
        except Exception:
            result[key] = None
    return result


def maintain_catalog_storage(db_path: Path, *, apply: bool = False,
                             batch_size: int = 1000, max_seconds: float = 30,
                             max_batches: int = 100, now: datetime | None = None,
                             evidence_storage=None) -> dict:
    """Perform at most max_batches transactions, each deleting <= batch_size rows.

    Seconds limits when another bounded transaction may start, not server query
    latency. Dry-run inspects only one bounded window of each category.
    """
    if batch_size < 1 or batch_size > 10000 or max_seconds <= 0 or max_batches < 1:
        raise ValueError('batch_size must be 1..10000; seconds and max_batches must be positive')
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('now must include a timezone')
    stamp = now.astimezone(timezone.utc).isoformat()
    cutoff = (now.astimezone(timezone.utc) - timedelta(days=7)).isoformat()
    source_cutoff = (now.astimezone(timezone.utc) - timedelta(days=14)).isoformat()
    deadline = time.monotonic() + max_seconds
    receipt = dict(apply=apply, deleted_memberships=0, deleted_publications=0,
                   deleted_rejections=0, deleted_empty_provenance=0, deleted_source_observations=0, logical_bytes_removed=0, batches=0,
                   retained_successful_snapshots=3, rejection_history_days=7, source_observation_history_days=14,
                   physical_reclamation='separate supported maintenance operation; VACUUM not run by retention',
                   deferred=['field provenance/current state', 'posting versions and referenced source observations',
                             'user saved/applied jobs', 'paid intelligence'],
                   capacity_warning_threshold_bytes=8_000_000_000,
                   deployment_capacity_bytes=9_000_000_000)
    with connect_database(Path(db_path)) as connection:
        receipt['before'] = _pages(connection)
        blockers = connection.execute("SELECT status, COUNT(*) FROM acquisition_reprocessing_runs WHERE status NOT IN ('completed','cancelled') GROUP BY status").fetchall()
        receipt['phase_backlog'] = {'source_observations': {
            'status': 'blocked' if blockers else 'eligible',
            'replay_blockers': [{'status': row[0], 'count': row[1]} for row in blockers],
        }}
        if not apply:
            publication = connection.execute(_CANDIDATE).fetchone()
            members = [] if not publication else connection.execute(
                'SELECT rowid FROM acquisition_publication_jobs WHERE publication_id=? LIMIT ?',
                (publication[0], batch_size)).fetchall()
            rejected = connection.execute(_REJECTIONS, (cutoff, batch_size)).fetchall()
            provenance = connection.execute('SELECT rowid FROM acquisition_field_provenance ORDER BY rowid LIMIT ?', (batch_size,)).fetchall()
            receipt['candidate_window'] = dict(publication_id=publication[0] if publication else None,
                                              memberships=len(members), rejections=len(rejected),
                                              provenance_rows_to_inspect=len(provenance))
            if connection.execute(_REPLAY_ACTIVE).fetchone():
                receipt['candidate_window']['source_phase_skipped'] = 'nonterminal replay'
            else:
                source_window, source_rows, _ = _source_window(connection,batch_size,source_cutoff)
                receipt['candidate_window'].update(source_rows_to_inspect=len(source_window), archived_source_candidates=len(source_rows))
            receipt['after'] = receipt['before']
            return receipt

        def batch(db, phase, prepared=None):
            # BEGIN IMMEDIATE prevents a publisher from changing the pins between
            # their read and deletion on SQLite. libSQL also uses a write transaction.
            db.execute('BEGIN IMMEDIATE')
            changed = dict(deleted_memberships=0, deleted_publications=0,
                           deleted_rejections=0, deleted_empty_provenance=0, deleted_source_observations=0, logical_bytes_removed=0, scanned_provenance=0, scanned_sources=0, source_verification_failures=0)
            last_rowid = 0
            if phase == 'publications':
                candidate = db.execute(_CANDIDATE).fetchone()
                if candidate:
                    publication_id = candidate[0]
                    rows = db.execute('SELECT rowid, length(CAST(canonical_job_id AS BLOB)) + length(CAST(publication_id AS BLOB)) FROM acquisition_publication_jobs WHERE publication_id=? LIMIT ?', (publication_id, batch_size)).fetchall()
                    if rows:
                        marks = ','.join('?' for _ in rows)
                        db.execute(f'DELETE FROM acquisition_publication_jobs WHERE rowid IN ({marks})', tuple(row[0] for row in rows))
                        changed['deleted_memberships'] = len(rows)
                        changed['logical_bytes_removed'] = sum(row[1] for row in rows)
                        last_rowid = max(row[0] for row in rows)
                    else:
                        row = db.execute('SELECT rowid,length(CAST(snapshot_json AS BLOB)) FROM acquisition_publications WHERE publication_id=?', (publication_id,)).fetchone()
                        db.execute('DELETE FROM acquisition_publications WHERE publication_id=?', (publication_id,))
                        changed['deleted_publications'] = 1
                        changed['logical_bytes_removed'] = row[1]
                        last_rowid = row[0]
            elif phase == 'source_observations':
                if db.execute(_REPLAY_ACTIVE).fetchone():
                    return changed
                window, verified, last_rowid, failures = prepared
                changed['scanned_sources'] = len(window)
                changed['source_verification_failures'] = failures
                eligible = []
                if verified:
                    marks = ','.join('?' for _ in verified)
                    current_rows = db.execute(f'SELECT rowid,payload_json FROM job_source_observations o WHERE rowid IN ({marks}) AND {_SOURCE_SAFE}', (*[row[0] for row in verified],source_cutoff)).fetchall()
                    expected = {row[0]: row[1] for row in verified}
                    eligible = [row for row in current_rows if expected.get(row[0]) == row[1]]
                if eligible:
                    trigger = db.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name='trg_job_source_observations_immutable_delete' AND tbl_name='job_source_observations'").fetchone()
                    if trigger is None or not trigger[0]:
                        raise RuntimeError('Source observation DELETE guard is missing')
                    # Transactional DDL: another connection never sees the guard
                    # absent; rollback restores it if delete or recreation fails.
                    db.execute('DROP TRIGGER trg_job_source_observations_immutable_delete')
                    marks = ','.join('?' for _ in eligible)
                    db.execute(f'DELETE FROM job_source_observations WHERE rowid IN ({marks})', tuple(row[0] for row in eligible))
                    db.execute(trigger[0])
                    restored = db.execute("SELECT sql FROM sqlite_master WHERE name='trg_job_source_observations_immutable_delete'").fetchone()
                    if restored is None or restored[0] != trigger[0]:
                        raise RuntimeError('Source observation DELETE guard did not restore exactly')
                    changed['deleted_source_observations'] = len(eligible)
                    changed['logical_bytes_removed'] = sum(len(row[1].encode('utf-8')) for row in eligible)
            elif phase == 'empty_provenance':
                checkpoint = db.execute("SELECT last_rowid FROM runr_catalog_storage_maintenance WHERE name='empty_provenance'").fetchone()
                cursor = int(checkpoint[0]) if checkpoint else 0
                rows = db.execute("SELECT rowid, provenance_id, entity_kind, entity_id, field_name, state, raw_value_json, normalized_value_json, evidence_json FROM acquisition_field_provenance WHERE rowid>? ORDER BY rowid LIMIT ?", (cursor,batch_size)).fetchall()
                changed['scanned_provenance'] = len(rows)
                empty = (None, '', 'null', '{}', '[]', '\"\"')
                candidates = [row for row in rows
                    if row[2] == 'job' and row[5] in ('missing','unknown')
                    and all(value is None or value.strip() in empty
                            for value in (row[6],row[7],row[8]))]
                job_ids = sorted({row[3] for row in candidates})
                states, queries = _current_field_states(db,job_ids)
                changed['current_state_projection_queries'] = queries
                eligible = [row for row in candidates if states.get(row[3],{}).get(row[4]) == row[5]]
                if rows:
                    last_rowid = int(rows[-1][0])
                if eligible:
                    marks = ','.join('?' for _ in eligible)
                    db.execute(f'DELETE FROM acquisition_field_provenance WHERE rowid IN ({marks})', tuple(row[0] for row in eligible))
                    changed['deleted_empty_provenance'] = len(eligible)
                    changed['logical_bytes_removed'] = sum(sum(len(value.encode('utf-8')) for value in (row[6], row[7], row[8]) if value) for row in eligible)
                if not rows:
                    # Reset after a complete pass: SQLite can reuse deleted high
                    # rowids, and old retained rows may gain a safe projection.
                    last_rowid = 0
            else:
                rows = db.execute(_REJECTIONS, (cutoff, batch_size)).fetchall()
                if rows:
                    marks = ','.join('?' for _ in rows)
                    db.execute(f'DELETE FROM acquisition_job_rejections WHERE rowid IN ({marks})', tuple(row[0] for row in rows))
                    changed['deleted_rejections'] = len(rows)
                    changed['logical_bytes_removed'] = sum(row[1] for row in rows)
                    last_rowid = max(row[0] for row in rows)
            db.execute('INSERT INTO runr_catalog_storage_maintenance(name,last_rowid,last_run_at,last_error) VALUES(?,?,?,?) ON CONFLICT(name) DO UPDATE SET last_rowid=excluded.last_rowid,last_run_at=excluded.last_run_at,last_error=excluded.last_error', (phase,last_rowid,stamp,''))
            return changed

        # Alternate categories so a large obsolete publication cannot starve
        # rejection/provenance cleanup. Incomplete headers are the durable publication cursor.
        finished = set()
        for number in range(max_batches):
            if time.monotonic() >= deadline or len(finished) == 4:
                break
            phase = ('publications', 'rejections', 'empty_provenance', 'source_observations')[number % 4]
            if phase in finished:
                phase = next(item for item in ('publications','rejections','empty_provenance','source_observations') if item not in finished)
            prepared = None
            if phase == 'source_observations':
                if evidence_storage is None and os.getenv('OBJECT_STORAGE_BACKEND') not in ('s3','r2'):
                    receipt['source_phase_skipped'] = 'shared S3/R2 evidence storage not configured'
                    finished.add(phase)
                    continue
                if connection.execute(_REPLAY_ACTIVE).fetchone():
                    receipt['source_phase_skipped'] = 'nonterminal replay'
                    finished.add(phase)
                    continue
                window, candidates, watermark = _source_window(connection,batch_size,source_cutoff)
                verified, failures = [], 0
                # Object reads happen before the write transaction. Recheck all
                # SQL references and exact payload equality under the write lock.
                for row in candidates:
                    if time.monotonic() >= deadline:
                        # Resume at the first unverified eligible row; do not
                        # advance a cursor past evidence work skipped by budget.
                        receipt['source_budget_deferred'] = len(candidates) - len(verified) - failures
                        watermark = row[0] - 1
                        window = [item for item in window if item[0] <= watermark]
                        break
                    try:
                        reference = json.loads(row[1])
                        restore_catalog_evidence(reference, evidence_storage)
                    except (CatalogEvidenceError, ObjectStorageError):
                        failures += 1
                        continue
                    verified.append(row)
                prepared = (window,verified,watermark,failures)
            try:
                changed = connection.transaction(lambda db: batch(db, phase, prepared))
            except Exception as error:
                # The deletion/checkpoint transaction was rolled back. Store only
                # the exception class; remote errors can contain connection data.
                def record_error(db):
                    db.execute('INSERT INTO runr_catalog_storage_maintenance(name,last_rowid,last_run_at,last_error) VALUES(?,0,?,?) ON CONFLICT(name) DO UPDATE SET last_run_at=excluded.last_run_at,last_error=excluded.last_error', (phase,stamp,type(error).__name__))
                connection.transaction(record_error)
                raise
            receipt['batches'] += 1
            for key, value in changed.items():
                receipt[key] = receipt.get(key, 0) + value
            if not any(changed[key] for key in ('deleted_memberships','deleted_publications','deleted_rejections','scanned_provenance','scanned_sources')):
                finished.add(phase)
        receipt['complete'] = len(finished) == 4 and not receipt.get('source_budget_deferred') and not receipt.get('source_phase_skipped')
        receipt['after'] = _pages(connection)
        if receipt['after'].get('page_count') is not None and receipt['after'].get('page_size') is not None:
            receipt['allocated_bytes'] = receipt['after']['page_count'] * receipt['after']['page_size']
            receipt['capacity_warning'] = receipt['allocated_bytes'] > receipt['capacity_warning_threshold_bytes']
            receipt['capacity_critical'] = receipt['allocated_bytes'] > receipt['deployment_capacity_bytes']
        receipt['logical_bytes_note'] = 'bounded removed payload and membership bytes; excludes indexes and other columns'
    return receipt
