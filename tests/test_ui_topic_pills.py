"""Topic pills select searches explicitly without repeated provider calls."""
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from backend.profiles import ProfileStore, identity_from_claims
from frontend import profile as ui
from src.contracts import ROOT


def identity():
    return identity_from_claims(
        {'iss': 'https://accounts.google.com', 'sub': 'test-alice',
         'email': 'alice@example.test', 'email_verified': True, 'name': 'Alice'},
        is_logged_in=True)


def result(topics):
    return {'topic': ' · '.join(topics), 'topics': list(topics),
            'start': '2026-06-27', 'end': '2026-09-27',
            'collected_at': '2026-09-27T12:00:00Z',
            'datasets': [], 'events': [], 'limitations': ['Corpus fictif.']}


@pytest.fixture
def offline(monkeypatch, tmp_path):
    monkeypatch.setenv('PYTHON_DOTENV_DISABLED', '1')
    monkeypatch.setenv('DO_NOT_TRACK', '1')
    monkeypatch.setenv('ENABLE_PIPELEX_CALLS', 'true')
    monkeypatch.setattr(ui, 'PROFILE_PATH', tmp_path / 'profiles.sqlite3')
    active = {'identity': None}
    monkeypatch.setattr(ui, 'current_identity', lambda: active['identity'])
    mocks = {name: Mock(side_effect=AssertionError('Unexpected provider call'))
             for name in ('agent', 'synthesis', 'legacy')}
    monkeypatch.setattr('frontend.recent_activity.agent_research', mocks['agent'])
    monkeypatch.setattr('backend.recent_brief.build', mocks['synthesis'])
    monkeypatch.setattr('src.service.search', mocks['legacy'])
    return active, mocks


def app():
    instance = AppTest.from_file(str(ROOT / 'app.py')).run()
    assert not instance.exception
    return instance


def search_button(instance):
    buttons = [button for button in instance.button if button.label == 'Rechercher']
    assert len(buttons) == 1
    return buttons[0]


def assert_no_calls(mocks):
    for mock in mocks.values():
        mock.assert_not_called()


def allow_result(mock, topics):
    mock.side_effect = None
    mock.return_value = result(topics)


def test_single_topic_selection_does_not_search_until_one_submit(offline):
    _, mocks = offline
    instance = app()
    assert instance.pills(key='recent_topics').value == []
    assert instance.text_input(key='recent_topic').label == 'Autres sujets'
    assert not any(expander.text_input for expander in instance.expander)
    instance.pills(key='recent_topics').set_value(['logement']).run()
    assert not instance.exception
    assert_no_calls(mocks)
    allow_result(mocks['agent'], ['logement'])

    search_button(instance).click().run()

    assert not instance.exception
    mocks['agent'].assert_called_once_with(['logement'], months=3)
    instance.run()
    assert not instance.exception
    mocks['agent'].assert_called_once()
    mocks['synthesis'].assert_not_called()
    mocks['legacy'].assert_not_called()
    assert len(instance.session_state['profile_guest_data']['history']) == 1
    assert not ui.PROFILE_PATH.exists()


def test_multiple_topics_use_one_search_request_and_one_history_entry(offline):
    _, mocks = offline
    instance = app()
    instance.pills(key='recent_topics').set_value(['logement', 'emploi']).run()
    assert not instance.exception
    assert_no_calls(mocks)
    allow_result(mocks['agent'], ['logement', 'emploi'])

    search_button(instance).click().run()

    assert not instance.exception
    mocks['agent'].assert_called_once_with(['logement', 'emploi'], months=3)
    mocks['synthesis'].assert_not_called()
    mocks['legacy'].assert_not_called()
    assert instance.session_state['recent_result']['topics'] == ['logement', 'emploi']
    history = instance.session_state['profile_guest_data']['history']
    assert len(history) == 1
    assert history[0]['data']['topic'] == 'logement · emploi'

    instance.radio(key='b_page').set_value('Historique').run()
    assert not instance.exception
    next(button for button in instance.button if button.label == 'Ouvrir les résultats').click().run()
    assert not instance.exception
    assert instance.session_state['b_page'] == 'Recherche'
    assert instance.pills(key='recent_topics').value == ['logement', 'emploi']
    assert instance.text_input(key='recent_topic').value == ''
    mocks['agent'].assert_called_once()
    assert len(instance.session_state['profile_guest_data']['history']) == 1


def test_empty_search_never_collects(offline):
    _, mocks = offline
    instance = app()
    assert instance.pills(key='recent_topics').value == []
    button = search_button(instance)
    if not button.disabled:
        button.click().run()
    assert not instance.exception
    assert_no_calls(mocks)
    assert 'recent_result' not in instance.session_state


def test_saved_topics_and_validated_answers_are_sent_without_identity(offline):
    active, mocks = offline
    active['identity'] = alice = identity()
    store = ProfileStore(ui.PROFILE_PATH)
    store.update(alice, display_name='Alice', topics=['logement', 'emploi'], recent_months=2)
    store.save_answers(alice, {'emploi': 'Étudiant(e)', 'enfants': 'Avec enfant(s)'})
    instance = app()
    instance.radio(key='b_page').set_value('Mon profil').run()
    assert not instance.exception
    assert not instance.pills
    assert not any(button.label == 'Rechercher' for button in instance.button)
    assert_no_calls(mocks)
    instance.radio(key='b_page').set_value('Recherche').run()
    assert not instance.exception
    assert instance.pills(key='recent_topics').label == 'Sujets'
    assert {'logement', 'emploi', 'santé'} <= set(instance.pills(key='recent_topics').options)
    assert instance.number_input(key='recent_amount').value == 2
    assert_no_calls(mocks)
    instance.pills(key='recent_topics').set_value(['emploi']).run()
    assert not instance.exception
    assert_no_calls(mocks)
    allow_result(mocks['agent'], ['emploi'])

    search_button(instance).click().run()

    assert not instance.exception
    assert instance.session_state['b_page'] == 'Recherche'
    assert instance.pills(key='recent_topics').value == ['emploi']
    assert instance.number_input(key='recent_amount').value == 2
    assert 'recent_pending_search' not in instance.session_state
    # Only explicit questionnaire choices accompany the selected subject.
    mocks['agent'].assert_called_once_with(['emploi'], months=2,
        profile_context={'emploi': 'Étudiant(e)', 'enfants': 'Avec enfant(s)'})
    mocks['synthesis'].assert_not_called()
    assert len(store.items(alice, 'history')) == 1
    instance.run()
    assert not instance.exception
    mocks['agent'].assert_called_once()


def test_saving_profile_and_changing_pills_never_collects(offline):
    _, mocks = offline
    instance = app()
    instance.radio(key='b_page').set_value('Mon profil').run()
    assert not instance.exception
    assert not instance.multiselect
    instance.number_input(key='profile_months').set_value(4)
    next(button for button in instance.button if button.label == 'Enregistrer mon profil').click().run()
    assert not instance.exception
    assert not instance.pills
    assert_no_calls(mocks)
    instance.radio(key='b_page').set_value('Recherche').run()
    assert not instance.exception
    assert instance.pills(key='recent_topics').label == 'Sujets'
    assert {'énergie', 'transports', 'emploi'} <= set(instance.pills(key='recent_topics').options)
    assert instance.number_input(key='recent_amount').value == 4
    assert instance.selectbox(key='recent_unit').value == 'mois'
    instance.pills(key='recent_topics').set_value(['transports']).run()
    assert_no_calls(mocks)
    instance.radio(key='b_page').set_value('Mon profil').run()
    assert not instance.multiselect
    instance.number_input(key='profile_months').set_value(1)
    next(button for button in instance.button if button.label == 'Enregistrer mon profil').click().run()
    assert not instance.exception
    assert not instance.pills
    assert_no_calls(mocks)
    instance.radio(key='b_page').set_value('Recherche').run()
    assert not instance.exception
    assert 'emploi' in instance.pills(key='recent_topics').options
    assert instance.number_input(key='recent_amount').value == 1
    assert instance.selectbox(key='recent_unit').value == 'mois'
    assert_no_calls(mocks)


def test_failed_search_is_not_retried_on_rerun_or_navigation(offline):
    active, mocks = offline
    active['identity'] = alice = identity()
    store = ProfileStore(ui.PROFILE_PATH)
    store.update(alice, display_name='Alice', topics=['logement', 'emploi'], recent_months=1)
    instance = app()
    instance.pills(key='recent_topics').set_value(['logement', 'emploi']).run()
    assert not instance.exception
    mocks['agent'].side_effect = ValueError('Collecte indisponible dans le test')

    search_button(instance).click().run()

    assert not instance.exception
    assert instance.error
    assert 'recent_pending_search' not in instance.session_state
    assert 'recent_result' not in instance.session_state
    mocks['agent'].assert_called_once_with(['logement', 'emploi'], months=1)
    instance.run()
    assert not instance.exception
    instance.radio(key='b_page').set_value('Mon profil').run()
    instance.radio(key='b_page').set_value('Recherche').run()
    assert not instance.exception
    mocks['agent'].assert_called_once()
    mocks['synthesis'].assert_not_called()
    assert store.items(alice, 'history') == []


def test_custom_history_topic_is_restored_as_a_pill_without_a_search(offline):
    active, mocks = offline
    active['identity'] = alice = identity()
    store = ProfileStore(ui.PROFILE_PATH)
    store.update(alice, display_name='Alice', topics=['logement'], recent_months=1)
    saved = result(['accessibilité des bâtiments'])
    saved['search_period'] = {'amount': 14, 'unit': 'jours'}
    item_id = store.save_item(alice, 'history', saved)
    instance = app()
    instance.radio(key='b_page').set_value('Historique').run()
    assert not instance.exception
    instance.button(key='profile_open_' + item_id).click().run()
    assert not instance.exception
    assert instance.pills(key='recent_topics').value == ['accessibilité des bâtiments']
    assert instance.pills(key='recent_topics').label == 'Sujets'
    assert {'logement', 'santé', 'accessibilité des bâtiments'} <= set(instance.pills(key='recent_topics').options)
    assert instance.number_input(key='recent_amount').value == 14
    assert instance.selectbox(key='recent_unit').value == 'jours'
    assert instance.session_state['recent_result'] == saved
    assert_no_calls(mocks)
    assert len(store.items(alice, 'history')) == 1


def test_saved_pills_and_comma_separated_free_topics_form_one_search(offline):
    active, mocks = offline
    active['identity'] = alice = identity()
    store = ProfileStore(ui.PROFILE_PATH)
    store.update(alice, display_name='Alice', topics=['logement'], recent_months=2)
    instance = app()
    instance.pills(key='recent_topics').set_value(['logement'])
    instance.text_input(key='recent_topic').set_value(' emploi , LOGEMENT, mobilité rurale, EMPLOI ').run()
    assert not instance.exception
    assert_no_calls(mocks)
    expected = ['logement', 'emploi', 'mobilité rurale']
    allow_result(mocks['agent'], expected)

    search_button(instance).click().run()

    assert not instance.exception
    mocks['agent'].assert_called_once_with(expected, months=2)
    mocks['synthesis'].assert_not_called()
    mocks['legacy'].assert_not_called()
    assert len(store.items(alice, 'history')) == 1
    assert instance.session_state['recent_result']['topics'] == expected


def test_free_topic_without_pills_searches_once_with_days_period(offline):
    _, mocks = offline
    instance = app()
    instance.text_input(key='recent_topic').set_value('  eau potable  ')
    instance.number_input(key='recent_amount').set_value(14)
    instance.selectbox(key='recent_unit').set_value('jours').run()
    assert not instance.exception
    assert_no_calls(mocks)
    allow_result(mocks['agent'], ['eau potable'])

    search_button(instance).click().run()

    assert not instance.exception
    mocks['agent'].assert_called_once_with(['eau potable'], days=14)
    mocks['synthesis'].assert_not_called()
    assert len(instance.session_state['profile_guest_data']['history']) == 1


@pytest.mark.parametrize('custom', [
    'ab', 'a' * 101, ', '.join(f'sujet {number}' for number in range(9)),
])
def test_invalid_free_subjects_are_rejected_before_any_collection(offline, custom):
    _, mocks = offline
    instance = app()
    instance.text_input(key='recent_topic').set_value(custom)

    search_button(instance).click().run()

    assert not instance.exception
    assert instance.error
    assert_no_calls(mocks)
    assert 'recent_result' not in instance.session_state


def test_eight_topics_including_free_text_are_accepted(offline):
    _, mocks = offline
    instance = app()
    expected = [f'sujet {number}' for number in range(8)]
    instance.text_input(key='recent_topic').set_value(', '.join(expected))
    allow_result(mocks['agent'], expected)

    search_button(instance).click().run()

    assert not instance.exception
    mocks['agent'].assert_called_once_with(expected, months=3)
    mocks['synthesis'].assert_not_called()
