"""Remote profile features tolerate an extra column left by a local prototype."""
import sqlite3

import pytest

from backend.profiles import ProfileStore, identity_from_claims


def identity(subject):
    return identity_from_claims(
        {'iss': 'https://accounts.google.com', 'sub': subject,
         'email': f'{subject}@example.test', 'email_verified': True,
         'name': subject.title()}, is_logged_in=True)


@pytest.fixture
def legacy_database(tmp_path):
    """Create only synthetic data, with the old schema plus one nullable column."""
    path = tmp_path / 'profiles.sqlite3'
    alice = identity('alice')
    old_situation = '{"activities":["student"],"housing":"tenant","children":""}'
    with sqlite3.connect(path) as db:
        db.execute('''CREATE TABLE profiles (
            user_id TEXT PRIMARY KEY NOT NULL,
            email TEXT NOT NULL,
            display_name TEXT NOT NULL,
            topics_json TEXT NOT NULL,
            recent_months INTEGER NOT NULL CHECK(recent_months BETWEEN 1 AND 12),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )''')
        db.execute('INSERT INTO profiles VALUES (?, ?, ?, ?, ?, ?, ?)',
                   (alice.user_id, alice.email, 'Alice enregistrée', '["logement"]', 1,
                    '2026-09-01T00:00:00+00:00', '2026-09-01T00:00:00+00:00'))
        db.execute('ALTER TABLE profiles ADD COLUMN situation_json TEXT')
        db.execute('UPDATE profiles SET situation_json=? WHERE user_id=?',
                   (old_situation, alice.user_id))
    return path, alice, old_situation


def test_existing_profile_and_new_questionnaire_preserve_the_extra_column(legacy_database):
    path, alice, old_situation = legacy_database
    store = ProfileStore(path)

    profile = store.get_or_create(alice)
    assert profile['display_name'] == 'Alice enregistrée'
    assert profile['topics'] == ['logement']
    assert profile['recent_months'] == 1
    # The remote questionnaire is independent from the old, unused local field.
    assert store.answers(alice) == {}

    updated = store.update(alice, display_name='Alice modifiée',
                           topics=['transports'], recent_months=3)
    assert updated['display_name'] == 'Alice modifiée'
    assert updated['topics'] == ['transports']
    assert updated['recent_months'] == 3
    answers = {'emploi': 'Étudiant(e)', 'logement': 'Locataire'}
    store.save_answers(alice, answers)
    assert ProfileStore(path).answers(alice) == answers
    assert ProfileStore(path).get_or_create(alice)['topics'] == ['transports']

    with sqlite3.connect(path) as db:
        assert db.execute('SELECT situation_json FROM profiles WHERE user_id=?',
                          (alice.user_id,)).fetchone()[0] == old_situation


@pytest.mark.parametrize('operation', ['get_or_create', 'update'])
def test_new_profile_can_be_inserted_without_populating_the_extra_column(
        legacy_database, operation):
    path, alice, old_situation = legacy_database
    store = ProfileStore(path)
    bob = identity('bob')
    if operation == 'get_or_create':
        created = store.get_or_create(bob)
        assert created['topics'] == []
    else:
        created = store.update(bob, display_name='Bob', topics=['énergie'], recent_months=2)
        assert created['topics'] == ['énergie']
    assert created['user_id'] == bob.user_id
    assert store.get_or_create(bob)['email'] == bob.email
    store.save_answers(bob, {'enfants': 'Sans enfant'})
    assert store.answers(bob) == {'enfants': 'Sans enfant'}

    with sqlite3.connect(path) as db:
        assert db.execute('SELECT situation_json FROM profiles WHERE user_id=?',
                          (bob.user_id,)).fetchone()[0] is None
        assert db.execute('SELECT situation_json FROM profiles WHERE user_id=?',
                          (alice.user_id,)).fetchone()[0] == old_situation
