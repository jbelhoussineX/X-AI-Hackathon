import unittest
from unittest.mock import patch

import httpx

from backend.data_sources.senate_documents import collect_dossiers, text_links
from backend.source_verification import FetchedSource, fetch_text
from time import monotonic

D = 'https://www.senat.fr/dossier-legislatif/test.html'
T = 'https://www.senat.fr/leg/ppl25-941.html'


class SenateDocumentsTests(unittest.TestCase):
    def test_main_content_excludes_navigation_and_keeps_only_main_links(self):
        html = ('<nav>NAVIGATION<a href="/leg/ppl20-1.html">ancien</a></nav>'
                '<main><h1>Titre</h1><p>Disposition réelle.</p><script>FAUX</script>'
                '<a href="/leg/ppl25-941.html">Texte</a></main><footer>PIED</footer>')
        with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(
                200, text=html, headers={'content-type': 'text/html'}))) as client:
            source = fetch_text(client, D, monotonic() + 5)
        self.assertIn('Disposition réelle.', source.text)
        for word in ['NAVIGATION', 'PIED', 'FAUX']:
            self.assertNotIn(word, source.text)
        self.assertEqual(source.links, [T])

    def test_no_main_preserves_older_html(self):
        with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(
                200, text='<p>Ancien texte.</p>', headers={'content-type': 'text/html'}))) as client:
            self.assertIn('Ancien texte.', fetch_text(client, T, monotonic() + 5).text)

    def test_versions_distinct_and_pdf_duplicate_collapsed(self):
        pdf = T.replace('.html', '.pdf')
        adopted = 'https://www.senat.fr/leg/tas25-20.html'
        self.assertEqual(text_links([pdf, T, T + '#article1', adopted]), [T, adopted])
        self.assertEqual(text_links([pdf]), [pdf])

    def test_unrelated_links_not_followed(self):
        self.assertEqual(text_links(['https://evil.invalid/leg/ppl25-1.html',
                                     'https://www.senat.fr/rap/r25-1/r25-1.html',
                                     'https://www.senat.fr/leg/ppl25-1.html?redirect=evil',
                                     'https://www.senat.fr/leg/exposes-des-motifs/ppl25-1-expose.html']), [])

    def test_traversal_preserves_parent_and_exact_text(self):
        calls = []
        def handler(request):
            calls.append(str(request.url))
            body = ('<nav>irrelevant</nav><main>Dossier <a href="/leg/ppl25-941.html">texte</a></main>'
                    if str(request.url) == D else '<main><p>Article 1. Exemple fictif.</p></main>')
            return httpx.Response(200, text=body, headers={'content-type': 'text/html'})
        corpus, links, _ = collect_dossiers([D, D], transport=httpx.MockTransport(handler))
        self.assertEqual(calls, [D, T])
        self.assertEqual(corpus[1]['dossier_urls'], [D])
        self.assertEqual(corpus[1]['source_role'], 'legislative_text')
        self.assertIn('Article 1. Exemple fictif.', corpus[1]['text'])
        self.assertEqual(len(corpus[1]['content_sha256']), 64)
        self.assertEqual(links[0]['status'], 'included')

    def test_dossier_without_links_does_not_invent_text_url(self):
        calls = []
        def handler(request):
            calls.append(str(request.url))
            return httpx.Response(200, text='<main>Dossier vide</main>', headers={'content-type': 'text/html'})
        corpus, links, limits = collect_dossiers([D], transport=httpx.MockTransport(handler))
        self.assertEqual(calls, [D])
        self.assertEqual(links, [])
        self.assertEqual(len(corpus), 1)
        self.assertTrue(any('Aucun lien' in s for s in limits))

    def test_html_indentation_does_not_hide_content_before_truncation(self):
        with patch('backend.data_sources.senate_documents.fetch_text',
                   return_value=FetchedSource('retrieved', ' ' * 20000 + 'Article 1. Exemple.', D)):
            corpus, _, _ = collect_dossiers([D])
        self.assertEqual(corpus[0]['text'], 'Article 1. Exemple.')
        self.assertFalse(corpus[0]['truncated'])

    def test_unavailable_text_is_recorded_not_replaced(self):
        def handler(request):
            if str(request.url) == D:
                return httpx.Response(200, text='<main><a href="/leg/ppl25-941.html">Texte</a></main>',
                                      headers={'content-type': 'text/html'})
            return httpx.Response(403)
        corpus, links, _ = collect_dossiers([D], transport=httpx.MockTransport(handler))
        self.assertEqual(len(corpus), 1)
        self.assertEqual(links[0]['status'], 'http_error')

    def test_pdf_boundaries_and_truncation_remain_explicit(self):
        pdf = T.replace('.html', '.pdf')
        def fetch(_, url, deadline):
            return (FetchedSource('retrieved', 'Dossier', D, links=[pdf]) if url == D else
                    FetchedSource('retrieved', '', pdf, pages=['A' * 8000, 'B' * 8000]))
        with patch('backend.data_sources.senate_documents.fetch_text', side_effect=fetch):
            corpus, _, limits = collect_dossiers([D])
        self.assertEqual([len(p) for p in corpus[1]['pdf_pages']], [8000, 4000])
        self.assertTrue(corpus[1]['truncated'])
        self.assertTrue(any('tronqué' in s for s in limits))

    def test_link_count_limit_and_external_dossier_before_network(self):
        def fetch(_, url, deadline):
            return FetchedSource('retrieved', 'Texte', url,
                                 links=[f'https://www.senat.fr/leg/ppl25-{i}.html' for i in range(3)])
        with patch('backend.data_sources.senate_documents.fetch_text', side_effect=fetch) as mocked:
            _, links, _ = collect_dossiers([D, 'https://evil.invalid/dossier-legislatif/a.html'])
        self.assertEqual(mocked.call_count, 3)
        self.assertEqual([x['status'] for x in links], ['included', 'included', 'not_attempted'])
