import importlib.util
from pathlib import Path


PATH = Path(__file__).resolve().parents[1] / 'deploy/vps-observability/stage_charts.py'
spec = importlib.util.spec_from_file_location('runr_stage_charts', PATH)
stage_charts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage_charts)


def test_city_grouping_and_unknown_are_bounded():
    assert stage_charts.city('Berlin, Germany') == 'Berlin'
    assert stage_charts.city('Remote / Germany') == 'Unknown'
    assert stage_charts.city('München, Bavaria') == 'Munich'
    assert stage_charts.city('Berlin / Hamburg') == 'Unknown'


def test_source_stage_aggregator_deduplicates_and_preserves_real_date():
    source = [
        {'id': '1', 'location': 'Berlin, Germany', 'date': '2026-09-01T10:00:00Z'},
        {'id': '1', 'location': 'Berlin', 'date': '2026-09-02T10:00:00Z'},
        {'id': '2', 'location': '', 'date': ''},
    ]
    result = stage_charts.aggregate(source, 'linkedin', 'collected', {'Berlin'})
    assert result[('linkedin', 'collected', 'Berlin', '2026-09-01')] == 1
    assert result[('linkedin', 'collected', 'Unknown', 'Unknown')] == 1
    assert sum(result.values()) == 2


def test_series_caps_city_labels_and_old_dates():
    row = [{'id': str(i), 'location': 'Hamburg', 'date': '2020-01-01'} for i in range(20)]
    result = stage_charts.aggregate(row, 'employer', 'detailed', {'Berlin'}, as_of='2026-09-28')
    assert result == {('employer', 'detailed', 'Other', 'Older'): 20}


def test_stage_snapshot_is_not_sum_of_stage_memberships():
    counts = stage_charts.stage_counts({'collected': {'1', '2'}, 'detailed': {'1'}, 'imported': {'1'}, 'published': {'1'}})
    assert counts == {'collected': 2, 'detailed': 1, 'imported': 1, 'published': 1}


def test_catalog_accepts_libsql_cursor_that_only_supports_fetchall():
    class Cursor:
        def fetchall(self):
            return [('canonical-1', 'linkedin', 'Berlin', '2026-09-01T00:00:00Z', 1)]
    class Connection:
        def execute(self, query):
            return Cursor()
    result = list(stage_charts.catalog_records(Connection()))
    assert [(source, stage) for source, stage, _ in result] == [('linkedin', 'imported'), ('linkedin', 'published')]
