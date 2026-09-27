"""Local Pipelex + official corpus, with network and inference simulated."""
import asyncio
from copy import deepcopy
import json
import socket
from unittest.mock import Mock

import httpx2
import pytest
from openai import AsyncOpenAI

from src.contracts import ROOT
from src.openai_research import Run, ResearchFailure
from src.source_passages import passages_from_corpus, resolve_passages
from test_pipelex import wire_response

URL = 'https://www.senat.fr/leg/ppl25-1.html'


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv('PYTHON_DOTENV_DISABLED', '1')
    monkeypatch.setenv('DO_NOT_TRACK', '1')
    monkeypatch.setenv('POLITICAL_DATA_SOURCE', 'official')
    monkeypatch.setenv('OPENAI_API_KEY', 'offline-test-placeholder')
    def reject(*args, **kwargs):
        raise AssertionError('No network in tests')
    monkeypatch.setattr(socket.socket, 'connect', reject)
    monkeypatch.setattr(socket.socket, 'connect_ex', reject)


def fixture_data(empty=False):
    report = json.loads((ROOT / 'fixtures/demo.json').read_text())
    excerpts = []
    for item in report['documents'] + report['contacts']:
        for proof in item['evidence']:
            proof['url'] = URL
            excerpts.append(proof['excerpt'])
    source = {'url': URL, 'final_url': URL, 'text': ' '.join(excerpts), 'pdf_pages': None, 'truncated': False}
    prepared = {'datasets': [{'status': 'ok'}], 'records': [], 'limitations': ['Corpus fictif.'],
                'corpus': [] if empty else [source], 'pipelex_inputs': None}
    return report, prepared


@pytest.mark.parametrize('followup', [False, True])
@pytest.mark.parametrize('empty', [False, True])
def test_real_local_graph_collects_official_sources_without_web_inference(monkeypatch, followup, empty):
    from src.pipelex_worker import execute
    report, prepared = fixture_data(empty)
    draft = deepcopy(report)
    for item in draft['documents'] + draft['contacts']:
        item['evidence'] = [{'purpose': proof['purpose'], 'passage_id': 'p0001'} for proof in item['evidence']]
    expected = resolve_passages(draft, passages_from_corpus(prepared['corpus'])) if not empty else None
    collect = Mock(side_effect=lambda *args: deepcopy(prepared))
    monkeypatch.setattr('backend.data_sources.official.prepare', collect)
    responses = [wire_response(json.dumps({'needs_more': followup,
                 'followup_query': 'habitat' if followup else None, 'limitations': []})),
                 wire_response(json.dumps(draft))]
    calls = []
    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        assert body['model'] == 'gpt-4o-mini'
        assert 'tools' not in body
        if 'documents' in body['text']['format']['schema']['properties']:
            from jsonschema import Draft202012Validator
            Draft202012Validator(body['text']['format']['schema']).validate(draft)
            assert '"passages"' in body['input']
            assert prepared['corpus'][0]['text'] in body['input']
        return httpx2.Response(200, json=responses.pop(0), request=request)
    def client():
        return AsyncOpenAI(api_key='offline-test-placeholder', max_retries=0,
                           http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)))
    monkeypatch.setattr('src.openai_research._make_client', client)
    output = asyncio.run(execute({'topic': 'logement', 'start': '2024-01-01', 'end': '2026-09-27'}))
    assert len(calls) == (0 if empty else 2)
    assert collect.call_count == (2 if followup and not empty else 1)
    if empty:
        assert output['documents'] == []
        assert any('Aucun résultat trouvé dans le corpus consulté' in s for s in output['limitations'])
    else:
        assert output['documents'] == expected['documents']
        assert output['contacts'] == expected['contacts']
        assert any('extraits retrouvés' in s for s in output['limitations'])
        if followup:
            assert collect.call_args.args == ('habitat', '2024-01-01', '2026-09-27')


def test_model_written_excerpt_refused_even_for_collected_url(monkeypatch):
    from types import SimpleNamespace
    report, prepared = fixture_data()
    report['documents'][0]['evidence'][0]['excerpt'] = 'Citation absente du corpus.'
    async def fake(**kwargs):
        return SimpleNamespace(output_text=json.dumps(report))
    run = Run('logement', '2024-01-01', '2026-09-27', source_urls={URL}, prepared=prepared)
    monkeypatch.setattr(run, 'call', fake)
    with pytest.raises(ResearchFailure) as caught:
        asyncio.run(run.finish())
    assert caught.value.reason == 'invalid_evidence_selection'


def test_unknown_source_never_falls_back_to_paid_web():
    run = Run('logement', '2024-01-01', '2026-09-27', data_source='typo')
    with pytest.raises(ResearchFailure, match='configuration'):
        asyncio.run(run.research())
    assert run.calls == 0


def test_combined_corpus_cap_and_unique_sources():
    from backend.data_sources.official import merge_prepared, fetched_corpus
    _, initial = fixture_data()
    initial['corpus'][0]['text'] = 'A' * 59_990
    supplement = deepcopy(initial)
    extra = deepcopy(initial['corpus'][0])
    extra.update(url='https://www.senat.fr/leg/ppl25-2.html', final_url='https://www.senat.fr/leg/ppl25-2.html',
                 text='', pdf_pages=['B' * 8, 'C' * 8])
    supplement['corpus'].append(extra)
    result = merge_prepared(initial, supplement)
    assert len(result['corpus']) == 2
    assert result['corpus'][1]['pdf_pages'] == ['B' * 8, 'C' * 2]
    assert result['corpus'][1]['truncated']
    assert fetched_corpus(result['corpus'])[extra['url']].pages == ['B' * 8, 'C' * 2]
    assert not initial['corpus'][0]['truncated']


def test_collect_both_real_parsers_and_pages_with_mock_http(monkeypatch):
    import httpx
    from backend.data_sources import official, assembly, senate
    from test_assembly_data import archive_bytes
    from test_senate_data import csv_bytes
    seen = []
    def handler(request):
        url = str(request.url)
        seen.append(url)
        if url == assembly.DATASET_URL:
            return httpx.Response(200, content=archive_bytes())
        if url == senate.DATASET_URL:
            return httpx.Response(200, content=csv_bytes(), headers={'content-type': 'text/csv'})
        return httpx.Response(200, headers={'content-type': 'text/html'},
                              text='<main><p>Texte officiel fictif de test.</p></main>')
    monkeypatch.setattr('src.openai_research._make_client', Mock(side_effect=AssertionError('No inference')))
    output = official.prepare('logement', '2026-01-01', '2026-09-27', transport=httpx.MockTransport(handler))
    assert {d['provider'] for d in output['datasets'] if d['status'] == 'ok'} == {'senat', 'assemblee'}
    assert len(output['records']) == 2
    assert all('Texte officiel fictif' in source['text'] for source in output['corpus'])
    assert len(output['corpus']) == 3
    assert len(seen) == 5
    assert all(url.startswith(('https://data.', 'https://www.senat.fr/', 'https://www.assemblee-nationale.fr/')) for url in seen)


def test_pdf_worker_handles_invalid_and_textless_documents():
    import io
    from pypdf import PdfWriter
    from backend.pdf_text_worker import extract_pdf
    assert extract_pdf(b'not a PDF')['status'] == 'invalid_pdf'
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    output = io.BytesIO()
    writer.write(output)
    assert extract_pdf(output.getvalue())['status'] == 'pdf_no_text'
