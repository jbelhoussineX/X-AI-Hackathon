import csv
import io
import json
import unittest
from unittest.mock import patch

import httpx

from backend.data_sources.senate import DATASET_URL, fetch_dataset, parse_csv, prepare, select


def csv_bytes(**changes):
    row = {'Titre': 'proposition de loi fictive sur le logement étudiant',
           'Type de dossier': 'proposition de loi', 'Date initiale': '02/09/2026',
           'URL du dossier': 'http://www.senat.fr/dossier-legislatif/test-fictif.html',
           'État du dossier': 'première lecture', 'Date de promulgation': '',
           'Numéro de la loi': '', 'Thèmes': 'Logement et urbanisme, Éducation'}
    row.update(changes)
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=list(row), delimiter=';')
    writer.writeheader()
    writer.writerow(row)
    return out.getvalue().encode('cp1252')


class SenateDataTests(unittest.TestCase):
    def test_encoding_dates_provenance_and_https(self):
        record = parse_csv(csv_bytes())[0]
        self.assertIn('étudiant', record.title)
        self.assertEqual(record.initial_date, '2026-09-02')
        self.assertIsNone(record.promulgation_date)
        self.assertTrue(record.original_url.startswith('http:'))
        self.assertTrue(record.dossier_url.startswith('https:'))
        self.assertEqual(record.kind, 'proposition_de_loi')

    def test_utf8_supported(self):
        data = csv_bytes().decode('cp1252').encode('utf-8-sig')
        self.assertEqual(parse_csv(data), parse_csv(csv_bytes()))

    def test_resolutions_excluded(self):
        self.assertEqual(parse_csv(csv_bytes(**{'Type de dossier': 'proposition de résolution'})), [])

    def test_invalid_columns_dates_and_urls_fail_closed(self):
        bad = [b'Title;URL\nx;y\n', csv_bytes(**{'Date initiale': '31/02/2026'}),
               csv_bytes(**{'URL du dossier': 'https://senat.fr.evil.org/dossier-legislatif/x.html'})]
        for data in bad:
            with self.subTest(data=data[:30]), self.assertRaises(ValueError):
                parse_csv(data)

    def test_lexical_search_all_terms_dates_and_themes(self):
        rows = parse_csv(csv_bytes())
        self.assertEqual(len(select(rows, 'education logement', '2026-01-01', '2026-12-31')), 1)
        self.assertEqual(select(rows, 'logement energie', '2026-01-01', '2026-12-31'), [])
        self.assertEqual(select(rows, 'logement', '2025-01-01', '2025-12-31'), [])
        with self.assertRaises(ValueError):
            select(rows, 'le et', '2026-01-01', '2026-12-31')

    def test_unknown_initial_date_not_guessed(self):
        rows = parse_csv(csv_bytes(**{'Date initiale': ''}))
        self.assertIsNone(rows[0].initial_date)
        self.assertEqual(select(rows, 'logement', '2026-01-01', '2026-12-31'), [])

    def test_exact_duplicates_deduplicated_but_conflicting_rows_rejected(self):
        data = csv_bytes()
        line = data.splitlines(keepends=True)[1]
        self.assertEqual(len(parse_csv(data + line)), 1)
        changed_line = csv_bytes(**{'État du dossier': 'promulgué'}).splitlines(keepends=True)[1]
        with self.assertRaises(ValueError):
            parse_csv(data + changed_line)

    def test_http_download_hash_and_limit(self):
        transport = httpx.MockTransport(lambda _: httpx.Response(200, content=csv_bytes(), headers={'content-type': 'text/csv'}))
        payload, provenance = fetch_dataset(transport=transport)
        self.assertEqual(payload, csv_bytes())
        self.assertEqual(provenance['source_url'], DATASET_URL)
        self.assertEqual(len(provenance['sha256']), 64)
        with patch('backend.data_sources.senate.MAX_BYTES', 10), self.assertRaises(ValueError):
            fetch_dataset(transport=transport)

    def test_http_errors_and_redirects_not_followed(self):
        for status in [302, 403, 429, 500]:
            calls = []
            def handler(request):
                calls.append(request.url)
                return httpx.Response(status, headers={'location': 'https://evil.invalid'})
            with self.subTest(status=status), self.assertRaises(ValueError):
                fetch_dataset(transport=httpx.MockTransport(handler))
            self.assertEqual(len(calls), 1)

    def test_prepare_reads_pages_but_never_calls_pipelex(self):
        calls = []
        def handler(request):
            calls.append(str(request.url))
            if str(request.url) == DATASET_URL:
                return httpx.Response(200, content=csv_bytes(), headers={'content-type': 'text/csv'})
            return httpx.Response(200, text='<p>Texte fictif pour les tests.</p>', headers={'content-type': 'text/html'})
        with patch('src.openai_research._make_client', side_effect=AssertionError('No inference')):
            result = prepare('logement', '2026-01-01', '2026-12-31', fetch_pages=True,
                             transport=httpx.MockTransport(handler))
        self.assertEqual(len(calls), 2)
        corpus = json.loads(result['pipelex_inputs']['request']['corpus_json'])
        self.assertIn('Texte fictif', corpus[0]['text'])
        self.assertNotIn('première lecture', result['pipelex_inputs']['request']['corpus_json'])

    def test_no_page_or_no_result_gives_no_model_input(self):
        def handler(request):
            return (httpx.Response(200, content=csv_bytes(), headers={'content-type': 'text/csv'})
                    if str(request.url) == DATASET_URL else httpx.Response(403))
        result = prepare('logement', '2026-01-01', '2026-12-31', fetch_pages=True,
                         transport=httpx.MockTransport(handler))
        self.assertIsNone(result['pipelex_inputs'])

    def test_invalid_request_before_network(self):
        with patch('backend.data_sources.senate.fetch_dataset') as fetch, self.assertRaises(ValueError):
            prepare('logement', '2026-12-31', '2026-01-01')
        fetch.assert_not_called()
