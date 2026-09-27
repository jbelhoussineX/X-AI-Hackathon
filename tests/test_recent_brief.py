import asyncio
from datetime import datetime, timezone
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from backend.data_sources.debates import INDEXES, dated_links, collect, passages
from backend.generated.recent_brief.models import Request, Brief, Item
from backend.recent_brief import build, prepare, verify
from test_pipelex import offline

URL = 'https://www.assemblee-nationale.fr/dyn/17/comptes-rendus/seance/session-ordinaire-de-2025-2026/premiere-seance-du-vendredi-25-septembre-2026'
TEXT = 'Mme Exemple. Nous discutons du logement étudiant et des conditions de ressources. Le vote est reporté.'


def result():
    return {'topic': 'logement', 'start': '2026-09-21', 'end': '2026-09-27',
            'collected_at': datetime.now(timezone.utc).isoformat(), 'limitations': [],
            'events': [{'id': 'one', 'title': 'Débat', 'event_date': '2026-09-25', 'category': 'debat',
                        'date_kind': 'Date de séance', 'dossier_url': URL,
                        'retrieved_at': '2026-09-27T12:00:00Z', 'content_passages': [TEXT]}]}


def test_dates_links_and_real_content_not_titles():
    index = f'<a href="{URL}#intervention">Séance</a><a href="https://evil.test{URL}">Faux</a>'
    assert dated_links(index.encode(), INDEXES['assemblee-debats']) == [(URL, '2026-09-25')]
    def handler(request):
        if str(request.url) == INDEXES['assemblee-debats']:
            return httpx.Response(200, text=index)
        if str(request.url) == URL:
            return httpx.Response(200, text=f'<main>25 septembre 2026<p>{TEXT}</p></main>')
        return httpx.Response(503)
    events, sources, limits = collect('logement', '2026-09-21', '2026-09-27', transport=httpx.MockTransport(handler))
    assert len(events) == 1
    assert TEXT in events[0]['content_passages'][0]
    assert events[0]['publication_date'] is None
    assert sources[1]['status'] == 'unavailable'
    assert collect('santé', '2026-09-21', '2026-09-27', transport=httpx.MockTransport(handler))[0] == []
    assert collect('logement', '2026-09-26', '2026-09-27', transport=httpx.MockTransport(handler))[0] == []


def test_senate_follows_observed_full_page_and_checks_date():
    base = 'https://www.senat.fr/cra/s20260925/s20260925_som.html'
    full = base.replace('_som', '_mono')
    def handler(request):
        url = str(request.url)
        if url == INDEXES['senat-debats']:
            return httpx.Response(200, text=f'<a href="{base}">25 septembre</a>')
        if url == base:
            return httpx.Response(200, text='<a href="s20260925_mono.html">Une seule page</a>')
        if url == full:
            return httpx.Response(200, text=f'<main>25 septembre 2026 {TEXT}</main>')
        return httpx.Response(503)
    events, _, _ = collect('logement', '2026-09-21', '2026-09-27', transport=httpx.MockTransport(handler))
    assert len(events) == 1 and events[0]['dossier_url'] == full
    assert events[0]['category'] == 'debat'


def test_passages_are_contiguous_and_bounded():
    text = 'A' * 10000 + TEXT + 'B' * 10000
    chunks = passages(text, 'logement')
    assert chunks and all(chunk in text and len(chunk) <= 3000 for chunk in chunks)


@pytest.mark.parametrize('bad', ['invented', 'unknown'])
def test_rejects_fake_citations_and_references(bad):
    corpus = prepare(result())
    item = Item(source_id='e0p0', summary='Un débat sur le logement.', quote_id='q0')
    if bad == 'invented':
        item.quote_id = 'invented'
    if bad == 'unknown':
        item.source_id = 'missing'
    with pytest.raises(ValueError):
        verify(Brief(items=[item, item] if bad == 'duplicate' else [item], limitations=[]), corpus)


def test_hosted_call_once_and_never_on_empty_or_stale(monkeypatch):
    monkeypatch.setenv('PIPELEX_EXECUTION_MODE', 'hosted')
    call = AsyncMock(return_value=Brief(items=[Item(source_id='e0p0', summary='Débat documenté.', quote_id='q0')], limitations=[]))
    monkeypatch.setattr('backend.recent_brief.summarize', call)
    output = build(result())
    assert output['items'][0]['url'] == URL
    assert call.call_count == 1
    empty = result(); empty['events'] = []
    assert build(empty)['items'] == []
    stale = result(); stale['collected_at'] = '2020-01-01T00:00:00Z'
    with pytest.raises(ValueError):
        build(stale)
    assert call.call_count == 1


def test_disabled_calls_fail_before_collection(monkeypatch):
    monkeypatch.setenv('ENABLE_PIPELEX_CALLS', 'false')
    collector = Mock(side_effect=AssertionError('Should not collect'))
    monkeypatch.setattr('backend.recent_brief.prepare', collector)
    with pytest.raises(RuntimeError):
        build(result())
    collector.assert_not_called()


def test_local_real_pipelex_graph_with_mock_inference(monkeypatch):
    from src.recent_worker import execute
    from pipelex.pipe_operators.llm.pipe_llm import run_llm_object
    captured = []
    async def fake(**kwargs):
        captured.append(kwargs)
        return kwargs['output_class'].model_validate({'items': [
            {'source_id': 'e0p0', 'summary': 'Débat documenté.', 'quote_id': 'q0'}], 'limitations': []})
    monkeypatch.setattr(run_llm_object.__module__ + '.generate_object_content', fake)
    req = Request(topic='logement', corpus_json=json.dumps(prepare(result())))
    output = asyncio.run(execute(req))
    assert output.items[0].quote_id == 'q0'
    assert len(captured) == 1
    assert 'logement' in captured[0]['llm_prompt'].user_text


def test_hosted_typed_call_uses_current_bundle(monkeypatch):
    from backend.pipelex_recent import summarize
    monkeypatch.setenv('PIPELEX_API_KEY', 'offline-pipelex-placeholder')
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.start_and_wait.return_value = SimpleNamespace(main_stuff={'items': [], 'limitations': []})
    monkeypatch.setattr('backend.pipelex_recent.pipelex_client', lambda: client)
    out = asyncio.run(summarize(Request(topic='logement', corpus_json='{}')))
    assert out.items == []
    assert client.start_and_wait.call_args.kwargs['pipe_code'] == 'recent_brief.summarize'


def test_ui_requires_click_and_does_not_repeat_generation(monkeypatch):
    from streamlit.testing.v1 import AppTest
    data = result()
    data['datasets'] = []
    data['events'][0].update(event='Débat', decision=None, provider='assemblee-debats',
                             source_url=URL, source_location='Compte rendu')
    generate = Mock(return_value=data)
    monkeypatch.setattr('frontend.recent_activity.agent_research', generate)
    app = AppTest.from_string('from frontend.recent_activity import render\nrender()').run()
    generate.assert_not_called()
    app.text_input(key='recent_topic').set_value('logement').run()
    generate.assert_not_called()
    app.button[0].click().run()
    assert not app.exception
    generate.assert_called_once()
    app.run()
    generate.assert_called_once()
    app.session_state['recent_brief'] = {'items': []}
    app.button[0].click().run()
    assert generate.call_count == 2
    assert 'recent_brief' not in app.session_state


@pytest.mark.parametrize('bad, message', [('invented', 'identifiant de citation absent'), ('unknown', 'référence absente')])
def test_precise_safe_rejection(bad, message):
    from backend.recent_brief import BriefError
    item = Item(source_id='e0p0', summary='Débat documenté.', quote_id='q0')
    if bad == 'invented':
        item.quote_id = 'invented'
    if bad == 'unknown':
        item.source_id = 'SECRET-untrusted-provider-value'
    with pytest.raises(BriefError, match=message) as caught:
        verify(Brief(items=[item, item] if bad == 'duplicate' else [item], limitations=[]), prepare(result()))
    assert 'SECRET' not in str(caught.value)


def test_stale_rejection_happens_before_any_network(monkeypatch):
    from backend.recent_brief import BriefError
    collector = Mock(side_effect=AssertionError('No network'))
    monkeypatch.setattr('backend.recent_brief.prepare', collector)
    data = result(); data['collected_at'] = '2020-01-01T00:00:00Z'
    with pytest.raises(BriefError, match='plus d’une heure'):
        build(data)
    collector.assert_not_called()


def test_error_persists_in_ui_without_retry(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from backend.recent_agent import AgentError
    generate = Mock(side_effect=AgentError('La citation ne se retrouve pas dans le passage.'))
    monkeypatch.setattr('frontend.recent_activity.agent_research', generate)
    app = AppTest.from_string('from frontend.recent_activity import render\nrender()').run()
    app.text_input(key='recent_topic').set_value('logement')
    app.button[0].click().run()
    assert 'citation' in app.error[0].value
    app.run()
    assert 'citation' in app.error[0].value
    generate.assert_called_once()
    generate.side_effect = None
    generate.return_value = dict(result(), datasets=[], events=[])
    app.button[0].click().run()
    assert not app.error


def test_quotes_are_exact_slices_and_selected_without_model_copy():
    from backend.recent_brief import quote_options
    text = ('Un passage officiel avec accents, apostrophes et conditions. ' * 40).strip()
    quotes = quote_options(text)
    assert len(quotes) > 1
    assert all(25 <= len(q['excerpt']) <= 500 and q['excerpt'] in text for q in quotes)
    data = result(); data['events'][0]['content_passages'] = [text]
    corpus = prepare(data)
    chosen = corpus['sources'][0]['quotes'][1]
    output = verify(Brief(items=[Item(source_id='e0p0', quote_id=chosen['quote_id'], summary='Résumé de test.')], limitations=[]), corpus)
    assert output['items'][0]['excerpt'] == chosen['excerpt']


def test_tampered_quote_is_rejected():
    corpus = prepare(result())
    corpus['sources'][0]['quotes'][0]['excerpt'] = 'Citation corrompue absente du texte.'
    with pytest.raises(ValueError, match='incohérent'):
        verify(Brief(items=[Item(source_id='e0p0', quote_id='q0', summary='Résumé de test.')], limitations=[]), corpus)


def test_duplicate_events_keep_first_verified_item_with_visible_count():
    corpus = prepare(result())
    item = Item(source_id='e0p0', quote_id='q0', summary='Premier résumé vérifié.')
    second = Item(source_id='e0p0', quote_id='q0', summary='Autre résumé du même événement.')
    output = verify(Brief(items=[item, second], limitations=[]), corpus)
    assert len(output['items']) == 1
    assert output['items'][0]['summary'] == item.summary
    assert output['duplicate_count'] == 1
    assert 'répétition' in output['limitations'][-1]


def test_invalid_duplicate_is_not_silently_accepted():
    corpus = prepare(result())
    items = [Item(source_id='e0p0', quote_id=q, summary='Résumé.') for q in ['q0','invented']]
    with pytest.raises(ValueError, match='identifiant de citation absent'):
        verify(Brief(items=items, limitations=[]), corpus)
