"""Vrai moteur Pipelex, transport OpenAI simulé ; aucun appel externe."""
import asyncio
from copy import deepcopy
import json
import socket
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.contracts import ROOT, ReportError
from src.openai_research import Run, ResearchFailure, sources_from_response
from src.pipelex_client import PipelexError, run_pipelex
from src.service import search

URL = 'https://www.assemblee-nationale.fr/dyn/test-fixture-fictive'


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv('PYTHON_DOTENV_DISABLED', '1')
    monkeypatch.setenv('DO_NOT_TRACK', '1')
    monkeypatch.setenv('OPENAI_API_KEY', 'offline-test-placeholder')
    def reject(*args, **kwargs):
        raise AssertionError('Réseau interdit pendant les tests')
    monkeypatch.setattr(socket.socket, 'connect', reject)
    monkeypatch.setattr(socket.socket, 'connect_ex', reject)


@pytest.fixture
def report():
    result = json.loads((ROOT / 'fixtures/demo.json').read_text())
    for item in result['documents'] + result['contacts']:
        for evidence in item['evidence']:
            evidence['url'] = URL
    return result


def wire_response(text, web=False):
    output = [{'id': 'msg_offline', 'type': 'message', 'role': 'assistant', 'status': 'completed',
               'content': [{'type': 'output_text', 'text': text, 'annotations': []}]}]
    if web:
        output.insert(0, {'id': 'ws_offline', 'type': 'web_search_call', 'status': 'completed',
                          'action': {'type': 'search', 'query': 'test fictif',
                                     'sources': [{'type': 'url', 'url': URL}]}})
    return {'id': 'resp_offline', 'object': 'response', 'created_at': 0, 'status': 'completed',
            'model': 'offline-fixture', 'output': output,
            'usage': {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0}}


@pytest.mark.parametrize('followup', [False, True])
def test_real_pipelex_graph_with_mocked_openai(monkeypatch, report, followup):
    import httpx2
    from openai import AsyncOpenAI
    from src.pipelex_worker import execute
    captured = []
    review = {'needs_more': followup, 'followup_query': 'préciser le statut' if followup else None,
              'limitations': ['Corpus fictif de test hors ligne.']}
    responses = [wire_response('Notes fictives documentées.', web=True), wire_response(json.dumps(review))]
    if followup:
        responses.append(wire_response('Complément fictif documenté.', web=True))
    responses.append(wire_response(json.dumps(report)))
    def handler(request):
        body = json.loads(request.content)
        captured.append(body)
        assert request.url.host == 'api.openai.com'
        assert request.url.path == '/v1/responses'
        assert body['store'] is False
        if 'tools' in body:
            assert body['model'] == 'gpt-4.1-mini'
            assert body['max_tool_calls'] == 3
            assert body['tool_choice'] == 'required'
        else:
            assert body['model'] == 'gpt-4o-mini'
            assert body['text']['format']['strict'] is True
        return httpx2.Response(200, json=responses.pop(0), request=request)
    def client():
        return AsyncOpenAI(api_key='offline-test-placeholder', max_retries=0,
                           http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
                           base_url='https://api.openai.com/v1')
    monkeypatch.setattr('src.openai_research._make_client', client)
    result = asyncio.run(execute({'topic': 'Sujet de test', 'start': '2024-01-01', 'end': '2026-09-27'}))
    assert result['topic'] == 'Sujet de test'
    assert result['documents'] == report['documents']
    assert len(captured) == (4 if followup else 3)
    assert not responses


def test_story_of_search_is_not_tool_evidence():
    with pytest.raises(ResearchFailure, match='sources'):
        sources_from_response(wire_response('J’ai consulté le site officiel ' + URL))


@pytest.mark.parametrize('url', ['https://evil.test/x', 'https://senat.fr.evil.org/x', 'https://127.0.0.1/x'])
def test_non_official_tool_url_rejected(url):
    data = wire_response('Résultat fictif', web=True)
    data['output'][0]['action']['sources'][0]['url'] = url
    assert sources_from_response(data) == set()


def test_no_fifth_call():
    run = Run('test', '2024-01-01', '2026-09-27', calls=4)
    with pytest.raises(ResearchFailure):
        asyncio.run(run.call(prompt='Interdit'))


def test_report_with_invented_source_refused(monkeypatch, report):
    run = Run('test', '2024-01-01', '2026-09-27', source_urls={URL})
    report['documents'][0]['evidence'][0]['url'] = 'https://www.senat.fr/source-non-consultee'
    async def fake(**kwargs):
        return SimpleNamespace(output_text=json.dumps(report))
    monkeypatch.setattr(run, 'call', fake)
    with pytest.raises(ResearchFailure, match='sources'):
        asyncio.run(run.finish())


def test_invalid_review_cannot_trigger_search(monkeypatch):
    run = Run('test', '2024-01-01', '2026-09-27')
    async def fake(**kwargs):
        return SimpleNamespace(output_text='{"needs_more": "yes", "followup_query": "test", "limitations": []}')
    monkeypatch.setattr(run, 'call', fake)
    with pytest.raises(ResearchFailure, match='format'):
        asyncio.run(run.review())


def test_subprocess_result_and_existing_contract(monkeypatch, report):
    process = Mock(return_value=SimpleNamespace(returncode=0, stdout=json.dumps({'ok': True, 'report': report})))
    monkeypatch.setattr('src.pipelex_client.subprocess.run', process)
    result = search('test', '2024-01-01', '2026-09-27', 'pipelex')
    assert result['mode'] == 'pipelex'
    assert result['conversation_id'] is None
    assert set(result) == {'mode', 'report', 'conversation_id', 'run_at_utc', 'duration_seconds', 'validation'}
    process.assert_called_once()
    assert process.call_args.kwargs['cwd'] == ROOT


@pytest.mark.parametrize('code', ['credentials', 'quota', 'timeout', 'provider'])
def test_error_never_replaced_with_demo_or_raw_secret(monkeypatch, code):
    process = Mock(return_value=SimpleNamespace(returncode=1, stdout=json.dumps({'ok': False, 'error': code}), stderr='SECRET'))
    monkeypatch.setattr('src.pipelex_client.subprocess.run', process)
    with pytest.raises(PipelexError) as error:
        run_pipelex('test', '2024-01-01', '2026-09-27')
    assert 'SECRET' not in str(error.value)
    process.assert_called_once()


def test_local_timeout_no_retry(monkeypatch):
    process = Mock(side_effect=subprocess.TimeoutExpired('worker', 240))
    monkeypatch.setattr('src.pipelex_client.subprocess.run', process)
    with pytest.raises(PipelexError, match='continuer'):
        run_pipelex('test', '2024-01-01', '2026-09-27')
    process.assert_called_once()


def test_service_filters_pipelex_dates(monkeypatch, report):
    monkeypatch.setattr('src.service.run_pipelex', lambda *args: (deepcopy(report), None))
    with pytest.raises(ReportError, match='période'):
        search('test', '2020-01-01', '2020-12-31', 'pipelex')
