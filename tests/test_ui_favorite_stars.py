"""Favorite stars toggle the same stored event without any provider request."""
from copy import deepcopy
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from backend.profiles import ProfileStore, identity_from_claims
from frontend import profile as ui
from src.contracts import ROOT
from frontend.recent_activity import source_favorite_key


def report():
    event = dict(title='Texte fictif', event_date='2026-09-20', event='Dépôt',
                 category='procedure', decision=None, provider='senat',
                 date_kind='publication', dossier_url='https://www.senat.fr/',
                 source_url='https://www.senat.fr/', source_location='Test',
                 retrieved_at='2026-09-27T12:00:00Z')
    return dict(topic='logement', topics=['logement'], start='2026-06-27', end='2026-09-27',
                collected_at='2026-09-27T12:00:00Z', datasets=[],
                limitations=['Corpus fictif du test.'], events=[event, deepcopy(event)])


@pytest.mark.parametrize('connected', [False, True], ids=['guest', 'google-account'])
def test_star_toggles_in_search_and_favorites_without_duplicates_or_calls(
        monkeypatch, tmp_path, connected):
    monkeypatch.setenv('PYTHON_DOTENV_DISABLED', '1')
    monkeypatch.setenv('DO_NOT_TRACK', '1')
    monkeypatch.setattr(ui, 'PROFILE_PATH', tmp_path / 'profiles.sqlite3')
    who = (identity_from_claims(
        dict(iss='https://accounts.google.com', sub='test-alice',
             email='alice@example.test', email_verified=True, name='Alice'),
        is_logged_in=True) if connected else None)
    monkeypatch.setattr(ui, 'current_identity', lambda: who)
    blocked_calls = []
    for path in ('frontend.recent_activity.agent_research',
                 'backend.data_sources.recent.search_topics',
                 'backend.recent_brief.build', 'src.service.search'):
        mock = Mock(side_effect=AssertionError('No provider call while toggling a favorite'))
        monkeypatch.setattr(path, mock)
        blocked_calls.append(mock)

    app = AppTest.from_file(str(ROOT / 'app.py')).run()
    assert not app.exception
    app.session_state['recent_result'] = report()
    app.run()
    assert not app.exception

    def favorites():
        if who is not None:
            return ProfileStore(ui.PROFILE_PATH).items(who, 'favorite')
        return app.session_state['profile_guest_data']['favorite']

    assert favorites() == []
    key = source_favorite_key(report()['events'][0])
    stars = [button for button in app.button if button.key and button.key.startswith('recent_favorite_')]
    assert len(stars) == 1  # Exact repeated events share one source card and one star.
    assert app.button(key=key).proto.help == 'Ajouter aux favoris'
    assert any('répétition' in caption.value for caption in app.caption)

    # Repeated clicks must alternate once, never cause a toggle/rerun loop.
    for index in range(6):
        app.button(key=key).click().run()
        assert not app.exception
        saved = index % 2 == 0
        assert len(favorites()) == int(saved)
        assert app.button(key=key).proto.help == ('Retirer des favoris' if saved else 'Ajouter aux favoris')
        app.run()
        assert not app.exception
        assert len(favorites()) == int(saved)
    app.button(key=key).click().run()
    assert len(favorites()) == 1

    item_id = favorites()[0]['id']
    app.radio(key='b_page').set_value('Favoris').run()
    assert not app.exception
    star = app.button(key='profile_remove_' + item_id)
    assert star.label == '★'
    assert star.proto.help == 'Retirer des favoris'
    assert not any(button.label in ('Retirer des favoris', '☆ Ajouter aux favoris')
                   for button in app.button)
    star.click().run()
    assert not app.exception
    assert favorites() == []
    assert any('Aucun favori' in item.value for item in app.info)

    app.radio(key='b_page').set_value('Recherche').run()
    assert not app.exception
    assert app.button(key=key).proto.help == 'Ajouter aux favoris'
    for mock in blocked_calls:
        mock.assert_not_called()
    if who is None:
        assert not ui.PROFILE_PATH.exists()
