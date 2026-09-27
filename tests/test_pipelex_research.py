"""No hosted inference or real network calls: exercise the entire new boundary."""
import asyncio
from copy import deepcopy
import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from backend.generated.political_search.models import SearchRequest, SearchResult
from backend.generated.political_report.models import Report, ReportRequest
from backend.pipelex_research import collect_sources, research
from backend.pipelex_search import find_sources
from backend.pipelex_report import build_report
from backend.source_verification import FetchedSource, verify_sources
from frontend.interface_b import verifier_sortie
from src.service import search

URL = 'https://www.senat.fr/leg/exemple-fictif.html'
TEXT = 'Dans ce texte fictif, une aide aux transports est proposée sous conditions de ressources.'


def report():
    return {'schema_version': '1.0', 'topic': 'Transports', 'scope': 'Corpus fictif de test.',
            'documents': [{'id': 'test1', 'title': 'Proposition fictive', 'kind': 'proposition_de_loi',
                           'publication_date': '2026-09-01', 'summary': 'Une aide fictive est proposée.',
                           'stage': None, 'stage_date': None,
                           'evidence': [{'purpose': 'contenu', 'url': URL, 'excerpt': TEXT, 'location': None}],
                           'uncertainties': ['Exemple de test inventé.']}],
            'contacts': [], 'limitations': ['Test local, aucune recherche réelle.']}


def search_output(urls=None):
    return SearchResult.model_validate({'answer': 'INVENTED_ANSWER', 'sources': [
        {'url': url, 'title': 'INVENTED_TITLE', 'snippet': 'INVENTED_SNIPPET'}
        for url in (urls if urls is not None else [URL])]})


class PipelexResearchTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'ENABLE_PIPELEX_CALLS': 'true', 'POLITICAL_DATA_SOURCE': 'web', 'PIPELEX_EXECUTION_MODE': 'hosted'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.transport = httpx.MockTransport(lambda _: httpx.Response(
            200, text=f'<article>{TEXT}</article>', headers={'content-type': 'text/html'}))

    def run_research(self, value=None, urls=None):
        search_run = SimpleNamespace(output=search_output(urls), results='search metadata')
        report_run = SimpleNamespace(results=SimpleNamespace(main_stuff=value if value is not None else report()))
        with patch('backend.pipelex_research.find_sources', new=AsyncMock(return_value=search_run)), \
             patch('backend.pipelex_research.build_report', new=AsyncMock(return_value=report_run)) as build:
            result = research('Transports', start='2026-01-01', end='2026-12-31', transport=self.transport)
        return result, build

    def test_full_chain_preserves_contract_and_uses_only_retrieved_text(self):
        result, build = self.run_research()
        self.assertEqual(result.checks[0]['status'], 'matched')
        corpus = build.call_args.args[0].corpus_json
        self.assertIn(TEXT, corpus)
        self.assertNotIn('INVENTED_', corpus)
        self.assertEqual(len(result.runs), 2)
        with patch('src.service.research', return_value=result):
            output = search('Transports', '2026-01-01', '2026-12-31', mode='pipelex')
        verifier_sortie(output, 'pipelex')

    def test_empty_search_skips_second_inference(self):
        result, build = self.run_research(urls=[])
        build.assert_not_called()
        self.assertEqual(result.report['documents'], [])

    def test_citation_can_use_the_verified_redirect_destination(self):
        destination = 'https://www.senat.fr/leg/redirected-fictif.html'
        with patch('backend.pipelex_research.fetch_text', return_value=FetchedSource(
                'retrieved', TEXT, destination)):
            _, fetched, _ = collect_sources(search_output())
        redirected = report()
        redirected['documents'][0]['evidence'][0]['url'] = destination
        self.assertTrue(verify_sources(redirected, fetched_sources=fetched).all_matched)

    def test_unreadable_pages_do_not_use_snippets(self):
        self.transport = httpx.MockTransport(lambda _: httpx.Response(403))
        result, build = self.run_research()
        build.assert_not_called()
        self.assertIn('http_error', ' '.join(result.report['limitations']))

    def test_wrong_domain_and_redirect_are_blocked(self):
        calls = []
        def response(request):
            calls.append(str(request.url))
            return httpx.Response(302, headers={'location': 'https://evil.invalid/page'})
        corpus, _, _ = collect_sources(search_output(['https://evil.invalid/page', URL]),
                                       transport=httpx.MockTransport(response))
        self.assertEqual(corpus, [])
        self.assertEqual(calls, [URL])

    def test_fabricated_quote_or_unread_url_rejects_report_without_network(self):
        for key, value in [('excerpt', 'INVENTED_SNIPPET'), ('url', 'https://www.senat.fr/unread')]:
            with self.subTest(key=key):
                invalid = report()
                invalid['documents'][0]['evidence'][0][key] = value
                with self.assertRaises(ValueError):
                    self.run_research(invalid)

    def test_extra_fields_and_unproven_status_rejected(self):
        for edit in ('extra', 'status', 'date', 'topic'):
            invalid = report()
            if edit == 'extra':
                invalid['documents'][0]['invented_field'] = True
            elif edit == 'status':
                invalid['documents'][0]['stage'] = 'Promulgué'
            elif edit == 'date':
                invalid['documents'][0]['stage_date'] = '2026-01-01'
            else:
                invalid['topic'] = 'Autre sujet'
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                self.run_research(invalid)

    def test_empty_generated_report_is_honest(self):
        empty = report()
        empty['documents'] = []
        result, _ = self.run_research(empty)
        self.assertEqual(result.checks, [])
        self.assertEqual(result.report['documents'], [])

    def test_truncation_bounds_verification_to_supplied_text(self):
        with patch('backend.pipelex_research.MAX_SOURCE_CHARS', 20):
            corpus, fetched, limits = collect_sources(search_output(), transport=self.transport)
        self.assertEqual(len(corpus[0]['text']), 20)
        self.assertTrue(corpus[0]['truncated'])
        self.assertTrue(any('tronqué' in s for s in limits))
        verified = verify_sources(report(), fetched_sources=fetched)
        self.assertFalse(verified.all_matched)

    def test_pdf_pages_preserved_and_quote_cannot_cross_pages(self):
        with patch('backend.pipelex_research.fetch_text', return_value=FetchedSource(
                'retrieved', '', URL, ['Début du passage', 'fin du passage'])):
            corpus, fetched, _ = collect_sources(search_output())
        self.assertEqual(corpus[0]['pdf_pages'], ['Début du passage', 'fin du passage'])
        invalid = report()
        invalid['documents'][0]['evidence'][0]['excerpt'] = 'passage fin'
        self.assertFalse(verify_sources(invalid, fetched_sources=fetched).all_matched)

    def test_disabled_fails_before_search_or_fetch(self):
        with patch.dict(os.environ, {'ENABLE_PIPELEX_CALLS': 'false'}), \
             patch('backend.pipelex_research.find_sources') as find:
            with self.assertRaises(RuntimeError):
                research('Transports', start='2026-01-01', end='2026-12-31')
        find.assert_not_called()

    def test_generated_types_and_sdk_calls_match_validated_signatures(self):
        Report.model_validate(report())
        for function, module, request, output, pipe in [
            (find_sources, 'backend.pipelex_search', SearchRequest(topic='Transports', start='2026-01-01', end='2026-12-31'), search_output().model_dump(), 'political_search.find_sources'),
            (build_report, 'backend.pipelex_report', ReportRequest(topic='Transports', start='2026-01-01', end='2026-12-31', corpus_json='[]'), report(), 'political_report.build_report')]:
            client = AsyncMock()
            client.__aenter__.return_value = client
            client.start_and_wait.return_value = SimpleNamespace(main_stuff=output)
            with patch(module + '.pipelex_client', return_value=client):
                run = asyncio.run(function(request))
            self.assertEqual(client.start_and_wait.call_args.kwargs['pipe_code'], pipe)
            self.assertEqual(client.start_and_wait.call_args.kwargs['inputs'], {'request': request.model_dump()})
            self.assertEqual(run.results.main_stuff, output)

    def test_source_checks_are_remapped_after_date_filter(self):
        result, _ = self.run_research()
        second = deepcopy(result.report['documents'][0])
        second['id'] = 'test2'
        result.report['documents'][0]['publication_date'] = '2025-01-01'
        result.report['documents'].append(second)
        result.checks.append(dict(result.checks[0], entity_index=1))
        with patch('src.service.research', return_value=result):
            output = search('Transports', '2026-01-01', '2026-12-31', mode='pipelex')
        self.assertEqual(len(output['source_checks']), 1)
        self.assertEqual(output['source_checks'][0]['entity_index'], 0)
        self.assertEqual(output['report']['documents'][0]['id'], 'test2')
