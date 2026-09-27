"""Repeated cards are grouped without dropping legislative steps or versions."""
from copy import deepcopy
from unittest.mock import Mock

from streamlit.testing.v1 import AppTest

from frontend import profile
from frontend.recent_activity import group_sources, source_favorite_key
from backend.document_groups import document_key, group_summaries
from src.contracts import ROOT
from test_ui_favorite_stars import report


def test_exact_repetitions_group_but_acts_and_content_versions_are_kept():
    event = report()['events'][0]
    events = [event, dict(event, retrieved_at='2026-09-28T00:00:00Z'),
              dict(event, event='Adoption', event_date='2026-09-21'),
              dict(event, dataset_sha256='different-version'),
              dict(event, dossier_url='https://www.senat.fr/other.html')]
    before = deepcopy(events)
    groups, repeats = group_sources(events)
    assert len(groups) == 2
    assert len(groups[0]) == 3
    assert len(groups[1]) == 1
    assert repeats == 1
    assert events == before
    assert source_favorite_key(events[0]) == source_favorite_key(events[1])
    assert source_favorite_key(events[0]) != source_favorite_key(events[2])


def test_missing_links_do_not_group_unrelated_events():
    base = report()['events'][0]
    groups, _ = group_sources([dict(base, dossier_url='', title=title) for title in ('A', 'B')])
    assert len(groups) == 2


def test_url_variants_and_different_collectors_group_without_losing_versions():
    base = dict(report()['events'][0], id='from-inventory', dossier_url='https://www.senat.fr/dossier/texte.html')
    duplicate = dict(base, id='from-feed', source_location='rss', provider='rss',
                     dossier_url='http://senat.fr/dossier/texte.html?utm_source=rss#section1')
    changed = dict(duplicate, content_passages=['Une version modifiée.'])
    adopted = dict(duplicate, event='Adoption', event_date='2026-09-25')
    before = deepcopy([base, duplicate, changed, adopted])
    groups, repeats = group_sources(before)
    assert repeats == 1
    assert len(groups) == 1 and len(groups[0]) == 3
    assert before == [base, duplicate, changed, adopted]
    assert document_key('https://www.senat.fr/texte?version=1') != document_key('https://www.senat.fr/texte?version=2')


def test_summary_groups_keep_distinct_steps_but_not_repeated_provenance():
    base = dict(event_id='a', url='https://www.senat.fr/leg/test.html', event_date='2026-09-20',
                event_label='Dépôt', sha256='version1', summary='Le texte propose une mesure.')
    duplicate = dict(base, event_id='b', url=base['url'] + '#toc')
    later = dict(base, event_id='c', event_label='Adoption', event_date='2026-09-25')
    other = dict(base, event_id='d', url='https://www.senat.fr/leg/other.html')
    groups = group_summaries([base, duplicate, later, other])
    assert groups == [[base, later], [other]]


def test_one_source_card_preserves_steps_and_favorites_across_sorting(monkeypatch, tmp_path):
    monkeypatch.setenv('PYTHON_DOTENV_DISABLED', '1')
    monkeypatch.setattr(profile, 'current_identity', lambda: None)
    monkeypatch.setattr(profile, 'PROFILE_PATH', tmp_path / 'profiles.sqlite3')
    model = Mock(side_effect=AssertionError('No model calls while browsing sources'))
    monkeypatch.setattr('frontend.recent_activity.agent_research', model)
    app = AppTest.from_file(str(ROOT / 'app.py')).run()
    data = report()
    adoption = dict(data['events'][0], event='Adoption', event_date='2026-09-21')
    data['events'].append(adoption)
    app.session_state['recent_result'] = data
    app.run()
    assert not app.exception
    assert len([m for m in app.markdown if 'class="doc-title"' in m.value]) == 1
    assert any(e.label == 'Autres étapes et versions (1)' for e in app.expander)
    assert not any(t.value in ('Adoption', 'Dépôt') for t in app.text)
    assert not any(e.label == 'Détails et provenance' for e in app.expander)
    assert {event['event'] for event in app.session_state['recent_result']['events']} == {'Dépôt', 'Adoption'}
    key = source_favorite_key(adoption)
    app.button(key=key).click().run()
    assert not app.exception
    assert len(app.session_state['profile_guest_data']['favorite']) == 1
    app.selectbox(key='recent_order').set_value('Plus anciens d’abord').run()
    assert not app.exception
    assert app.button(key=key).proto.help == 'Retirer des favoris'
    app.button(key=key).click().run()
    assert not app.exception
    assert app.session_state['profile_guest_data']['favorite'] == []
    assert len(app.session_state['recent_result']['events']) == 3
    model.assert_not_called()
