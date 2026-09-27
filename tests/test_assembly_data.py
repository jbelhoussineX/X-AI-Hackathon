import io
import json
import unittest
from unittest.mock import patch
import zipfile

import httpx

from backend.data_sources.assembly import parse_archive, select, fetch_dataset
from backend.data_sources.official import prepare, fetched_corpus


def archive_bytes(**changes):
    doc = {'uid': 'PIONANR5L17B1234', 'legislature': '17',
           'denominationStructurelle': 'Proposition de loi',
           'titres': {'titrePrincipal': 'Proposition de loi logement fictive'},
           'cycleDeVie': {'chrono': {'dateDepot': '2026-01-10T00:00:00+01:00',
                                     'datePublication': None, 'datePublicationWeb': '2026-01-11T10:00:00+01:00'}},
           'dossierRef': 'DLR5L17N12345'}
    doc.update(changes)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('json/document/PIONANR5L17B1234.json', json.dumps({'document': doc}))
    return buf.getvalue()


class AssemblyDataTests(unittest.TestCase):
    def test_dates_are_distinct_and_uid_preserved(self):
        r = parse_archive(archive_bytes())[0]
        self.assertEqual(r.initial_date, '2026-01-10')
        self.assertIsNone(r.publication_date)
        self.assertEqual(r.web_publication_date, '2026-01-11')
        self.assertTrue(r.document_url.endswith('/PIONANR5L17B1234.html'))
        self.assertEqual(len(select([r], 'logement', '2026-01-01', '2026-12-31')), 1)

    def test_other_legislature_and_resolution_not_mislabeled(self):
        for changes in [{'legislature': '16'}, {'denominationStructurelle': 'Proposition de résolution'}]:
            with self.assertRaises(ValueError):
                parse_archive(archive_bytes(**changes))

    def test_archive_limits_and_invalid_reference(self):
        with patch('backend.data_sources.assembly.MAX_UNPACKED', 10), self.assertRaises(ValueError):
            parse_archive(archive_bytes())
        with self.assertRaises(ValueError):
            parse_archive(archive_bytes(dossierRef='../../evil'))
        with self.assertRaises(zipfile.BadZipFile):
            parse_archive(b'not a ZIP')

    def test_download_not_retried_or_redirected(self):
        seen = []
        def handler(request):
            seen.append(request.url)
            return httpx.Response(302, headers={'location': 'https://evil.invalid'})
        with self.assertRaises(ValueError):
            fetch_dataset(transport=httpx.MockTransport(handler))
        self.assertEqual(len(seen), 1)

    def test_inventory_failure_is_explicit_and_no_inference(self):
        with patch('backend.data_sources.official.senate.fetch_dataset', side_effect=ValueError('failure')), \
             patch('backend.data_sources.official.assembly.inventory', side_effect=ValueError('failure')):
            result = prepare('logement', '2026-01-01', '2026-12-31')
        self.assertEqual(result['corpus'], [])
        self.assertIsNone(result['pipelex_inputs'])
        self.assertEqual([d['status'] for d in result['datasets']], ['unavailable', 'unavailable'])

    def test_cached_verification_uses_only_supplied_text(self):
        corpus = [{'url': 'https://www.senat.fr/a', 'final_url': 'https://www.senat.fr/b',
                   'text': 'Exact body', 'pdf_pages': None}]
        cached = fetched_corpus(corpus)
        self.assertEqual(cached[corpus[0]['url']].text, 'Exact body')
        self.assertIs(cached[corpus[0]['url']], cached[corpus[0]['final_url']])
