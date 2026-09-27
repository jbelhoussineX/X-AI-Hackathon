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
    monkeypatch.setenv('POLITICAL_DATA_SOURCE', 'web')
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
@pytest.mark.parametrize('contact_link', ['absent', 'unproven', 'proven'])
def test_real_pipelex_graph_with_mocked_openai(monkeypatch, report, followup, contact_link):
    import httpx2
    from openai import AsyncOpenAI
    from src.pipelex_worker import execute
    if contact_link != 'absent':
        report['contacts'][0]['contact_url'] = URL
    if contact_link == 'proven':
        report['contacts'][0]['evidence'].append({
            'purpose': 'contact', 'url': URL, 'excerpt': 'Page de contact fictive.', 'location': None,
        })
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
            assert body['model'] == 'gpt-5-mini'
            assert body['reasoning'] == {'effort': 'low'}
            assert body['max_output_tokens'] == 4000
            assert body['max_tool_calls'] == 3
            assert body['tool_choice'] == 'required'
        else:
            assert body['model'] == 'gpt-4o-mini'
            assert 'reasoning' not in body
            assert body['text']['format']['strict'] is True
            sent_schema = body['text']['format']['schema']
            if 'documents' in sent_schema['properties']:
                from jsonschema import Draft202012Validator
                assert not Draft202012Validator(sent_schema).is_valid({**report, 'scope': ' '})
                assert not Draft202012Validator(sent_schema).is_valid({**report, 'documents': report['documents'] * 5})
                assert not Draft202012Validator(sent_schema).is_valid({**report, 'contacts': report['contacts'] * 4})
                Draft202012Validator(sent_schema).validate(report)
        return httpx2.Response(200, json=responses.pop(0), request=request)
    def client():
        return AsyncOpenAI(api_key='offline-test-placeholder', max_retries=0,
                           http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
                           base_url='https://api.openai.com/v1')
    monkeypatch.setattr('src.openai_research._make_client', client)
    result = asyncio.run(execute({'topic': 'Sujet de test', 'start': '2024-01-01', 'end': '2026-09-27'}))
    assert result['topic'] == 'Sujet de test'
    assert result['documents'] == report['documents']
    contact = result['contacts'][0]
    assert contact['contact_url'] == (URL if contact_link == 'proven' else None)
    assert contact['evidence'] == report['contacts'][0]['evidence']
    assert contact['document_ids'] == report['contacts'][0]['document_ids']
    assert any('Page de contact de l’interlocuteur' in item for item in result['limitations']) == (contact_link == 'unproven')
    assert len(captured) == (4 if followup else 3)
    assert not responses


def test_story_of_search_is_not_tool_evidence():
    with pytest.raises(ResearchFailure, match='sources'):
        sources_from_response(wire_response('J’ai consulté le site officiel ' + URL))


def test_unproven_contact_link_is_omitted_without_inventing_or_reusing_other_proof(report):
    from src.openai_research import prepare_report
    from src.contracts import validate_report
    contact = report['contacts'][0]
    contact['contact_url'] = 'https://www.assemblee-nationale.fr/contact-non-etabli'
    contact['evidence'].append({'purpose': 'contact', 'url': URL, 'excerpt': 'Autre page fictive.', 'location': None})
    original = deepcopy(report)
    with pytest.raises(ReportError) as caught:
        validate_report(report)
    assert caught.value.reason == 'missing_contact_evidence'  # Shared contract stays strict.
    result = prepare_report(report)
    assert report == original
    assert result['documents'] == original['documents']
    assert result['contacts'][0] == {**contact, 'contact_url': None}
    assert len(result['limitations']) == len(report['limitations']) + 1
    assert 'contact-non-etabli' not in json.dumps(result)
    validate_report(result)


@pytest.mark.parametrize('failure', ['relation', 'document', 'unsafe_link', 'empty_excerpt', 'schema'])
def test_omitting_contact_link_keeps_other_validation_failures(report, failure):
    from src.openai_research import prepare_report
    contact = report['contacts'][0]
    contact['contact_url'] = URL
    if failure == 'relation':
        contact['evidence'] = []
    elif failure == 'document':
        report['documents'][0]['evidence'] = []
    elif failure == 'unsafe_link':
        contact['contact_url'] = 'http://127.0.0.1/'
    elif failure == 'empty_excerpt':
        contact['evidence'].append({'purpose': 'contact', 'url': URL, 'excerpt': ' ', 'location': None})
    else:
        contact['evidence'] = None
    with pytest.raises(ReportError):
        prepare_report(report)


def test_dedicated_contact_proof_from_unobserved_source_still_fails(monkeypatch, report):
    run = Run('test', '2024-01-01', '2026-09-27', source_urls={URL})
    other = 'https://www.senat.fr/contact-non-consulte'
    report['contacts'][0]['contact_url'] = other
    report['contacts'][0]['evidence'].append({'purpose': 'contact', 'url': other, 'excerpt': 'Fictif.', 'location': None})
    async def fake(**kwargs):
        return SimpleNamespace(output_text=json.dumps(report))
    monkeypatch.setattr(run, 'call', fake)
    with pytest.raises(ResearchFailure) as caught:
        asyncio.run(run.finish())
    assert caught.value.code == 'sources'
    assert caught.value.reason == 'unobserved_source'


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


@pytest.mark.parametrize('status,expected', [(400, 'request'), (404, 'model'), (429, 'quota'), (500, 'server')])
def test_pipeline_preserves_safe_api_failure_details(monkeypatch, status, expected):
    import httpx2
    from openai import AsyncOpenAI
    from src.pipelex_worker import execute, error_code, error_diagnostic
    from src.pipelex_client import failure_message

    requests = []
    def handler(request):
        requests.append(request)
        return httpx2.Response(status, request=request, json={'error': {
            'message': 'SECRET_IN_RAW_ERROR', 'type': 'invalid_request_error',
            'code': 'unsupported_parameter', 'param': 'max_tool_calls',
        }})
    def client():
        return AsyncOpenAI(api_key='offline-test-placeholder', max_retries=0,
                           http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
                           base_url='https://api.openai.com/v1')
    monkeypatch.setattr('src.openai_research._make_client', client)
    with pytest.raises(Exception) as caught:
        asyncio.run(execute({'topic': 'test', 'start': '2024-01-01', 'end': '2026-09-27'}))
    assert error_code(caught.value) == expected
    details = error_diagnostic(caught.value)
    assert details['stage'] == 'collecter'
    assert details['http_status'] == status
    assert details['param'] == 'max_tool_calls'
    message = failure_message(expected, details)
    assert 'SECRET_IN_RAW_ERROR' not in message
    assert f'HTTP={status}' in message
    assert len(requests) == 1


def test_optional_null_sources_and_annotations():
    data = wire_response('Notes de test', web=True)
    data['output'][0]['action']['sources'] = None
    data['output'][1]['content'][0]['annotations'] = [
        {'type': 'url_citation', 'url': URL, 'title': 'Document fictif', 'start_index': 0, 'end_index': 5},
    ]
    assert sources_from_response(data) == {URL}
    data['output'][1]['content'][0]['annotations'] = None
    assert sources_from_response(data) == set()


def test_worker_diagnostic_is_filtered_again_before_display(monkeypatch):
    payload = {'ok': False, 'error': 'request', 'diagnostic': {
        'stage': 'collecter', 'http_status': 400, 'param': 'SECRET_PARAM', 'code': ['untrusted'],
        'type': 'BadRequestError', 'message': 'SECRET_MESSAGE', 'headers': 'SECRET_HEADERS',
        'reason': 'SECRET_REASON', 'field': 'SECRET_FIELD',
    }}
    process = Mock(return_value=SimpleNamespace(returncode=1, stdout=json.dumps(payload)))
    monkeypatch.setattr('src.pipelex_client.subprocess.run', process)
    with pytest.raises(PipelexError) as caught:
        run_pipelex('test', '2024-01-01', '2026-09-27')
    assert 'HTTP=400' in str(caught.value)
    assert 'collecter' in str(caught.value)
    assert 'SECRET' not in str(caught.value)
    process.assert_called_once()


@pytest.mark.parametrize('reason', [
    'invalid_date', 'invalid_stage_evidence',
    'publication_outside_period', 'document_kind', 'report_schema', 'invalid_json',
    'max_output_tokens', 'content_filter', 'response_refusal', 'empty_response', 'empty_field', 'item_limit',
])
def test_final_failure_reaches_ui_without_raw_content_or_retry(monkeypatch, report, reason):
    import httpx2
    from openai import AsyncOpenAI
    from src.pipelex_worker import execute, error_code, error_diagnostic
    from src.pipelex_client import VALIDATION_REASONS

    document = report['documents'][0]
    if reason == 'invalid_date':
        document['publication_date'] = 'SECRET_PARTIAL_DATE'
    elif reason == 'invalid_stage_evidence':
        document['stage'] = 'SECRET_STAGE'
        document['evidence'] = [e for e in document['evidence'] if e['purpose'] != 'statut']
    elif reason == 'publication_outside_period':
        document['publication_date'] = '2020-01-01'
    elif reason == 'document_kind':
        document['kind'] = 'programme'
    elif reason == 'report_schema':
        report['scope'] = {'SECRET_UNEXPECTED_FIELD': True}
    elif reason == 'empty_field':
        document['title'] = ' '
    elif reason == 'item_limit':
        report['documents'] *= 5

    final = wire_response('SECRET_INVALID_JSON' if reason == 'invalid_json' else json.dumps(report))
    if reason in ('max_output_tokens', 'content_filter'):
        final['status'] = 'incomplete'
        final['incomplete_details'] = {'reason': reason}
    elif reason == 'response_refusal':
        final['output'][0]['content'] = [{'type': 'refusal', 'refusal': 'SECRET_REFUSAL'}]
    elif reason == 'empty_response':
        final['output'] = []
    responses = [
        wire_response('Notes fictives.', web=True),
        wire_response(json.dumps({'needs_more': False, 'followup_query': None, 'limitations': []})),
        final,
    ]
    calls = []
    def handler(request):
        calls.append(request)
        return httpx2.Response(200, json=responses.pop(0), request=request)
    def client():
        return AsyncOpenAI(api_key='offline-test-placeholder', max_retries=0,
                           http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)))
    monkeypatch.setattr('src.openai_research._make_client', client)
    with pytest.raises(Exception) as caught:
        asyncio.run(execute({'topic': 'test', 'start': '2024-01-01', 'end': '2026-09-27'}))
    assert error_code(caught.value) == 'format'
    diagnostic = error_diagnostic(caught.value)
    assert diagnostic['stage'] == 'rediger'
    assert diagnostic['reason'] == reason
    if reason == 'empty_field':
        assert diagnostic['field'] == 'documents.title'
    assert len(calls) == 3
    assert not responses
    payload = {'ok': False, 'error': error_code(caught.value), 'diagnostic': diagnostic}
    process = Mock(return_value=SimpleNamespace(returncode=1, stdout=json.dumps(payload)))
    monkeypatch.setattr('src.pipelex_client.subprocess.run', process)
    with pytest.raises(PipelexError) as shown:
        run_pipelex('test', '2024-01-01', '2026-09-27')
    assert VALIDATION_REASONS[reason] in str(shown.value)
    assert 'étape=rediger' in str(shown.value)
    if reason == 'empty_field':
        assert 'champ=documents.title' in str(shown.value)
    assert 'SECRET' not in str(shown.value)
    process.assert_called_once()


def test_unknown_publication_and_later_stage_remain_accepted(monkeypatch, report):
    run = Run('test', '2024-01-01', '2026-09-27', source_urls={URL})
    document = report['documents'][0]
    document['publication_date'] = None
    document['stage'] = 'Statut fictif de test'
    document['stage_date'] = '2026-10-01'
    document['evidence'].append({'purpose': 'statut', 'url': URL, 'excerpt': 'Preuve fictive.', 'location': None})
    async def fake(**kwargs):
        return SimpleNamespace(output_text=json.dumps(report))
    monkeypatch.setattr(run, 'call', fake)
    result = asyncio.run(run.finish())
    assert result['documents'][0]['publication_date'] is None
    assert result['documents'][0]['stage_date'] == '2026-10-01'
    assert any('période non confirmée' in item for item in result['documents'][0]['uncertainties'])


@pytest.mark.parametrize('path', [
    ('topic',), ('scope',), ('documents', 0, 'id'), ('documents', 0, 'title'),
    ('documents', 0, 'summary'), ('contacts', 0, 'name'), ('contacts', 0, 'role'),
    ('contacts', 0, 'relation'),
])
@pytest.mark.parametrize('blank', ['', ' \t\n\u00a0'])
def test_generation_disallows_blank_fields_and_validator_names_them(report, path, blank):
    from jsonschema import Draft202012Validator
    from src.contracts import SCHEMA, validate_report
    from src.openai_research import report_response_schema
    from src.pipelex_worker import error_diagnostic
    from src.pipelex_client import failure_message

    original_schema = deepcopy(SCHEMA)
    schema = report_response_schema()
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(report)
    item = report
    for key in path[:-1]:
        item = item[key]
    item[path[-1]] = blank
    # The old generation schema accepts this; the local validator always rejected it.
    assert Draft202012Validator(SCHEMA).is_valid(report)
    assert not Draft202012Validator(schema).is_valid(report)
    with pytest.raises(ReportError) as caught:
        validate_report(report)
    field_name = '.'.join(key for key in path if isinstance(key, str))
    assert caught.value.reason == 'empty_field'
    assert caught.value.field == field_name
    assert f'champ={field_name}' in failure_message('format', error_diagnostic(caught.value))
    assert SCHEMA == original_schema


def test_generation_schema_allows_honest_empty_report_and_nulls(report):
    from jsonschema import Draft202012Validator
    from src.contracts import validate_report
    from src.openai_research import report_response_schema

    validator = Draft202012Validator(report_response_schema())
    report['documents'][0]['publication_date'] = None
    report['documents'][0]['stage'] = None
    report['documents'][0]['stage_date'] = None
    validator.validate(report)
    validate_report(report)
    report['documents'] = []
    report['contacts'] = []
    report['limitations'] = ['Aucun résultat trouvé dans le corpus consulté.']
    validator.validate(report)
    validate_report(report)


@pytest.mark.parametrize('documents,contacts,valid', [(0, 0, True), (4, 3, True), (5, 3, False), (4, 4, False)])
def test_generation_and_local_validator_agree_on_report_limits(report, documents, contacts, valid):
    from jsonschema import Draft202012Validator
    from src.contracts import SCHEMA, validate_report
    from src.openai_research import report_response_schema

    original_schema = deepcopy(SCHEMA)
    template = report['documents'][0]
    report['documents'] = [deepcopy(template) for _ in range(documents)]
    for index, document in enumerate(report['documents'][1:], start=1):
        document['id'] = template['id'] + f'-test-{index}'
    report['contacts'] = [deepcopy(report['contacts'][0]) for _ in range(contacts)]
    report['limitations'] = ['Rapport fictif de test ; corpus limité.']
    snapshot = deepcopy(report)
    schema = report_response_schema()
    Draft202012Validator.check_schema(schema)
    assert Draft202012Validator(schema).is_valid(report) is valid
    if valid:
        validate_report(report)
    else:
        with pytest.raises(ReportError) as caught:
            validate_report(report)
        assert caught.value.reason == 'item_limit'
    assert report == snapshot  # Never trim results or orphan contact references.
    assert SCHEMA == original_schema


@pytest.mark.parametrize('failure', ['supplement_truncated', 'initial_truncated', 'supplement_filter', 'supplement_timeout'])
def test_only_optional_token_truncation_preserves_initial_corpus(monkeypatch, report, failure):
    import httpx2
    from openai import AsyncOpenAI
    from src.pipelex_worker import execute, error_diagnostic, error_code

    incomplete = wire_response('PARTIAL_CONTENT_MUST_NOT_REACH_REPORT', web=True)
    incomplete['output'][0]['action']['sources'][0]['url'] = 'https://www.senat.fr/partial-only'
    incomplete['status'] = 'incomplete'
    incomplete['incomplete_details'] = {'reason': 'content_filter' if failure == 'supplement_filter' else 'max_output_tokens'}
    responses = [
        incomplete if failure == 'initial_truncated' else wire_response('Initial corpus.', web=True),
        wire_response(json.dumps({'needs_more': True, 'followup_query': 'Préciser le statut',
                                  'limitations': ['Statut à préciser.']})),
        incomplete,
        wire_response(json.dumps(report)),
    ]
    calls = []
    def handler(request):
        calls.append(json.loads(request.content))
        if len(calls) == 3 and failure == 'supplement_timeout':
            raise httpx2.ReadTimeout('Fake timeout', request=request)
        return httpx2.Response(200, json=responses.pop(0), request=request)
    def client():
        return AsyncOpenAI(api_key='offline-test-placeholder', max_retries=0,
                           http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)))
    monkeypatch.setattr('src.openai_research._make_client', client)
    request = {'topic': 'test', 'start': '2024-01-01', 'end': '2026-09-27'}
    if failure == 'supplement_truncated':
        output = asyncio.run(execute(request))
        assert len(calls) == 4  # Initial, review, one failed supplement, report; no retry.
        assert output['documents'] == report['documents']
        assert any('complémentaire a été interrompue' in item for item in output['limitations'])
        assert 'Statut à préciser.' in output['limitations']
        assert 'Initial corpus.' in calls[-1]['input']
        assert 'PARTIAL_CONTENT' not in calls[-1]['input']
        assert 'partial-only' not in calls[-1]['input']
        assert 'complémentaire a été interrompue' in calls[-1]['input']
    else:
        with pytest.raises(Exception) as caught:
            asyncio.run(execute(request))
        initial = failure == 'initial_truncated'
        assert len(calls) == (1 if initial else 3)
        assert error_diagnostic(caught.value)['stage'] == ('collecter' if initial else 'completer')
        assert error_code(caught.value) == ('timeout' if failure == 'supplement_timeout' else 'format')
