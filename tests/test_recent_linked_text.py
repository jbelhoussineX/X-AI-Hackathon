"""Read an observed legislative text, without following arbitrary or recursive links."""
import httpx
import pytest

from backend.data_sources.pages import collect_sources
from backend.recent_brief import prepare, verify
from backend.generated.recent_brief.models import Brief
from backend.agent_models import AssessedItem
from test_recent_agent import result

DOSSIER = 'https://www.assemblee-nationale.fr/dyn/17/dossiers/DLR5L17N12345'
TEXT_URL = 'https://www.assemblee-nationale.fr/dyn/opendata/PIONANR5L17B00941.html'
MEASURE = 'Article 1. Dans cette fixture fictive, les communes doivent publier un bilan annuel des logements adaptés.'


def transport(calls, *, unavailable=False):
    def handler(request):
        url = str(request.url)
        calls.append(url)
        if url == DOSSIER:
            return httpx.Response(200, headers={'content-type': 'text/html'}, text=f'<main>Proposition fictive déposée : suivi de la procédure.'
                                  f'<a href="https://example.test/texte">Lien externe</a>'
                                  f'<a href="{TEXT_URL}">Texte de la proposition</a></main>')
        if url == TEXT_URL:
            if unavailable:
                return httpx.Response(503)
            return httpx.Response(200, headers={'content-type': 'text/html'}, text=f'<main>{MEASURE}'
                                  '<a href="https://www.senat.fr/leg/ppl25-999.html">Un autre texte</a></main>')
        raise AssertionError('Unexpected external or recursive fetch')
    return httpx.MockTransport(handler)


def test_semantic_corpus_explains_the_observed_text_with_its_own_quote_url():
    calls = []
    report = result()
    report['events'][0].pop('content_passages')
    report['events'][0]['dossier_url'] = DOSSIER
    corpus = prepare(report, semantic=True, transport=transport(calls))
    assert calls == [DOSSIER, TEXT_URL]
    source = corpus['sources'][0]
    assert MEASURE in source['text']
    assert source['url'] == TEXT_URL and source['dossier_url'] == DOSSIER
    assert source['source_role'] == 'linked_legislative_text'
    brief = Brief(items=[dict(source_id=source['source_id'], quote_id=source['quotes'][0]['quote_id'],
                              summary='Le texte fictif impose aux communes de publier un bilan annuel.')], limitations=[])
    checked = verify(brief, corpus)['items'][0]
    assert checked['excerpt'] in source['text'] and checked['url'] == TEXT_URL


def test_missing_linked_text_preserves_the_notice_without_invented_content():
    calls = []
    report = result()
    report['events'][0].pop('content_passages')
    report['events'][0]['dossier_url'] = DOSSIER
    corpus = prepare(report, semantic=True, transport=transport(calls, unavailable=True))
    assert calls == [DOSSIER, TEXT_URL]
    assert corpus['sources'][0]['url'] == DOSSIER
    assert MEASURE not in corpus['sources'][0]['text']
    assert any('Page non exploitable' in entry for entry in corpus['limitations'])


def test_legacy_collector_does_not_follow_text_links_implicitly():
    calls = []
    collect_sources([DOSSIER], transport=transport(calls))
    assert calls == [DOSSIER]


@pytest.mark.parametrize('length', [599, 600, 601])
def test_summary_length_is_enforced_without_truncating_sentences(length):
    item = dict(source_id='f0', quote_id='q0', summary='é' * length, uncertainty='Texte fictif.')
    if length > 600:
        with pytest.raises(ValueError):
            AssessedItem.model_validate(item)
    else:
        assert len(AssessedItem.model_validate(item).summary) == length
