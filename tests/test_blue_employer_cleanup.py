import json
import sqlite3

import pytest

from scripts.cleanup_blue_employer_catalog import application_reference_guard


@pytest.mark.parametrize('reference_kind',['canonical','external','url','nested_payload'])
def test_new_application_reference_aborts_purge_transaction(reference_kind):
    c=sqlite3.connect(':memory:')
    for table in ('reviews','application_packages','run_jobs','generation_provenance'):
        c.execute(f'CREATE TABLE {table}(job_id TEXT,payload_json TEXT)')
    for table in ('run_job_sets','run_blobs'):
        c.execute(f'CREATE TABLE {table}(payload_json TEXT)')
    for table in ('personalized_job_dispositions','personalized_job_events','personalized_job_evaluations','job_intelligence_cache'):
        c.execute(f'CREATE TABLE {table}(canonical_job_id TEXT)')
    c.execute('CREATE TABLE employer_acquisition_exclusions(company_id TEXT,reason TEXT NOT NULL)')
    c.execute("INSERT INTO employer_acquisition_exclusions VALUES ('company','policy')")
    c.execute('CREATE TABLE canonical_jobs(canonical_job_id TEXT,canonical_url TEXT)')
    c.execute("INSERT INTO canonical_jobs VALUES ('job','https://employer/job')")
    c.execute('CREATE TABLE canonical_job_external_ids(canonical_job_id TEXT,external_job_id TEXT)')
    c.execute("INSERT INTO canonical_job_external_ids VALUES ('job','12345')")
    c.execute('CREATE TABLE canonical_job_url_aliases(canonical_job_id TEXT,url TEXT)')
    c.execute("INSERT INTO canonical_job_url_aliases VALUES ('job','https://alias/job')")
    c.commit()
    sql,params=application_reference_guard(json.dumps(['job']),'company')
    c.execute(sql,params)  # Safe before an application exists.
    if reference_kind=='canonical': c.execute("INSERT INTO reviews VALUES ('job','{}')")
    if reference_kind=='external': c.execute("INSERT INTO reviews VALUES ('12345','{}')")
    if reference_kind=='url': c.execute('INSERT INTO run_jobs VALUES (?,?)',('',json.dumps({'link':'https://alias/job'})))
    if reference_kind=='nested_payload': c.execute('INSERT INTO run_blobs VALUES (?)',(json.dumps({'saved':{'canonical_job_id':'job'}}),))
    c.commit()
    with pytest.raises(sqlite3.IntegrityError), c:
        c.execute(sql,params)
        c.execute('DELETE FROM canonical_jobs')
    assert c.execute('SELECT COUNT(*) FROM canonical_jobs').fetchone()[0]==1
