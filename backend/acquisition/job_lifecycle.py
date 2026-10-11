"""Shared rolling job age policy. Re-observation never resets first-seen age."""
from datetime import datetime, timedelta, timezone
from typing import Mapping, Any


def exclusion_reason(record: Mapping[str, Any], *, now: datetime | None = None) -> str:
    # Local import keeps this helper usable by the completeness gate itself.
    from backend.acquisition.job_publication_completeness import _posted_at, _parse_iso
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError('now must include a timezone')
    cutoff = current - timedelta(days=30)
    posted = _parse_iso(_posted_at(record))
    first_seen = _parse_iso(str(record.get('first_seen_at') or record.get('created_at') or ''))
    if posted is not None and posted < cutoff:
        return 'posted_over_30_days'
    if first_seen is not None and first_seen < cutoff:
        return 'first_seen_over_30_days'
    return ''


def maintain_job_lifecycle(db_path, *, apply=False, batch_size=100, max_batches=20,
                           max_seconds=30, now=None):
    """Expire a bounded restartable window; customer history and evidence survive.

    Canonical identity is deliberately retained. Physical reclamation belongs to
    evidence storage retention, not this discovery availability operation.
    """
    import json
    import time
    from backend.database.connection import connect_database
    if not 1 <= batch_size <= 1000 or max_batches < 1 or max_seconds <= 0:
        raise ValueError('invalid lifecycle maintenance bounds')
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError('now must include a timezone')
    stamp = current.astimezone(timezone.utc).isoformat()
    deadline = time.monotonic() + max_seconds
    receipt = dict(apply=apply, retention_days=30, scanned_jobs=0, expired_jobs=0,
                   candidate_jobs=0, batches=0, pass_complete=False,
                   retained='Canonical identities, customer history, versions and source evidence',
                   physical_rows_deleted=0)
    with connect_database(db_path) as db:
        # Reuse the existing storage-maintenance progress table.
        cursor_row = db.execute("SELECT last_rowid FROM runr_catalog_storage_maintenance WHERE name='job_lifecycle'").fetchone()
        cursor = int(cursor_row[0]) if cursor_row else 0
        for _ in range(max_batches):
            if time.monotonic() >= deadline:
                break
            if apply:
                db.execute('BEGIN IMMEDIATE')
            try:
                rows = db.execute('''SELECT j.rowid, j.canonical_job_id, j.first_seen_at,
                    j.created_at, v.payload_json,j.title,f.filters_json FROM canonical_jobs j
                    LEFT JOIN job_posting_versions v ON v.version_id=j.current_version_id
                    LEFT JOIN job_filter_intelligence f ON f.version_id=v.version_id AND f.content_hash=v.content_hash
                    WHERE j.rowid>? ORDER BY j.rowid LIMIT ?''', (cursor,batch_size)).fetchall()
                selected = []
                for row in rows:
                    try:
                        record = json.loads(row[4] or '{}')
                    except (ValueError, TypeError):
                        record = {}
                    if not isinstance(record, dict):
                        record = {}
                    record.update(first_seen_at=row[2], created_at=row[3])
                    from backend.application.catalog_job_filters import profession_override
                    try:
                        filters = json.loads(row[6] or '{}')
                    except (ValueError, TypeError):
                        filters = {}
                    blue = (isinstance(filters, dict) and filters.get('collar') == 'blue') or profession_override(row[5], '') == ('blue', [])
                    if exclusion_reason(record, now=current) or blue:
                        selected.append(row[1])
                receipt['scanned_jobs'] += len(rows)
                receipt['candidate_jobs'] += len(selected)
                cursor = int(rows[-1][0]) if rows else 0
                if apply:
                    if selected:
                        encoded = json.dumps(selected)
                        clause = 'canonical_job_id IN (SELECT value FROM json_each(?))'
                        db.execute("UPDATE canonical_jobs SET lifecycle_state='expired', closed_at=?, updated_at=? WHERE " + clause + " AND lifecycle_state<>'expired'", (stamp,stamp,encoded))
                        db.execute('DELETE FROM acquisition_publication_jobs WHERE publication_id IN (SELECT publication_id FROM acquisition_publication_head) AND '+clause, (encoded,))
                        db.execute('''UPDATE acquisition_publications SET snapshot_json=COALESCE(
                            (SELECT json_group_array(json(value)) FROM json_each(snapshot_json)
                            WHERE json_extract(value,'$.canonical_job_id') NOT IN (SELECT value FROM json_each(?))), '[]')
                            WHERE publication_id IN (SELECT publication_id FROM acquisition_publication_head)''', (encoded,))
                        db.execute('DELETE FROM acquisition_publication_queue WHERE '+clause, (encoded,))
                        db.execute("UPDATE job_enrichment_queue SET state='superseded',error_code='lifecycle_excluded',lease_token='',lease_expires_at='' WHERE "+clause, (encoded,))
                        db.execute('UPDATE acquisition_publication_head SET updated_at=? WHERE head_id=1', (stamp,))
                        receipt['expired_jobs'] += len(selected)
                    db.execute("INSERT INTO runr_catalog_storage_maintenance(name,last_rowid,last_run_at,last_error) VALUES('job_lifecycle',?,?, '') ON CONFLICT(name) DO UPDATE SET last_rowid=excluded.last_rowid,last_run_at=excluded.last_run_at,last_error=''", (cursor,stamp))
                    db.commit()
                receipt['batches'] += 1
                if not rows:
                    receipt['pass_complete'] = True
                    break
            except Exception:
                if apply:
                    db.rollback()
                raise
    return receipt
