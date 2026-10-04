import io
import json

import pytest

from scripts import classify_published_catalog as rollout


def test_bounded_transport_preserves_typed_parameters_and_rows(monkeypatch):
    monkeypatch.setenv('TURSO_DATABASE_URL', 'libsql://example.invalid')
    monkeypatch.setenv('TURSO_AUTH_TOKEN', 'test-token')
    def request(req, timeout):
        assert timeout == 60
        body = json.loads(req.data)
        assert body['requests'][1] == {'type': 'close'}
        assert body['requests'][0]['stmt']['args'] == [
            {'type': 'null'}, {'type': 'integer', 'value': '2'},
            {'type': 'float', 'value': 2.5}, {'type': 'text', 'value': 'hello'}]
        return io.BytesIO(json.dumps({'results': [{'type': 'ok', 'response': {'result': {
            'cols': [{'name': 'id'}, {'name': 'missing'}],
            'rows': [[{'type': 'integer', 'value': '42'}, {'type': 'null'}]]}}}]}).encode())
    monkeypatch.setattr(rollout, 'urlopen', request)
    assert rollout.http_execute('SELECT ?', (None, 2, 2.5, 'hello')) == [{'id': 42, 'missing': None}]


def test_statement_error_is_not_reported_as_success(monkeypatch):
    monkeypatch.setenv('TURSO_DATABASE_URL', 'libsql://example.invalid')
    monkeypatch.setenv('TURSO_AUTH_TOKEN', 'test-token')
    monkeypatch.setattr(rollout, 'urlopen', lambda *args, **kwargs: io.BytesIO(
        b'{"results":[{"type":"error","error":{"code":"SQLITE_BUSY"}}]}'))
    with pytest.raises(RuntimeError, match='SQLITE_BUSY'):
        rollout.http_execute('SELECT 1')
