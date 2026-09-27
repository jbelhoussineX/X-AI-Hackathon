"""Actual recent PipeLLM and instructor stack with only a simulated HTTP provider."""

import asyncio
import json
import os
import socket

import httpx2
from openai import AsyncOpenAI
import pytest

from backend.generated.recent_brief.models import Request
from src.recent_worker import execute


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    # Replace, rather than copy/read, the real environment. No local .env loading.
    monkeypatch.setattr(os, 'environ', {
        'PYTHON_DOTENV_DISABLED': '1', 'DO_NOT_TRACK': '1',
        'ENABLE_PIPELEX_CALLS': 'true', 'PIPELEX_EXECUTION_MODE': 'local',
        'OPENAI_API_KEY': 'offline-test-placeholder',
    })
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def guard(original):
        def connect(sock, address, *args, **kwargs):
            if isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1'):
                return original(sock, address, *args, **kwargs)
            raise AssertionError('External sockets are forbidden in this offline test')
        return connect

    monkeypatch.setattr(socket.socket, 'connect', guard(original_connect))
    monkeypatch.setattr(socket.socket, 'connect_ex', guard(original_connect_ex))


def request():
    return Request(topic='logement', corpus_json=json.dumps({
        'topic': 'logement', 'sources': [{
            'source_id': 'e0p0', 'event_id': 'fictitious-event',
            'text': 'Le compte rendu fictif évoque le logement étudiant.',
            'quotes': [{'quote_id': 'q0', 'excerpt': 'Le compte rendu fictif évoque le logement étudiant.'}],
        }], 'limitations': ['Test entièrement fictif, sans réseau.'],
    }, ensure_ascii=False))


def test_recent_pipelex_uses_real_sdk_instructor_and_mock_http(monkeypatch):
    sent = []

    def handler(req):
        body = json.loads(req.content)
        sent.append(body)
        assert req.url.host == 'api.openai.com'
        assert req.url.path == '/v1/responses'
        assert req.headers['authorization'] == 'Bearer offline-test-placeholder'
        assert body['model'] == 'gpt-4o-mini'
        functions = [tool for tool in body['tools'] if tool['type'] == 'function']
        assert len(functions) == 1
        answer = {'items': [{'source_id': 'e0p0', 'summary': 'Le logement étudiant est évoqué.',
                             'quote_id': 'q0'}], 'limitations': []}
        return httpx2.Response(200, json={
            'id': 'resp_offline', 'object': 'response', 'created_at': 0,
            'status': 'completed', 'model': body['model'],
            'output': [{'type': 'function_call', 'id': 'fc_offline', 'call_id': 'call_offline',
                        'status': 'completed', 'name': functions[0]['name'],
                        'arguments': json.dumps(answer, ensure_ascii=False)}],
            'usage': {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0},
        }, request=req)

    original_init = AsyncOpenAI.__init__

    def initialize(self, *args, **kwargs):
        assert kwargs['api_key'] == 'offline-test-placeholder'
        assert kwargs['max_retries'] == 0
        kwargs['http_client'] = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(AsyncOpenAI, '__init__', initialize)
    result = asyncio.run(execute(request()))
    assert result.items[0].source_id == 'e0p0'
    assert result.items[0].quote_id == 'q0'
    assert len(sent) == 1

@pytest.mark.parametrize('stage,answer,limit', [
    ('plan', {'queries': ['logement étudiant']}, 700),
    ('select', {'queries': ['logement étudiant'], 'event_ids': ['c0']}, 900),
    ('select', {'queries': [], 'event_ids': []}, 900),
    ('select', {'queries': ['IA'], 'event_ids': ['c0']}, 900),
    ('select', {'queries': ['logement', 'emploi', 'bourses'], 'event_ids': ['c0']}, 900),
    ('evaluate', {'coverage': 'partiel', 'relevant_sources': ['e0p0'],
                  'gaps': ['Le corpus est partiel.'], 'followup_query': 'bourses'}, 1600),
    ('summarize', {'items': [{'source_id': 'e0p0', 'quote_id': 'q0',
        'summary': 'Une proposition traite du logement.', 'relevance': 'Le sujet demandé est abordé.',
        'relevance_fields': [], 'uncertainty': 'Aucune adoption établie.'}], 'limitations': []}, 3500),
    ('summarize', {'items': [{'source_id': 'e0p0', 'quote_id': 'q0',
        'summary': 'Une proposition traite du logement.', 'relevance': '',
        'relevance_fields': [], 'uncertainty': 'Aucune adoption établie.'}], 'limitations': []}, 3500),
])
def test_agent_stages_use_real_pipelex_and_mock_http(monkeypatch, stage, answer, limit):
    from src.recent_agent_worker import execute_stage
    from backend.agent_models import OUTPUTS
    captured = []

    def handler(req):
        body = json.loads(req.content)
        captured.append(body)
        assert req.url.host == 'api.openai.com'
        assert body['model'] == 'gpt-4o-mini'
        assert body['max_output_tokens'] == limit
        tool = next(tool for tool in body['tools'] if tool['type'] == 'function')
        return httpx2.Response(200, json={
            'id': 'resp_offline', 'object': 'response', 'created_at': 0,
            'status': 'completed', 'model': body['model'],
            'output': [{'type': 'function_call', 'id': 'fc_offline', 'call_id': 'call_offline',
                'status': 'completed', 'name': tool['name'], 'arguments': json.dumps(answer)}],
            'usage': {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0},
        }, request=req)

    original_init = AsyncOpenAI.__init__
    def initialize(self, *args, **kwargs):
        assert kwargs['api_key'] == 'offline-test-placeholder'
        assert kwargs['max_retries'] == 0
        kwargs['http_client'] = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
        original_init(self, *args, **kwargs)
    monkeypatch.setattr(AsyncOpenAI, '__init__', initialize)
    output = asyncio.run(execute_stage(stage, request()))
    assert output == OUTPUTS[stage].model_validate(answer)
    assert len(captured) == 1


@pytest.mark.parametrize('failure,reason', [
    ('truncated', 'max_output_tokens'),
    ('invalid_json', 'report_schema'),
    ('missing_field', 'report_schema'),
])
def test_synthesis_failures_are_diagnosed_without_retry_or_raw_content(monkeypatch, failure, reason):
    from src.recent_agent_worker import execute_stage
    from src.pipelex_worker import error_code, error_diagnostic
    from src.pipelex_client import failure_message
    captured = []

    def handler(req):
        body = json.loads(req.content)
        captured.append(body)
        tool = next(tool for tool in body['tools'] if tool['type'] == 'function')
        arguments = '{"items":SECRET_PRIVATE_TEXT' if failure != 'missing_field' else json.dumps({
            'items': [{'source_id': 'e0p0', 'quote_id': 'q0', 'summary': 'SECRET_PRIVATE_TEXT'}],
            'limitations': [],
        })
        incomplete = failure == 'truncated'
        return httpx2.Response(200, json={
            'id': 'resp_offline', 'object': 'response', 'created_at': 0,
            'status': 'incomplete' if incomplete else 'completed', 'model': body['model'],
            'incomplete_details': {'reason': 'max_output_tokens'} if incomplete else None,
            'output': [{'type': 'function_call', 'id': 'fc_offline', 'call_id': 'call_offline',
                       'status': 'incomplete' if incomplete else 'completed',
                       'name': tool['name'], 'arguments': arguments}],
            'usage': {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0},
        }, request=req)

    original_init = AsyncOpenAI.__init__
    def initialize(self, *args, **kwargs):
        assert kwargs['api_key'] == 'offline-test-placeholder'
        assert kwargs['max_retries'] == 0
        kwargs['http_client'] = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
        original_init(self, *args, **kwargs)
    monkeypatch.setattr(AsyncOpenAI, '__init__', initialize)
    with pytest.raises(Exception) as caught:
        asyncio.run(execute_stage('summarize', request()))
    assert len(captured) == 1
    assert error_code(caught.value) == 'format'
    diagnostic = error_diagnostic(caught.value)
    assert diagnostic['reason'] == reason
    message = failure_message('format', diagnostic)
    assert 'SECRET_PRIVATE_TEXT' not in message
    assert 'offline-test-placeholder' not in message
