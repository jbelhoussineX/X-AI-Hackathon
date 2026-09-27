"""Semantic relevance is model-selected; dates, provenance and bounds stay enforced."""
from copy import deepcopy
from unittest.mock import Mock

import pytest

from backend import recent_agent as agent
from backend.agent_models import Selection
from backend.data_sources import recent
from backend.data_sources.debates import passages
from backend.data_sources.live_feeds import rss_events, amendment_event
from backend.recent_brief import prepare
from test_live_feeds import RSS, XML, URL
from test_recent_topics import offline, TODAY, event
from test_recent_brief_topics import collection, mock_pages
from test_recent_agent import result, mocks, install_model


def test_candidate_inventory_has_no_keyword_filter_but_enforces_dates(offline):
    inventory = recent.collect_candidates(days=7, today=TODAY)
    titles = {row['title'] for row in inventory['events']}
    assert 'Projet fictif logement' in titles
    assert 'Projet fictif travail' in titles
    assert 'Projet fictif énergie' in titles
    assert not any('futur' in title or 'ancien' in title for title in titles)
    for name in ('assembly', 'senate', 'feeds', 'debates'):
        offline[name].assert_called_once()
    assert offline['feeds'].call_args.args == (None, '2026-09-21', '2026-09-27')


def test_candidate_pool_is_bounded_and_keeps_smaller_providers(offline):
    many = [event(f'feed:{i}', title=f'Notice {i}') for i in range(200)]
    offline['feeds'].return_value = many, [], []
    inventory = recent.collect_candidates(days=7, today=TODAY)
    assert len(inventory['events']) == 120
    assert {row['provider'] for row in inventory['events']} >= {'assemblee', 'senat', 'senat-rss'}
    assert inventory['total_events'] > 120
    assert any('120 notices' in limitation for limitation in inventory['limitations'])


def test_candidate_inventory_excludes_adjacent_day_feed_entries(offline):
    offline['feeds'].return_value = ([event('yesterday', day='2026-09-26'),
                                     event('today', day='2026-09-27'),
                                     event('tomorrow', day='2026-09-28')], [], [])
    inventory = recent.collect_candidates(days=1, today=TODAY)
    assert [row['id'] for row in inventory['events']] == ['today']


def test_feeds_and_amendments_support_semantic_candidates():
    assert rss_events(RSS, None, '2026-09-21', '2026-09-27', 'feed')
    assert rss_events(RSS, None, '2026-09-26', '2026-09-27', 'feed') == []
    assert amendment_event(XML, None, '2026-09-26T12:00:00', URL, 'list', 1)


def test_no_keyword_gate_in_evidence_and_no_pdf_page_stitching(monkeypatch):
    pages_text = ['Une aide au paiement des loyers est proposée sous conditions de ressources.',
                  'Le texte prévoit des modalités de versement qui restent à préciser.']
    data, pages = collection(['étudiant'], [pages_text])
    mock_pages(monkeypatch, pages)
    assert prepare(data)['sources'] == []  # Historical lexical path remains internal.
    corpus = prepare(data, semantic=True)
    assert len(corpus['sources']) == 2
    assert all(source['text'] in pages_text for source in corpus['sources'])
    assert all(quote['excerpt'] in source['text'] for source in corpus['sources'] for quote in source['quotes'])
    long_text = 'Début. ' * 1000 + 'Milieu. ' * 1000 + 'Fin. ' * 1000
    assert all(chunk in long_text for chunk in passages(long_text, None))


def test_model_can_select_a_notice_without_literal_query_terms(monkeypatch):
    inventory = result()
    inventory['events'][0]['title'] = 'Versement d’une allocation pour payer le loyer'
    original = deepcopy(inventory)
    model = Mock(return_value=Selection(queries=['logement étudiant'], event_ids=['c0']))
    monkeypatch.setattr(agent, 'call_stage', model)
    selected, queries = agent.select_candidates(inventory, 'logement étudiant')
    assert selected['events'] == original['events']
    assert inventory == original
    assert queries == ['logement étudiant']
    assert model.call_args.args[0] == 'select'
    assert model.call_args.args[2]['candidates'][0]['title'] == original['events'][0]['title']


@pytest.mark.parametrize('ids', [['invented'], ['c0', 'c0']])
def test_unknown_or_duplicate_model_selected_ids_are_rejected(monkeypatch, ids):
    model = Mock(return_value=Selection(queries=['logement'], event_ids=ids))
    monkeypatch.setattr(agent, 'call_stage', model)
    with pytest.raises(agent.BriefError, match='absente ou répétée'):
        agent.select_candidates(result(), 'logement')
    model.assert_called_once()


def test_no_extra_selection_when_all_candidates_already_selected(monkeypatch, mocks):
    mocks[0].return_value = result()
    model = install_model(monkeypatch, supplement=True)
    output = agent.research(['logement'], months=1, today=TODAY)
    assert [call.args[0] for call in model.call_args_list] == ['select', 'evaluate', 'summarize']
    assert not any(step['step'] == 'complement' for step in output['agent_analysis']['trace'])


def test_supplement_failure_keeps_initial_sources_without_retry(monkeypatch, mocks):
    model = install_model(monkeypatch, supplement=True)
    original = model.side_effect
    def fail_supplement(stage, topic, payload):
        if stage == 'select' and payload['focus']:
            raise agent.PipelexError('Limite OpenAI atteinte.')
        return original(stage, topic, payload)
    model.side_effect = fail_supplement
    with pytest.raises(agent.AgentError, match='complément') as caught:
        agent.research(['logement'], months=1, today=TODAY)
    assert model.call_count == 3
    assert len(caught.value.result['events']) == 1
    assert caught.value.result['events'][0]['id'] == 'initial'
