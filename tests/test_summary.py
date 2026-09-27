import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from backend.summary_service import prepare_summary, synthesize_report, validate_summary
from backend.pipelex_summary import summarize_interest
from backend.generated.political_summary.models import SummaryRequest
from frontend.interface_b import verifier_sortie
from backend.pipelex_research import ResearchResult
from src.service import search
from backend.source_verification import SourceVerification

ROOT = Path(__file__).resolve().parents[1]


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.report = json.loads((ROOT / 'tests/fixtures/dust/report.json').read_text(encoding='utf-8'))
        self.output = {'documents': [{
            'document_id': self.report['documents'][0]['id'],
            'explanation': {'text': 'Cet exemple fictif indique une clôture le 20 octobre 2026.', 'evidence_ids': ['e1']},
            'relevance': {'text': 'Le lien avec le logement étudiant reste à confirmer dans ces extraits fictifs.', 'evidence_ids': ['e1']},
            'limitations': ['Exemple fictif rédigé à la main ; aucune génération Pipelex.'],
        }]}

    def test_metadata_sources_contacts_and_limits_preserved(self):
        original = deepcopy(self.report)
        result = synthesize_report('Logement étudiant', self.report, lambda _: self.output)
        self.assertEqual(self.report, original)
        for key in ('scope', 'contacts', 'topic'):
            self.assertEqual(result[key], original[key])
        for key in ('id', 'title', 'kind', 'publication_date', 'stage', 'stage_date', 'evidence'):
            self.assertEqual(result['documents'][0][key], original['documents'][0][key])
        self.assertTrue(set(original['limitations']) <= set(result['limitations']))
        self.assertIn('Lien avec le sujet', result['documents'][0]['summary'])
        verifier_sortie({'mode': 'pipelex', 'report': result, 'duration_seconds': 0}, 'pipelex')

    def test_request_uses_explicit_interest_not_generated_topic(self):
        request = prepare_summary('Logement étudiant', self.report)
        self.assertEqual(request['topic'], 'Logement étudiant')
        corpus = json.loads(request['corpus_json'])
        self.assertNotIn('summary', corpus['documents'][0])
        self.assertNotIn('contacts', corpus)

    def test_invalid_reference_and_status_reference_refused(self):
        for refs in (['invented'], ['e2'], [], ['e1', 'e1']):
            with self.subTest(refs=refs):
                output = deepcopy(self.output)
                output['documents'][0]['explanation']['evidence_ids'] = refs
                with self.assertRaises(ValueError):
                    validate_summary(self.report, output)

    def test_missing_extra_and_duplicate_documents_refused(self):
        for docs in ([], self.output['documents'] * 2,
                     [dict(self.output['documents'][0], document_id='unknown')]):
            with self.subTest(docs=docs):
                with self.assertRaises(ValueError):
                    validate_summary(self.report, {'documents': docs})

    def test_generated_metadata_cannot_overwrite_dust(self):
        output = deepcopy(self.output)
        output['documents'][0]['stage'] = 'Promulgué'
        with self.assertRaises(ValueError):
            synthesize_report('Transports', self.report, lambda _: output)

    def test_empty_report_does_not_call_model(self):
        report = deepcopy(self.report)
        report['documents'] = []
        report['contacts'] = []
        analyzer = Mock(side_effect=AssertionError('No inference'))
        self.assertEqual(synthesize_report('Transports', report, analyzer), report)
        analyzer.assert_not_called()

    def test_model_failure_propagates_and_preserves_original(self):
        original = deepcopy(self.report)
        with self.assertRaises(RuntimeError):
            synthesize_report('Transports', self.report, Mock(side_effect=RuntimeError('failure')))
        self.assertEqual(self.report, original)

    def test_sdk_disabled_before_network(self):
        request = SummaryRequest.model_validate(prepare_summary('Transports', self.report))
        with patch.dict(os.environ, {'ENABLE_PIPELEX_CALLS': 'false'}):
            with self.assertRaises(RuntimeError):
                asyncio.run(summarize_interest(request))

    def test_service_uses_new_report_without_legacy_synthesis(self):
        with patch.dict(os.environ, {'ENABLE_PIPELEX_CALLS': 'true'}), \
             patch('src.service.research', return_value=ResearchResult(self.report, [])), \
             patch('backend.pipelex_summary.analyze_summary') as analyzer:
            result = search('Logement étudiant', '2026-01-01', '2026-12-31')
        analyzer.assert_not_called()
        verifier_sortie(result, 'pipelex')

    def test_disabled_pipeline_never_calls_research(self):
        with patch.dict(os.environ, {'ENABLE_PIPELEX_CALLS': 'false'}), \
             patch('src.service.research') as provider:
            with self.assertRaises(RuntimeError):
                search('Logement étudiant', '2026-01-01', '2026-12-31')
        provider.assert_not_called()
