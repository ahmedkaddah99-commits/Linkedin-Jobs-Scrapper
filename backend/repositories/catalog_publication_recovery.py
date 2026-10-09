"""Bounded, atomic publication of durable jobs left outside producer cycles."""
import json
import os
import time
from uuid import uuid4

from backend.acquisition.publication import StalePublicationHeadError, get_publication_policy
from backend.domain.models import utc_now_iso


def publish_pending(store, *, batch_size, policy_version):
    from backend.repositories.sqlite_acquisition import _publication_payload_sql, _insert_publication_jobs_batched

    started=time.monotonic()
    recording=False
    def trace(stage):
        if os.getenv('RUNR_PUBLICATION_RECOVERY_TRACE')=='1':
            print(json.dumps({'event':'publication_recovery_phase','phase':('record_'+stage if recording else stage),
                'elapsed_seconds':round(time.monotonic()-started,3)}),flush=True)
    trace('prepare_start')
    policy = get_publication_policy(policy_version)
    with store._connect() as conn:
        head_rows = store._fetch_read_rows(conn, 'SELECT publication_id,updated_at FROM acquisition_publication_head WHERE head_id=1')
        head = dict(head_rows[0]) if head_rows else {}
        if head:
            actual = store._fetch_read_rows(conn,'SELECT policy_version FROM acquisition_publications WHERE publication_id=?',(head['publication_id'],))[0]['policy_version']
            if actual != policy.version:
                raise ValueError('Recovery policy must match the current publication policy.')
        candidates = store._fetch_read_rows(conn, f"""
            SELECT q.revision AS queue_revision,q.version_id AS queue_version,j.*,
                   c.canonical_name AS company,COALESCE(v.description,'') AS version_description,
                   COALESCE(v.location,'') AS version_location,COALESCE(v.apply_url,'') AS apply_url,
                   {_publication_payload_sql()} AS version_payload_json,
                   o.external_job_id AS source_job_id,o.source_ats,
                   o.observed_at AS observation_observed_at,o.target_id AS source_target_id,
                   o.task_id AS source_task_id,
                   CASE WHEN a.canonical_job_id IS NULL THEN 0 ELSE 1 END AS already_published
            FROM acquisition_publication_queue q
            JOIN canonical_jobs j ON j.canonical_job_id=q.canonical_job_id
            JOIN canonical_companies c ON c.company_id=j.company_id
            LEFT JOIN job_posting_versions v ON v.version_id=j.current_version_id
            LEFT JOIN job_source_observations o ON o.observation_id=(
                SELECT latest.observation_id FROM job_source_observations latest
                WHERE latest.canonical_job_id=j.canonical_job_id
                ORDER BY latest.observed_at DESC,latest.observation_id DESC LIMIT 1)
            LEFT JOIN acquisition_publication_jobs a ON a.canonical_job_id=j.canonical_job_id AND a.publication_id=?
            WHERE q.status='pending' ORDER BY q.canonical_job_id LIMIT ?
        """, (head.get('publication_id',''),max(1,min(500,int(batch_size)))))
    trace('prepare_complete')
    if not candidates:
        return {'processed':0,'published':0,'rejected':0,'publication_id':head.get('publication_id','')}
    candidates = [dict(r) for r in candidates]
    active = [r for r in candidates if r['lifecycle_state']=='active' and not r['already_published']]
    snapshot, rejections = store._publication_rows_with_completeness(active,policy=policy)
    accepted = {r['canonical_job_id'] for r in snapshot}
    reasons = {r['canonical_job_id']:[reason['code'] for reason in r['reasons']] for r in rejections}
    now = utc_now_iso()
    trace('gate_complete')
    publication_id = head.get('publication_id') or 'acq_recovery_'+uuid4().hex

    def commit(conn):
        trace('transaction_start')
        conn.execute('BEGIN IMMEDIATE')
        trace('write_transaction_acquired')
        current = conn.execute('SELECT publication_id,updated_at FROM acquisition_publication_head WHERE head_id=1').fetchone()
        if (dict(current) if current else {}) != head:
            raise StalePublicationHeadError('Publication head changed during recovery preparation.')
        expected=[{'id':r['canonical_job_id'],'version':r['current_version_id'],
                   'state':r['lifecycle_state'],'revision':r['queue_revision']} for r in candidates]
        # Validate on the server and return one scalar. Remote cursor streaming
        # must not hold the write transaction open for every candidate row.
        matched=conn.execute("""SELECT COUNT(*) AS jobs FROM json_each(?) expected
            JOIN canonical_jobs j ON j.canonical_job_id=json_extract(expected.value,'$.id')
            JOIN acquisition_publication_queue q ON q.canonical_job_id=j.canonical_job_id
            WHERE j.current_version_id IS json_extract(expected.value,'$.version')
              AND j.lifecycle_state=json_extract(expected.value,'$.state')
              AND q.revision=json_extract(expected.value,'$.revision')""",(json.dumps(expected),)).fetchone()['jobs']
        if matched != len(candidates):
            raise StalePublicationHeadError('Job changed during recovery preparation; retry its queued revision.')
        trace('fences_checked')
        if snapshot:
            if not head:
                conn.execute("""INSERT INTO acquisition_publications(publication_id,cycle_id,status,snapshot_json,
                    published_at,valid_until,previous_publication_id,origin,created_by,scheduled_run_id,preflight_json,policy_version)
                    VALUES(?,?,'valid','[]',?,'','','system','catalog_recovery','','{}',?)""",
                    (publication_id,'recovery_'+uuid4().hex,now,policy.version))
                conn.execute('INSERT INTO acquisition_publication_head(head_id,publication_id,updated_at) VALUES(1,?,?)',(publication_id,now))
            _insert_publication_jobs_batched(conn,publication_id=publication_id,canonical_job_ids=sorted(accepted))
            trace('membership_written')
            # Append on the server. Do not download/re-upload the entire 36k-job
            # snapshot for each bounded batch. Old membership is preserved.
            conn.execute("""UPDATE acquisition_publications SET snapshot_json=(
                SELECT json_group_array(json(value)) FROM (
                    SELECT value FROM json_each(acquisition_publications.snapshot_json)
                    UNION ALL SELECT value FROM json_each(?))),published_at=?
                WHERE publication_id=?""",(json.dumps(snapshot,separators=(',',':')),now,publication_id))
            trace('snapshot_written')
            conn.execute('UPDATE acquisition_publication_head SET updated_at=? WHERE head_id=1 AND publication_id=?',(now,publication_id))
            conn.execute("""UPDATE acquisition_cycles SET jobs_published=(SELECT COUNT(*) FROM acquisition_publication_jobs WHERE publication_id=?),
                updated_at=? WHERE cycle_id=(SELECT cycle_id FROM acquisition_publications WHERE publication_id=?)""",(publication_id,now,publication_id))
            store._record_publication_audit(conn,publication_id=publication_id,event_type='publication_recovered',
                actor_user_id='catalog_recovery',previous_publication_id=head.get('publication_id',''),
                payload={'added':len(snapshot),'policy_version':policy.version},created_at=now)
            trace('head_and_audit_written')
        if rejections:
            trace('gate_records_start')
            store._persist_publication_rejections(conn,cycle_id='catalog_recovery',rejected_rows=rejections)
        trace('queue_acknowledgement')
        outcomes = []
        for r in candidates:
            key = r['canonical_job_id']
            status = 'published' if key in accepted or r['already_published'] else ('inactive' if r['lifecycle_state']!='active' else 'rejected')
            outcomes.append({'id':key,'revision':r['queue_revision'],'version':r['current_version_id'],
                             'status':status,'reasons':json.dumps(reasons.get(key,[]))})
        conn.execute("""WITH outcomes AS (SELECT value FROM json_each(?))
            UPDATE acquisition_publication_queue SET
              version_id=(SELECT json_extract(value,'$.version') FROM outcomes WHERE json_extract(value,'$.id')=canonical_job_id),
              status=(SELECT json_extract(value,'$.status') FROM outcomes WHERE json_extract(value,'$.id')=canonical_job_id),
              reason_codes_json=(SELECT json_extract(value,'$.reasons') FROM outcomes WHERE json_extract(value,'$.id')=canonical_job_id),
              policy_version=?,evaluated_at=?
            WHERE canonical_job_id IN (SELECT json_extract(value,'$.id') FROM outcomes)""",
            (json.dumps(outcomes),policy.version,now))
        return {'processed':len(candidates),'published':len(snapshot),'rejected':len(active)-len(snapshot),
                'publication_id':publication_id if head or snapshot else ''}

    if os.getenv('RUNR_PUBLICATION_RECOVERY_HTTP_BATCH')=='1':
        from backend.database.http_batch import execute_atomic_batch
        statements=[]
        expected=[{'id':r['canonical_job_id'],'version':r['current_version_id'],
                   'state':r['lifecycle_state'],'revision':r['queue_revision']} for r in candidates]
        guard="""UPDATE acquisition_publication_queue SET version_id=CASE WHEN
            COALESCE((SELECT publication_id FROM acquisition_publication_head WHERE head_id=1),'')=?
            AND COALESCE((SELECT updated_at FROM acquisition_publication_head WHERE head_id=1),'')=?
            AND (SELECT COUNT(*) FROM json_each(?) e JOIN canonical_jobs j
                ON j.canonical_job_id=json_extract(e.value,'$.id')
                JOIN acquisition_publication_queue q ON q.canonical_job_id=j.canonical_job_id
                WHERE j.current_version_id IS json_extract(e.value,'$.version')
                AND j.lifecycle_state=json_extract(e.value,'$.state')
                AND q.revision=json_extract(e.value,'$.revision'))=?
            THEN version_id ELSE NULL END WHERE canonical_job_id=?"""
        statements.append((guard,(head.get('publication_id',''),head.get('updated_at',''),
            json.dumps(expected),len(candidates),candidates[0]['canonical_job_id'])))
        class Result:
            def __init__(self,value):self.value=value
            def fetchone(self):return self.value
        class Recorder:
            def execute(self,sql,parameters=()):
                if sql=='BEGIN IMMEDIATE':return Result(None)
                if sql.startswith('SELECT publication_id,updated_at'):
                    return Result(head or None)
                if sql.startswith('SELECT COUNT(*) AS jobs FROM json_each'):
                    return Result({'jobs':len(candidates)})
                statements.append((sql,parameters))
                return Result(None)
        recording=True
        outcome=commit(Recorder())
        recording=False
        trace('http_atomic_write_start')
        execute_atomic_batch(statements)
        trace('http_atomic_write_committed')
        return outcome
    return store._run_transaction(commit)
