from datetime import datetime, timedelta, timezone
import sqlite3
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from backend.profiles import ProfileStore, ProfileError, identity_from_claims
from frontend import profile as ui
from src.contracts import ROOT


def identity(subject):
    return identity_from_claims(dict(iss='https://accounts.google.com', sub=subject,
        email=subject + '@example.test', email_verified=True, name=subject), is_logged_in=True)


def result():
    return dict(topic='logement', start='2026-06-27', end='2026-09-27',
        collected_at='2026-09-27T12:00:00Z', datasets=[], limitations=['Test fictif'], events=[dict(
            title='Texte fictif', event_date='2026-09-20', event='Dépôt', category='procedure',
            decision=None, provider='senat', date_kind='publication',
            dossier_url='https://www.senat.fr/', source_url='https://www.senat.fr/',
            source_location='Test', retrieved_at='2026-09-27T12:00:00Z')])


def test_saved_items_persist_and_are_isolated_expire_and_delete(tmp_path):
    path = tmp_path / 'profiles.sqlite3'
    store = ProfileStore(path)
    alice, bob = identity('alice'), identity('bob')
    history = store.save_item(alice, 'history', result())
    favorite = store.save_item(alice, 'favorite', result()['events'][0])
    assert store.save_item(alice, 'favorite', result()['events'][0]) == favorite
    assert len(ProfileStore(path).items(alice, 'favorite')) == 1
    assert store.items(bob, 'history') == store.items(bob, 'favorite') == []
    store.remove_item(bob, 'favorite', favorite)
    assert len(store.items(alice, 'favorite')) == 1
    store.save_answers(alice, {'genre': 'Femme', 'logement': 'Locataire'})
    assert ProfileStore(path).answers(alice)['genre'] == 'Femme'
    assert store.answers(bob) == {}
    with sqlite3.connect(path) as db:
        db.execute('UPDATE saved_items SET saved_at=? WHERE item_id=?',
                   ((datetime.now(timezone.utc) - timedelta(days=8)).isoformat(), history))
    assert store.items(alice, 'history') == []
    assert len(store.items(alice, 'favorite')) == 1
    store.save_item(bob, 'history', result())
    store.delete(alice)
    assert store.answers(alice) == {}
    assert store.items(alice, 'favorite') == []
    assert len(store.items(bob, 'history')) == 1


def test_rejects_invalid_questionnaire_and_anonymous_storage(tmp_path):
    store = ProfileStore(tmp_path / 'profiles.sqlite3')
    for answers in ({'genre': 'invented'}, {'political_preference': 'x'}):
        with pytest.raises(ProfileError):
            store.save_answers(identity('alice'), answers)
    with pytest.raises(ProfileError):
        store.save_item(None, 'favorite', {})


def test_guest_can_search_save_and_reopen_without_database(monkeypatch, tmp_path):
    monkeypatch.setattr(ui, 'PROFILE_PATH', tmp_path / 'no_database.sqlite3')
    monkeypatch.setattr(ui, 'current_identity', lambda: None)
    fetch = Mock(return_value=result())
    monkeypatch.setattr('frontend.recent_activity.search_recent', fetch)
    app = AppTest.from_file(str(ROOT / 'app.py')).run()
    app.text_input(key='recent_topic').set_value('logement')
    next(b for b in app.button if b.label == 'Rechercher').click().run()
    app.button(key='recent_favorite_0').click().run()
    app.radio(key='b_page').set_value('Favoris').run()
    assert any(t.value == 'Texte fictif' for t in app.text)
    app.radio(key='b_page').set_value('Historique').run()
    next(b for b in app.button if b.label == 'Ouvrir les résultats').click().run()
    fetch.assert_called_once()
    app.radio(key='b_page').set_value('Mon profil').run()
    app.selectbox(key='profile_answer_logement').set_value('Locataire')
    next(b for b in app.button if b.label == 'Enregistrer mon profil').click().run()
    assert app.session_state['profile_guest_data']['answers']['logement'] == 'Locataire'
    assert not app.exception
    assert not ui.PROFILE_PATH.exists()
    other = AppTest.from_file(str(ROOT / 'app.py')).run()
    other.radio(key='b_page').set_value('Favoris').run()
    assert any('Aucun favori' in item.value for item in other.info)


def test_ui_history_favorites_and_questionnaire_without_ai(monkeypatch, tmp_path):
    alice = identity('alice')
    monkeypatch.setattr(ui, 'PROFILE_PATH', tmp_path / 'profiles.sqlite3')
    monkeypatch.setattr(ui, 'current_identity', lambda: alice)
    fetch = Mock(return_value=result())
    ai = Mock(side_effect=AssertionError('No AI'))
    monkeypatch.setattr('frontend.recent_activity.search_recent', fetch)
    monkeypatch.setattr('frontend.recent_activity.build', ai)
    app = AppTest.from_file(str(ROOT / 'app.py')).run()
    app.text_input(key='recent_topic').set_value('logement')
    next(b for b in app.button if b.label == 'Rechercher').click().run()
    assert not app.exception
    app.button(key='recent_favorite_0').click().run()
    store = ProfileStore(ui.PROFILE_PATH)
    assert len(store.items(alice, 'favorite')) == 1
    assert len(store.items(alice, 'history')) == 1
    app.radio(key='b_page').set_value('Historique').run()
    next(b for b in app.button if b.label == 'Ouvrir les résultats').click().run()
    assert not app.exception
    assert app.session_state['b_page'] == 'Recherche'
    fetch.assert_called_once_with('logement', months=3)
    ai.assert_not_called()
    app.radio(key='b_page').set_value('Favoris').run()
    next(b for b in app.button if b.label == 'Retirer des favoris').click().run()
    assert store.items(alice, 'favorite') == []
    app.radio(key='b_page').set_value('Mon profil').run()
    app.selectbox(key='profile_answer_genre').set_value('Femme')
    app.selectbox(key='profile_answer_emploi').set_value('Salarié(e)')
    next(b for b in app.button if b.label == 'Enregistrer mon profil').click().run()
    assert not app.exception
    assert store.answers(alice)['emploi'] == 'Salarié(e)'
    again = AppTest.from_file(str(ROOT / 'app.py')).run()
    again.radio(key='b_page').set_value('Mon profil').run()
    assert again.selectbox(key='profile_answer_genre').value == 'Femme'
    assert not again.exception
