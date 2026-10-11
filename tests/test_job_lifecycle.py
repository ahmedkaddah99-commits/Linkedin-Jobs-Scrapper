from datetime import datetime, timezone
import pytest
from backend.acquisition.job_lifecycle import exclusion_reason

NOW = datetime(2026, 10, 11, tzinfo=timezone.utc)

@pytest.mark.parametrize('record,expected', [
 ({'posted_at':'2026-09-10','last_seen_at':'2026-10-11'}, 'posted_over_30_days'),
 ({'first_seen_at':'2026-09-10','posted_at':'2026-10-10'}, 'first_seen_over_30_days'),
 ({'posted_at':'2026-09-11'}, ''),
 ({'posted_at':'invalid','first_seen_at':'2026-10-10'}, ''),
 ({'source_timestamps':{'fields':{'source_posted_at':{'value':'2026-09-10'}}}}, 'posted_over_30_days'),
])
def test_age_policy(record, expected):
    assert exclusion_reason(record, now=NOW) == expected

def test_publication_rejects_recently_observed_old_posting():
    from backend.acquisition.job_publication_completeness import validate_job_for_publication
    result = validate_job_for_publication({'posted_at':'2026-09-01','observed_at':'2026-10-11'}, now=NOW)
    assert 'posted_over_30_days' in result.reason_codes

def test_retention_is_bounded_and_preserves_canonical_history(tmp_path):
    import sqlite3
    from backend.repositories.sqlite_acquisition import SqliteAcquisitionStore
    from backend.acquisition.job_lifecycle import maintain_job_lifecycle
    path = tmp_path / 'catalog.db'
    SqliteAcquisitionStore(path)
    with sqlite3.connect(path) as db:
        for key,first in [('old','2026-08-01'),('young','2026-10-10')]:
            db.execute("INSERT INTO canonical_jobs(canonical_job_id,company_id,identity_key,title,first_seen_at,last_seen_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)", (key,'co',key,key,first,'2026-10-11',first,'2026-10-11'))
        db.execute("INSERT INTO acquisition_publications(publication_id,cycle_id,status,snapshot_json,published_at) VALUES('p','c','valid','[{\"canonical_job_id\":\"old\"},{\"canonical_job_id\":\"young\"}]','now')")
        db.execute("INSERT INTO acquisition_publication_head VALUES(1,'p','now')")
        db.executemany("INSERT INTO acquisition_publication_jobs VALUES('p',?)", [('old',),('young',)])
    assert maintain_job_lifecycle(path, now=NOW)['expired_jobs'] == 0
    result = maintain_job_lifecycle(path, now=NOW, apply=True, batch_size=1, max_batches=1)
    assert result['expired_jobs'] == 1
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT lifecycle_state FROM canonical_jobs WHERE canonical_job_id='old'").fetchone()[0] == 'expired'
        assert db.execute('SELECT count(*) FROM canonical_jobs').fetchone()[0] == 2
        assert db.execute('SELECT canonical_job_id FROM acquisition_publication_jobs').fetchall() == [('young',)]
        assert 'old' not in db.execute('SELECT snapshot_json FROM acquisition_publications').fetchone()[0]
