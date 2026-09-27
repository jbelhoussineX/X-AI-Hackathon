from copy import deepcopy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx
from backend.source_verification import allowed_url, verify_sources
from src.service import search


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.report = json.loads((Path(__file__).parent / 'fixtures/dust/report.json').read_text(encoding='utf-8'))
        self.url = 'https://www.assemblee-nationale.fr/dyn/test'
        for e in self.report['documents'][0]['evidence']:
            e['url'] = self.url
        self.html = '<p>La consultation se termine le 20 octobre 2026.</p><p>Le texte a été déposé.</p>'

    def verify(self, handler):
        return verify_sources(self.report, transport=httpx.MockTransport(handler))

    def test_match_and_same_url_only_fetched_once(self):
        calls = []
        before = deepcopy(self.report)
        def handler(request):
            calls.append(request)
            return httpx.Response(200, text=self.html, headers={'content-type': 'text/html; charset=utf-8'})
        result = self.verify(handler)
        self.assertTrue(result.all_matched)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.report, before)
        self.assertEqual(result.report['documents'][0]['evidence'], before['documents'][0]['evidence'])

    def test_whitespace_only_normalization(self):
        result = self.verify(lambda _: httpx.Response(200, text=self.html.replace('le 20', 'le\n 20'), headers={'content-type': 'text/html'}))
        self.assertEqual(result.checks[0]['status'], 'matched_whitespace')

    def test_script_content_is_not_evidence(self):
        result = self.verify(lambda _: httpx.Response(200, text='<script>'+self.html+'</script><p>Autre texte</p>', headers={'content-type': 'text/html'}))
        self.assertFalse(result.all_matched)
        self.assertEqual(result.checks[0]['status'], 'not_found')

    def test_changed_number_is_not_a_match(self):
        result = self.verify(lambda _: httpx.Response(200, text=self.html.replace('20 octobre', '21 octobre'), headers={'content-type': 'text/html'}))
        self.assertEqual(result.checks[0]['status'], 'not_found')

    def test_untrusted_redirect_never_followed(self):
        calls = []
        def handler(request):
            calls.append(str(request.url))
            return httpx.Response(302, headers={'location': 'http://127.0.0.1/admin'})
        result = self.verify(handler)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result.checks[0]['status'], 'domain_not_allowed')

    def test_domain_checks(self):
        for url in ('https://www.senat.fr.evil.org/x', 'https://evil.org/?www.senat.fr',
                    'https://user:password@www.senat.fr/x', 'http://www.senat.fr/x',
                    'https://www.senat.fr:8080/x', 'https://127.0.0.1/x'):
            self.assertFalse(allowed_url(url), url)
        self.assertTrue(allowed_url('https://www.senat.fr/dossier-legislatif/test.html'))

    def test_invalid_pdf_and_http_errors_not_claimed_verified(self):
        for response, expected in [(httpx.Response(200, content=b'%PDF', headers={'content-type':'application/pdf'}), 'invalid_pdf'),
                                   (httpx.Response(403), 'http_error')]:
            result = self.verify(lambda _: response)
            self.assertEqual(result.checks[0]['status'], expected)
            self.assertFalse(result.all_matched)

    def test_large_page_stops(self):
        with patch('backend.source_verification.MAX_BYTES', 10):
            result = self.verify(lambda _: httpx.Response(200, text=self.html, headers={'content-type':'text/html'}))
        self.assertEqual(result.checks[0]['status'], 'too_large')

    def test_timeout_preserves_report_and_marks_uncertainty(self):
        def handler(request):
            raise httpx.ReadTimeout('do not expose', request=request)
        result = self.verify(handler)
        self.assertEqual(result.checks[0]['status'], 'unavailable')
        self.assertTrue(result.report['documents'][0]['uncertainties'])
        self.assertNotIn('do not expose', str(result.report))

    def test_invalid_research_report_is_not_replaced_with_demo(self):
        with patch.dict(os.environ, {'ENABLE_PIPELEX_CALLS': 'true'}), \
             patch('src.service.research', side_effect=ValueError('Source non confirmee')):
            with self.assertRaises(ValueError):
                search('Transports', '2026-01-01', '2026-12-31')
