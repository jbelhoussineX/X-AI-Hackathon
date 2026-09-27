"""Multi-topic brief regressions using fictional pages and no network calls."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

from backend.generated.recent_brief.models import Brief, Item
from backend.recent_brief import build, prepare, verify


HOUSING = 'Document fictif : le logement fait l’objet d’un débat sur les conditions de location.'
EDUCATION = 'Document fictif : les bourses étudiantes font l’objet d’une nouvelle discussion.'


def collection(topics, texts):
    events, pages = [], []
    for index, text in enumerate(texts):
        url = f'https://www.senat.fr/leg/ppl25-{index:03d}.html'
        events.append({'id': f'fixture-{index}', 'title': f'Document fictif {index}',
                       'category': 'debat', 'event_date': '2026-09-25',
                       'date_kind': 'Date du débat', 'dossier_url': url})
        pages.append({'url': url, 'pdf_pages': text if isinstance(text, list) else [],
                      'text': text if isinstance(text, str) else '',
                      'retrieved_at': '2026-09-27T12:00:00Z'})
    return ({'topic': ' · '.join(topics), 'topics': topics,
             'start': '2026-09-21', 'end': '2026-09-27', 'events': events,
             'collected_at': datetime.now(timezone.utc).isoformat(), 'limitations': []}, pages)


def mock_pages(monkeypatch, pages):
    collector = Mock(return_value=(pages, {}, []))
    monkeypatch.setattr('backend.recent_brief.collect_sources', collector)
    return collector


def test_each_topic_keeps_its_own_event_and_exact_quote(monkeypatch):
    data, pages = collection(['logement', 'bourses'], [HOUSING, EDUCATION])
    mock_pages(monkeypatch, pages)
    corpus = prepare(data)
    assert [source['event_id'] for source in corpus['sources']] == ['fixture-0', 'fixture-1']
    assert [source['text'] for source in corpus['sources']] == [HOUSING, EDUCATION]
    response = Brief(items=[Item(source_id=source['source_id'], quote_id='q0',
                                 summary='Résumé fictif utilisé pour le contrôle.')
                            for source in corpus['sources']], limitations=[])
    verified = verify(response, corpus)
    assert len(verified['items']) == 2
    assert all(item['excerpt'] in item['text'] for item in verified['items'])


def test_pdf_passages_share_the_budget_between_topics(monkeypatch):
    housing_pages = [f'{HOUSING} Numéro de page {index}.' for index in range(4)]
    data, pages = collection(['logement', 'bourses'], [[*housing_pages, EDUCATION]])
    mock_pages(monkeypatch, pages)
    corpus = prepare(data)
    excerpts = [source['text'] for source in corpus['sources']]
    assert len(excerpts) == 3
    assert EDUCATION in excerpts
    assert all(excerpt in [*housing_pages, EDUCATION] for excerpt in excerpts)


def test_shared_passage_is_not_duplicated_for_matching_topics(monkeypatch):
    text = HOUSING + ' ' + EDUCATION
    data, pages = collection(['logement', 'bourses'], [text])
    mock_pages(monkeypatch, pages)
    assert len(prepare(data)['sources']) == 1


def test_old_single_topic_history_is_still_supported(monkeypatch):
    data, pages = collection(['logement'], [HOUSING])
    del data['topics']
    mock_pages(monkeypatch, pages)
    assert prepare(data)['sources'][0]['text'] == HOUSING


def test_multi_topic_corpus_keeps_event_and_passage_limits(monkeypatch):
    data, pages = collection(['logement', 'bourses'],
                             [[HOUSING, EDUCATION, HOUSING + ' Suite.', EDUCATION + ' Suite.']] * 8)
    collector = mock_pages(monkeypatch, pages)
    corpus = prepare(data)
    assert len(collector.call_args.args[0]) == 6
    assert len(corpus['sources']) == 18
    assert len({source['event_id'] for source in corpus['sources']}) == 6
    assert all(len(source['text']) <= 4000 for source in corpus['sources'])


def test_multi_topic_brief_uses_one_explicit_mocked_generation(monkeypatch):
    data, pages = collection(['logement', 'bourses'], [HOUSING, EDUCATION])
    mock_pages(monkeypatch, pages)
    monkeypatch.setenv('ENABLE_PIPELEX_CALLS', 'true')
    monkeypatch.setenv('PIPELEX_EXECUTION_MODE', 'hosted')
    generate = AsyncMock(return_value=Brief(items=[], limitations=['Réponse fictive.']))
    monkeypatch.setattr('backend.recent_brief.summarize', generate)
    build(data)
    generate.assert_awaited_once()
    request = generate.call_args.args[0]
    assert request.topic == 'logement · bourses'
    assert HOUSING in request.corpus_json
    assert EDUCATION in request.corpus_json
