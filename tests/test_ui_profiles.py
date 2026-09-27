"""Profiles integrate into the real UI without OAuth, network or paid inference."""
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from backend.profiles import ProfileStore, identity_from_claims
from frontend import profile as ui
from src.contracts import ROOT


def identity(subject='alice'):
    return identity_from_claims({'iss': 'https://accounts.google.com', 'sub': subject,
                                'email': f'{subject}@example.test', 'email_verified': True,
                                'name': subject.title()}, is_logged_in=True)


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    monkeypatch.setenv('PYTHON_DOTENV_DISABLED', '1')
    monkeypatch.setenv('DO_NOT_TRACK', '1')
    monkeypatch.setenv('ENABLE_PIPELEX_CALLS', 'true')
    monkeypatch.setattr(ui, 'PROFILE_PATH', tmp_path / 'profiles.sqlite3')
    monkeypatch.setattr(ui, 'current_identity', lambda: None)
    monkeypatch.setattr('src.service.search', Mock(side_effect=AssertionError('No AI in profile tests')))
    monkeypatch.setattr('frontend.recent_activity.agent_research', Mock(side_effect=AssertionError('No network')))
    monkeypatch.setattr('backend.data_sources.recent.search_topics', Mock(side_effect=AssertionError('No network')))
    monkeypatch.setattr('backend.recent_brief.build', Mock(side_effect=AssertionError('No synthesis')))


def app_for(monkeypatch, who=None):
    monkeypatch.setattr(ui, 'current_identity', lambda: who)
    app = AppTest.from_file(str(ROOT / 'app.py')).run()
    assert not app.exception
    app.radio(key='b_page').set_value('Mon profil').run()
    assert not app.exception
    return app


def recent_result(topics):
    return {'topic': ' · '.join(topics), 'topics': topics,
            'start': '2026-07-27', 'end': '2026-09-27',
            'collected_at': '2026-09-27T12:00:00Z', 'datasets': [],
            'events': [], 'limitations': ['Corpus fictif du test.']}


def test_anonymous_profile_does_not_create_a_database(monkeypatch):
    app = app_for(monkeypatch)
    assert not ui.PROFILE_PATH.exists()
    assert any(button.label == 'Enregistrer mon profil' for button in app.button)
    assert not app.get('download_button')
    assert not app.pills
    assert not any(button.label in ('Rechercher', 'Supprimer mon profil') for button in app.button)


def test_profile_has_no_login_or_guest_controls(monkeypatch):
    login = Mock(side_effect=AssertionError('Login disabled'))
    logout = Mock(side_effect=AssertionError('Logout disabled'))
    monkeypatch.setattr(ui.st, 'login', login)
    monkeypatch.setattr(ui.st, 'logout', logout)
    app = app_for(monkeypatch)
    assert not app.exception
    assert app.text_input(key='profile_display_name').value == 'Mon profil'
    for page in ('Recherche', 'Historique', 'Favoris', 'Mon profil', 'Aide'):
        app.radio(key='b_page').set_value(page).run()
        assert not app.exception
        visible = ' '.join(item.value for group in (app.text, app.caption, app.info, app.markdown) for item in group)
        assert 'Google' not in visible and 'invité' not in visible.lower()
        assert not any(button.key in ('profile_login', 'profile_logout', 'profile_invalid_logout') for button in app.button)
    login.assert_not_called()
    logout.assert_not_called()
    assert not ui.PROFILE_PATH.exists()


def test_profile_persists_between_sessions_and_searches_only_after_click(monkeypatch):
    collect = Mock(return_value=recent_result(['logement', 'transports']))
    monkeypatch.setattr('frontend.recent_activity.agent_research', collect)
    alice = identity()
    app = app_for(monkeypatch, alice)
    app.text_input(key='profile_display_name').set_value('Alice citoyenne')
    assert not app.multiselect
    app.number_input(key='profile_months').set_value(2)
    next(button for button in app.button if button.label == 'Enregistrer mon profil').click().run()
    assert not app.exception
    saved = ProfileStore(ui.PROFILE_PATH).get_or_create(alice)
    assert saved['display_name'] == 'Alice citoyenne'
    assert saved['topics'] == []
    again = app_for(monkeypatch, alice)
    assert again.text_input(key='profile_display_name').value == 'Alice citoyenne'
    assert not again.multiselect
    collect.assert_not_called()
    again.radio(key='b_page').set_value('Recherche').run()
    assert not again.exception
    assert again.session_state['b_page'] == 'Recherche'
    assert again.pills(key='recent_topics').label == 'Sujets'
    assert {'logement', 'transports', 'santé'} <= set(again.pills(key='recent_topics').options)
    again.pills(key='recent_topics').set_value(['logement', 'transports']).run()
    collect.assert_not_called()
    next(button for button in again.button if button.label == 'Rechercher').click().run()
    assert not again.exception
    assert [field.key for field in again.text_input] == ['recent_topic']
    assert again.text_input(key='recent_topic').value == ''
    assert again.pills(key='recent_topics').value == ['logement', 'transports']
    assert again.number_input(key='recent_amount').value == 2
    assert again.selectbox(key='recent_unit').value == 'mois'
    assert again.session_state['b_last'] is None
    from src.service import search
    from backend.data_sources.recent import search_topics
    search.assert_not_called()
    search_topics.assert_not_called()
    collect.assert_called_once_with(['logement', 'transports'], months=2)
    again.run()
    assert not again.exception
    collect.assert_called_once()


def test_explicit_search_clears_previous_results_filters_and_ai_consent(monkeypatch):
    fresh_result = recent_result(['logement'])
    collect = Mock(return_value=fresh_result)
    monkeypatch.setattr('frontend.recent_activity.agent_research', collect)
    alice = identity()
    ProfileStore(ui.PROFILE_PATH).update(
        alice, display_name='Alice', topics=['logement'], recent_months=1)
    app = app_for(monkeypatch, alice)
    app.radio(key='b_page').set_value('Recherche').run()
    assert not app.exception
    app.pills(key='recent_topics').set_value(['logement']).run()
    collect.assert_not_called()
    previous_fields = {
        'recent_result': recent_result(['Ancien sujet']),
        'recent_brief': {'items': ['Ancienne synthèse']},
        'recent_brief_error': 'Ancienne erreur',
        'recent_categories': ['debat'],
        'recent_order': 'Plus anciens d’abord',
        'recent_consent': True,
    }
    for key, value in previous_fields.items():
        app.session_state[key] = value
    next(button for button in app.button if button.label == 'Rechercher').click().run()

    assert not app.exception
    assert app.session_state['b_page'] == 'Recherche'
    assert app.text_input(key='recent_topic').value == ''
    assert app.pills(key='recent_topics').value == ['logement']
    assert app.number_input(key='recent_amount').value == 1
    assert app.selectbox(key='recent_unit').value == 'mois'
    assert app.session_state['recent_result'] == fresh_result
    assert app.multiselect(key='recent_categories').value == []
    assert app.selectbox(key='recent_order').value == 'Plus récents d’abord'
    for key in ('recent_brief', 'recent_brief_error', 'recent_consent'):
        assert key not in app.session_state
    from src.service import search
    from backend.recent_brief import build
    from frontend.recent_activity import agent_research
    search.assert_not_called()
    agent_research.assert_called_once_with(['logement'], months=1)
    build.assert_not_called()


def test_switching_accounts_clears_results_forms_and_paid_consent(monkeypatch):
    alice, bob = identity(), identity('bob')
    app = app_for(monkeypatch, alice)
    ProfileStore(ui.PROFILE_PATH).update(alice, display_name='Alice', topics=['logement'], recent_months=3)
    assert not app.multiselect
    next(button for button in app.button if button.label == 'Enregistrer mon profil').click().run()
    app.session_state['b_history'] = [{'private': 'alice'}]
    app.session_state['b_watches'] = [{'private': 'alice'}]
    app.session_state['b_consent'] = True
    app.session_state['b_live_attempts'] = 3
    app.session_state['recent_result'] = {'private': 'alice'}
    monkeypatch.setattr(ui, 'current_identity', lambda: bob)
    app.run()
    assert not app.exception
    assert app.session_state['b_history'] == app.session_state['b_watches'] == []
    assert app.session_state['b_consent'] is False
    assert app.session_state['b_live_attempts'] == 3
    assert 'recent_result' not in app.session_state
    app.radio(key='b_page').set_value('Mon profil').run()
    assert not app.exception
    assert app.text_input(key='profile_display_name').value == 'Bob'
    assert not app.multiselect
    assert ProfileStore(ui.PROFILE_PATH).get_or_create(alice)['topics'] == ['logement']


def test_profile_has_no_export_delete_or_search_controls_and_preserves_accounts(monkeypatch):
    alice, bob = identity(), identity('bob')
    store = ProfileStore(ui.PROFILE_PATH)
    store.update(alice, display_name='Alice', topics=['logement'], recent_months=2)
    store.update(bob, display_name='Bob', topics=['énergie'], recent_months=1)
    logout = Mock()
    monkeypatch.setattr(ui.st, 'logout', logout)
    app = app_for(monkeypatch, alice)
    assert not app.get('download_button')
    assert not app.pills
    assert not any(button.label in ('Supprimer mon profil', 'Rechercher') for button in app.button)
    assert not any(item.label == 'Supprimer mon profil enregistré' for item in app.expander)
    assert not any(item.value == 'Explorer mes sujets' for item in app.subheader)
    assert not app.multiselect
    next(button for button in app.button if button.label == 'Enregistrer mon profil').click().run()
    assert not app.exception
    logout.assert_not_called()
    assert store.get_or_create(alice)['topics'] == ['logement']
    assert store.get_or_create(bob)['topics'] == ['énergie']


def test_clear_identity_removes_personal_fields_but_keeps_attempt_counter():
    state = {'b_last': 'private', 'b_history': ['private'], 'recent_result': 'private',
             'profile_topics': 'private', 'b_live_attempts': 7, 'unrelated': 1}
    ui.clear_personal_session(state)
    assert state == {'b_live_attempts': 7, 'unrelated': 1}


def test_help_clears_recent_results_without_deleting_saved_profile(monkeypatch):
    alice = identity()
    store = ProfileStore(ui.PROFILE_PATH)
    store.update(alice, display_name='Alice', topics=['logement'], recent_months=2)
    app = app_for(monkeypatch, alice)
    app.radio(key='b_page').set_value('Aide').run()
    recent_fields = ('recent_result', 'recent_brief', 'recent_brief_error',
                     'recent_categories', 'recent_order', 'recent_consent')
    for key in recent_fields:
        app.session_state[key] = 'Ancienne recherche'
    app.session_state['b_history'] = ['Ancienne recherche']
    app.session_state['b_live_attempts'] = 3
    app.button(key='b_clear_session').click().run()
    assert not app.exception
    assert all(key not in app.session_state for key in recent_fields)
    assert app.session_state['b_history'] == []
    assert app.session_state['b_live_attempts'] == 3
    assert store.get_or_create(alice)['topics'] == ['logement']
