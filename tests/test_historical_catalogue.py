"""Historical coverage and unlimited metadata export; no real network or inference."""
from dataclasses import replace

import httpx
import pytest

from backend.data_sources import assembly, catalogue, official, senate
from test_assembly_data import archive_bytes
from test_senate_data import csv_bytes


def archive(legislature, year):
    return archive_bytes(uid=f'PIONANR5L{legislature}B1234', legislature=str(legislature),
                         dossierRef=f'DLR5L{legislature}N12345',
                         cycleDeVie={'chrono': {'dateDepot': f'{year}-02-01',
                                               'datePublication': f'{year}-02-02'}})


@pytest.mark.parametrize('legislature,year', [(15, 2017), (16, 2023), (17, 2026)])
def test_archive_preserves_legislature_and_dates(legislature, year):
    record = assembly.parse_archive(archive(legislature, year), legislature)[0]
    assert record.initial_date == f'{year}-02-01'
    assert f'/dyn/{legislature}/dossiers/' in record.dossier_url
    assert f'L{legislature}B' in record.document_url
    with pytest.raises(ValueError):
        assembly.parse_archive(archive(legislature, year), 14)


def test_period_selects_all_relevant_archives():
    assert assembly.legislatures_for_period('2017-06-21', '2026-09-27') == [15, 16, 17]
    assert assembly.legislatures_for_period('2017-06-21', '2019-12-31') == [15]
    assert assembly.legislatures_for_period('2020-01-01', '2021-12-31') == [15]
    assert assembly.legislatures_for_period('2023-01-01', '2023-12-31') == [16]
    assert assembly.legislatures_for_period('2026-01-01', '2026-09-27') == [17]
    assert assembly.legislatures_for_period('2024-06-01', '2024-07-31') == [16, 17]


def test_inventory_merges_archives_and_keeps_healthy_ones_after_failure():
    requests = []
    def handler(request):
        url = str(request.url)
        requests.append(url)
        if url == assembly.DATASET_URLS[16]:
            return httpx.Response(503)
        legislature = next(n for n, source in assembly.DATASET_URLS.items() if source == url)
        return httpx.Response(200, content=archive(legislature, {15: 2020, 17: 2026}[legislature]))
    result = assembly.inventory('logement', '2020-01-01', '2026-09-27', transport=httpx.MockTransport(handler))
    assert len(requests) == 3  # No retry of the unavailable archive.
    assert [d['status'] for d in result['datasets']] == ['ok', 'unavailable', 'ok']
    assert [r['initial_date'] for r in result['records']] == ['2026-02-01', '2020-02-01']


def test_invalid_period_and_topic_fail_before_network():
    def reject(request):
        pytest.fail('Invalid input must not download anything')
    for topic, start, end in [('logement', '2026-01-01', '2020-01-01'), ('le', '2020-01-01', '2026-01-01')]:
        with pytest.raises(ValueError):
            assembly.inventory(topic, start, end, transport=httpx.MockTransport(reject))


def test_partial_coverage_reaches_report_limitations(monkeypatch):
    monkeypatch.setattr(senate, 'fetch_dataset', lambda **kwargs: (csv_bytes(), {}))
    monkeypatch.setattr(official, 'collect_dossiers', lambda *args, **kwargs: ([], {}, []))
    monkeypatch.setattr(assembly, 'inventory', lambda *args, **kwargs: {
        'datasets': [{'provider': 'assemblee', 'legislature': 15, 'status': 'unavailable'}], 'records': []})
    output = official.prepare('logement', '2020-01-01', '2026-09-27')
    assert any('15e législature indisponible' in text for text in output['limitations'])


def test_catalogue_has_no_top_n_limit_and_keeps_later_promulgations(monkeypatch):
    template = assembly.parse_archive(archive(15, 2020), 15)[0]
    records = [replace(template, id=f'assemblee:test-{i}') for i in range(10)]
    records.append(replace(template, id='old', initial_date='2019-01-01', publication_date='2019-01-02'))
    records.append(replace(template, id='undated', initial_date=None, publication_date=None))
    monkeypatch.setattr(assembly, 'load_inventories', lambda *args, **kwargs: (records, [{'status': 'ok'}]))
    monkeypatch.setattr(senate, 'fetch_dataset', lambda **kwargs: (b'', {}))
    senate_record = senate.parse_csv(csv_bytes())[0]
    monkeypatch.setattr(senate, 'parse_csv', lambda body: [
        replace(senate_record, initial_date='2019-01-01', promulgation_date='2020-01-01')])
    result = catalogue.build('2020-01-01', '2020-12-31')
    assert result['status'] == 'ok'
    assert result['record_count'] == 11
    assert result['undated_notices_excluded'] == 1
    assert not {'old', 'undated'} & {r['id'] for r in result['records']}
    assert next(r for r in result['records'] if r['provider'] == 'senat')['period_matched_on'] == ['promulgation_date']


def test_catalogue_cli_saves_partial_status_and_refuses_overwrite(tmp_path, monkeypatch):
    def build(start, end):
        assert start == '2017-06-21'
        return {'record_count': 0, 'status': 'partial'}
    monkeypatch.setattr(catalogue, 'build', build)
    path = tmp_path / 'snapshot.json'
    assert catalogue.main(['--output', str(path)]) == 1
    saved = path.read_bytes()
    with pytest.raises(SystemExit):
        catalogue.main(['--output', str(path)])
    assert path.read_bytes() == saved
