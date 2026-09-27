import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.dust.client import DustResult
from frontend.interface_b import appeler_service_a, verifier_sortie
from src.service import search

ROOT = Path(__file__).resolve().parents[1]


class FrontendContractTests(unittest.TestCase):
    def report(self):
        return json.loads((ROOT / 'tests/fixtures/dust/report.json').read_text(encoding='utf-8'))

    def test_frontend_calls_real_service_with_mocked_dust(self):
        with patch('src.service.research', return_value=DustResult(self.report(), 'fake')) as provider:
            result = appeler_service_a({'topic': 'Transports', 'start': '2026-01-01', 'end': '2026-12-31'})
        self.assertEqual(verifier_sortie(result, 'dust')['mode'], 'dust')
        provider.assert_called_once_with('Transports', start='2026-01-01', end='2026-12-31')

    def test_outside_date_range_is_removed(self):
        report = self.report()
        report['documents'][0]['publication_date'] = '2025-12-31'
        with patch('src.service.research', return_value=DustResult(report, 'fake')):
            result = search('Transports', '2026-01-01', '2026-12-31')
        self.assertEqual(result['report']['documents'], [])
        self.assertTrue(result['report']['limitations'])
        verifier_sortie(result, 'dust')

    def test_invalid_period_fails_before_provider(self):
        with patch('src.service.research') as provider:
            with self.assertRaises(ValueError):
                search('Transports', '2026-12-31', '2026-01-01')
            provider.assert_not_called()

    def test_real_mode_disabled_and_error_redacted(self):
        with patch.dict(os.environ, {'ENABLE_DUST_CALLS': 'false'}):
            with self.assertRaises(ValueError) as context:
                appeler_service_a({'topic': 'Transports', 'start': '2026-01-01', 'end': '2026-12-31'})
        self.assertNotIn('API_KEY', str(context.exception))


class StreamlitDemoTests(unittest.TestCase):
    def test_existing_page_opens_and_submits_demo_without_network(self):
        try:
            from streamlit.testing.v1 import AppTest
        except ImportError:
            self.skipTest('Install requirements-ui.txt for Streamlit UI checks.')
        # Catch any accidental external call while interacting with the existing page.
        with patch('httpx.Client.send', side_effect=AssertionError('Network forbidden')), \
             patch('src.service.research', side_effect=AssertionError('Dust forbidden')):
            app = AppTest.from_file(str(ROOT / 'frontend/interface_b.py')).run()
            self.assertEqual(len(app.exception), 0)
            app.text_input(key='b_topic').set_value('Accessibilité des transports')
            app.button[0].click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertIsNotNone(app.session_state['b_last'])
            self.assertEqual(app.session_state['b_last']['result']['mode'], 'demo')
