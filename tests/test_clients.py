import asyncio
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from pipelex_sdk.runs import RunResults
from backend.dust.client import parse_response, research
from backend.pipelex_comparison import compare_document, method_contents
from backend.generated.political_watch.models import ComparisonRequest

ROOT = Path(__file__).resolve().parents[1]


def dust_payload():
    report = json.loads((ROOT / 'tests/fixtures/dust/report.json').read_text(encoding='utf-8'))
    return {'conversation': {'sId': 'test-conversation', 'content': [[
        {'type': 'agent', 'configuration': {'sId': 'McsricPkF8'},
         'status': 'succeeded', 'error': None, 'content': json.dumps(report)}]]}}


class ClientTests(unittest.TestCase):
    def test_dust_disabled_even_with_key(self):
        with patch.dict(os.environ, {'ENABLE_DUST_CALLS': 'false', 'DUST_API_KEY': 'fake'}):
            with self.assertRaises(RuntimeError):
                research('Transports')

    def test_dust_mock_transport_and_agent_configuration(self):
        def handler(request):
            self.assertEqual(request.url.host, 'dust.tt')
            body = json.loads(request.content)
            self.assertTrue(body['blocking'])
            self.assertFalse(body['skipToolsValidation'])
            self.assertEqual(body['message']['mentions'], [{'configurationId': 'McsricPkF8'}])
            return httpx.Response(200, json=dust_payload())
        with patch.dict(os.environ, {'ENABLE_DUST_CALLS': 'true', 'DUST_API_KEY': 'fake-test-only',
                                     'DUST_WORKSPACE_ID': 'E1CnnabqLA', 'DUST_AGENT_ID': 'McsricPkF8'}):
            result = research('Transports', transport=httpx.MockTransport(handler))
        self.assertEqual(result.conversation_id, 'test-conversation')

    def test_dust_wrong_agent_and_pending_status_rejected(self):
        with self.assertRaises(ValueError):
            parse_response(dust_payload(), 'wrong-agent')
        payload = dust_payload()
        payload['conversation']['content'][0][0]['status'] = 'created'
        with self.assertRaises(ValueError):
            parse_response(payload, 'McsricPkF8')

    def test_dust_invalid_json_contract_rejected(self):
        payload = dust_payload()
        payload['conversation']['content'][0][0]['content'] = '{}'
        with self.assertRaises(ValueError):
            parse_response(payload, 'McsricPkF8')

    def test_pipelex_disabled_before_network(self):
        request = json.loads((ROOT / 'tests/fixtures/political_watch/modified/inputs.json').read_text(encoding='utf-8'))['request']
        with patch.dict(os.environ, {'ENABLE_PIPELEX_CALLS': 'false'}):
            with self.assertRaises(RuntimeError):
                asyncio.run(compare_document(ComparisonRequest.model_validate(request)))

    def test_pipelex_mock_preserves_run_metadata_and_contract(self):
        request = json.loads((ROOT / 'tests/fixtures/political_watch/modified/inputs.json').read_text(encoding='utf-8'))['request']
        report = json.loads((ROOT / 'tests/fixtures/political_watch/modified/expected.json').read_text(encoding='utf-8'))
        results = RunResults(pipeline_run_id='offline-test', main_stuff=report)
        outer = self

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def start_and_wait(self, **kwargs):
                outer.assertEqual(kwargs['pipe_code'], 'political_watch.compare_document')
                outer.assertEqual(kwargs['inputs']['request']['document_id'], request['document_id'])
                outer.assertEqual(kwargs['mthds_contents'], method_contents())
                return results

        with patch('backend.pipelex_comparison.pipelex_client', return_value=FakeClient()):
            result = asyncio.run(compare_document(ComparisonRequest.model_validate(request)))
        self.assertIs(result.results, results)
        self.assertEqual(result.output.change_type, 'modified')
