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
    monkeypatch.setattr(ui, 'PROFILE_PATH', tmp_path / 'profiles.sqlite3')
    monkeypatch.setattr(ui, 'current_identity', lambda: None)
    monkeypatch.setattr('src.service.search', Mock(side_effect=AssertionError('No AI in profile tests')))
    monkeypatch.setattr('frontend.recent_activity.search_recent', Mock(side_effect=AssertionError('No network')))
    monkeypatch.setattr('frontend.recent_activity.build', Mock(side_effect=AssertionError('No synthesis')))


def app_for(monkeypatch, who=None):
    monkeypatch.setattr(ui, 'current_identity', lambda: who)
    app = AppTest.from_file(str(ROOT / 'app.py')).run()
    assert not app.exception
    app.radio(key='b_page').set_value('Mon profil').run()
    assert not app.exception
    return app


def test_anonymous_profile_does_not_create_a_database(monkeypatch):
    app = app_for(monkeypatch)
    assert 'Mode invité' in app.info[0].value
    assert not ui.PROFILE_PATH.exists()
    assert any(button.label == 'Enregistrer mon profil' for button in app.button)


def test_login_only_starts_on_click_and_errors_do_not_expose_secrets(monkeypatch):
    login = Mock(side_effect=RuntimeError('TOP_SECRET_CLIENT_TOKEN'))
    monkeypatch.setattr(ui.st, 'login', login)
    app = app_for(monkeypatch)
    login.assert_not_called()
    app.button(key='profile_login').click().run()
    assert not app.exception
    login.assert_called_once_with('google')
    assert any('indisponible' in error.value for error in app.error)
    assert 'TOP_SECRET' not in str([error.value for error in app.error])
    assert not ui.PROFILE_PATH.exists()


def test_profile_persists_between_sessions_and_prefills_only_after_click(monkeypatch):
    alice = identity()
    app = app_for(monkeypatch, alice)
    app.text_input(key='profile_display_name').set_value('Alice citoyenne')
    app.multiselect(key='profile_topics').set_value(['logement', 'transports'])
    app.number_input(key='profile_months').set_value(2)
    next(button for button in app.button if button.label == 'Enregistrer mon profil').click().run()
    assert not app.exception
    saved = ProfileStore(ui.PROFILE_PATH).get_or_create(alice)
    assert saved['display_name'] == 'Alice citoyenne'
    assert saved['topics'] == ['logement', 'transports']
    again = app_for(monkeypatch, alice)
    assert again.text_input(key='profile_display_name').value == 'Alice citoyenne'
    assert again.multiselect(key='profile_topics').value == ['logement', 'transports']
    again.button(key='profile_search_0').click().run()
    assert not again.exception
    assert again.session_state['b_page'] == 'Recherche'
    assert [field.key for field in again.text_input] == ['recent_topic']
    assert again.text_input(key='recent_topic').value == 'logement'
    assert again.number_input(key='recent_amount').value == 2
    assert again.selectbox(key='recent_unit').value == 'mois'
    assert again.session_state['b_last'] is None
    from src.service import search
    from frontend.recent_activity import search_recent
    search.assert_not_called()
    search_recent.assert_not_called()


def test_profile_topic_clears_previous_results_filters_and_ai_consent(monkeypatch):
    alice = identity()
    ProfileStore(ui.PROFILE_PATH).update(
        alice, display_name='Alice', topics=['logement'], recent_months=1)
    app = app_for(monkeypatch, alice)
    previous_fields = {
        'recent_result': {'topic': 'Ancien sujet'},
        'recent_brief': {'items': ['Ancienne synthèse']},
        'recent_brief_error': 'Ancienne erreur',
        'recent_categories': ['debat'],
        'recent_order': 'Plus anciens d’abord',
        'recent_consent': True,
    }
    for key, value in previous_fields.items():
        app.session_state[key] = value
    app.session_state['b_last'] = {'previous': 'result'}
    app.session_state['b_error'] = 'Ancienne erreur'
    app.session_state['recent_topic'] = 'Ancien sujet'
    app.session_state['recent_amount'] = 90
    app.session_state['recent_unit'] = 'jours'

    app.button(key='profile_search_0').click().run()

    assert not app.exception
    assert app.session_state['b_page'] == 'Recherche'
    assert app.text_input(key='recent_topic').value == 'logement'
    assert app.number_input(key='recent_amount').value == 1
    assert app.selectbox(key='recent_unit').value == 'mois'
    assert app.session_state['b_last'] is None
    assert app.session_state['b_error'] is None
    for key in previous_fields:
        assert key not in app.session_state
    from src.service import search
    from frontend.recent_activity import build, search_recent
    search.assert_not_called()
    search_recent.assert_not_called()
    build.assert_not_called()


def test_switching_accounts_clears_results_forms_and_paid_consent(monkeypatch):
    alice, bob = identity(), identity('bob')
    app = app_for(monkeypatch, alice)
    app.multiselect(key='profile_topics').set_value(['logement'])
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
    assert app.multiselect(key='profile_topics').value == []
    assert ProfileStore(ui.PROFILE_PATH).get_or_create(alice)['topics'] == ['logement']


def test_delete_needs_confirmation_and_does_not_delete_another_profile(monkeypatch):
    alice, bob = identity(), identity('bob')
    store = ProfileStore(ui.PROFILE_PATH)
    store.update(bob, display_name='Bob', topics=['énergie'], recent_months=1)
    logout = Mock()
    monkeypatch.setattr(ui.st, 'logout', logout)
    app = app_for(monkeypatch, alice)
    assert app.button(key='profile_delete').disabled
    app.checkbox(key='profile_delete_confirm').check().run()
    app.button(key='profile_delete').click().run()
    assert not app.exception
    logout.assert_called_once()
    assert store.get_or_create(bob)['topics'] == ['énergie']
    # Native st.logout starts a new session; the mock cannot reproduce that redirect.
    anonymous = app_for(monkeypatch)
    assert not anonymous.exception
    import sqlite3
    with sqlite3.connect(ui.PROFILE_PATH) as db:
        assert db.execute('SELECT count(*) FROM profiles WHERE user_id=?', (alice.user_id,)).fetchone()[0] == 0


def test_deleted_profile_is_not_recreated_when_logout_cannot_complete(monkeypatch):
    alice = identity()
    monkeypatch.setattr(ui, 'current_identity', lambda: alice)
    app = AppTest.from_file(str(ROOT / 'app.py'))
    app.session_state['_profile_owner'] = alice.user_id
    app.session_state['_profile_deleted_for'] = alice.user_id
    app.session_state['b_page'] = 'Mon profil'
    app.run()
    assert not app.exception
    assert any('supprimé' in message.value for message in app.success)
    assert not ui.PROFILE_PATH.exists()


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
