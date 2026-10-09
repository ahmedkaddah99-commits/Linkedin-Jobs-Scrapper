import json
import sqlite3
import sys

import pytest

from backend.storage.local import LocalObjectStorage
from scripts import prepare_compact_catalog_candidate as module


def args(monkeypatch,tmp_path,receipt):
    path=tmp_path/'candidate.sqlite3'
    path.touch()
    record=tmp_path/'receipt.json'
    record.write_text(json.dumps(receipt))
    monkeypatch.setattr(sys,'argv',['candidate','--sqlite',str(path),'--restore-receipt',str(record),'--checkpoint',str(tmp_path/'state.json'),'--env',str(tmp_path/'empty.env')])
    return path


def test_unverified_restore_rejected_before_object_storage_access(monkeypatch,tmp_path):
    path=args(monkeypatch,tmp_path,{'restored':True,'quick_check':'failed'})
    monkeypatch.setattr(module,'create_catalog_evidence_storage',lambda: pytest.fail('Storage must not be accessed'))
    with pytest.raises(ValueError,match='verification'):
        module.main()
    assert path.stat().st_size == 0


def test_candidate_counts_must_match_verified_export_before_any_compaction(monkeypatch,tmp_path):
    path=args(monkeypatch,tmp_path,{'restored':True,'quick_check':'ok','counts':{'canonical_jobs':99,'job_posting_versions':0,'job_source_observations':0}})
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE canonical_jobs(id TEXT)')
        db.execute("INSERT INTO canonical_jobs VALUES('preserve')")
    monkeypatch.setattr(module,'create_catalog_evidence_storage',lambda:LocalObjectStorage(tmp_path/'objects'))
    monkeypatch.setattr(module.reducer,'reduce_catalog_storage',lambda *a,**k:pytest.fail('Compaction must not run'))
    with pytest.raises(ValueError,match='counts'):
        module.main()
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT id FROM canonical_jobs').fetchall() == [('preserve',)]
