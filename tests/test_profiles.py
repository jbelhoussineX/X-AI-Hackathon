"""Offline identity boundaries, private profile storage, and account isolation."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError

import pytest

from backend.profiles import Identity, ProfileError, ProfileStore, identity_from_claims


def claims(subject="google-subject-alice", email="alice@example.org", **overrides):
    return {
        "iss": "https://accounts.google.com", "sub": subject,
        "email": email, "email_verified": True, "name": "Alice",
        **overrides,
    }


def identity(subject="google-subject-alice", email="alice@example.org", **overrides):
    return identity_from_claims(claims(subject, email, **overrides), is_logged_in=True)


@pytest.fixture
def store(tmp_path):
    return ProfileStore(tmp_path / "local" / "profiles.sqlite3")


def test_anonymous_claims_cannot_select_or_create_an_identity():
    assert identity_from_claims(claims(), is_logged_in=False) is None
    assert identity_from_claims({}, is_logged_in=False) is None
    assert identity_from_claims(claims(), is_logged_in="true") is None


@pytest.mark.parametrize("overrides", [
    {"iss": "https://accounts.google.com.attacker.example"},
    {"iss": "https://another-provider.example"},
    {"iss": None}, {"sub": ""}, {"sub": None}, {"sub": "a" * 256},
    {"sub": "subject\x00tail"}, {"sub": " subject"}, {"sub": "énonce"},
    {"email_verified": False}, {"email_verified": "true"}, {"email_verified": 1},
    {"email_verified": None}, {"email": None}, {"email": "alice"},
    {"email": "a@b@c.fr"}, {"email": "alice\n@example.org"},
    {"email": "a" * 255 + "@example.org"},
    {"name": "a" * 101}, {"name": "Alice\nAdmin"}, {"name": False}, {"name": ""},
])
def test_invalid_authenticated_claims_fail_closed(overrides):
    with pytest.raises(ProfileError):
        identity_from_claims(claims(**overrides), is_logged_in=True)


def test_logged_in_requires_claim_mapping():
    with pytest.raises(ProfileError):
        identity_from_claims(None, is_logged_in=True)


def test_issuer_alias_and_email_changes_keep_same_subject_identity():
    alice = identity()
    moved = identity(email="new@example.org", iss="accounts.google.com")
    assert alice.user_id == moved.user_id
    assert len(alice.user_id) == 64
    assert alice.user_id != claims()["sub"]
    assert identity("another-subject").user_id != alice.user_id
    with pytest.raises(FrozenInstanceError):
        alice.email = "changed@example.org"


def test_missing_google_name_can_use_verified_address():
    data = claims()
    del data["name"]
    assert identity_from_claims(data, is_logged_in=True).name == "alice"


def test_new_profile_has_no_inferred_interests_and_survives_restart(store):
    alice = identity()
    profile = store.get_or_create(alice)
    assert set(profile) == {
        "user_id", "email", "display_name", "topics", "recent_months", "created_at", "updated_at",
    }
    assert profile["topics"] == []
    assert profile["recent_months"] == 2
    assert profile["display_name"] == "Alice"
    assert profile["created_at"] == profile["updated_at"]
    assert ProfileStore(store.path).get_or_create(alice) == profile
    assert store.path.stat().st_mode & 0o777 == 0o600


def test_two_accounts_are_isolated_and_deletion_does_not_affect_other(store):
    alice = identity()
    bob = identity("google-subject-bob", "bob@example.org", name="Bob")
    alice_profile = store.update(alice, display_name="Ali", topics=["Logement"], recent_months=1)
    bob_profile = store.update(bob, display_name="Bob", topics=["Transports"], recent_months=6)
    assert store.get_or_create(alice) == alice_profile
    assert store.get_or_create(bob) == bob_profile
    store.delete(alice)
    store.delete(alice)  # Idempotent and still scoped to Alice.
    assert store.get_or_create(bob) == bob_profile
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT user_id FROM profiles").fetchall() == [(bob.user_id,)]
    assert store.get_or_create(alice)["topics"] == []


def test_same_email_is_not_an_account_identifier(store):
    first = identity("subject-one", "same@example.org")
    second = identity("subject-two", "same@example.org")
    store.update(first, display_name="First", topics=["Sujet privé"], recent_months=3)
    assert store.get_or_create(second)["topics"] == []
    assert first.user_id != second.user_id


def test_verified_email_change_keeps_custom_name_and_preferences(store):
    alice = identity()
    old = store.update(alice, display_name="Nom choisi", topics=["Énergie"], recent_months=12)
    changed = identity(email="new-address@example.org", name="Nouveau nom Google")
    profile = store.get_or_create(changed)
    assert profile["email"] == changed.email
    assert profile["topics"] == old["topics"]
    assert profile["display_name"] == "Nom choisi"
    assert profile["recent_months"] == 12
    assert profile["created_at"] == old["created_at"]


@pytest.mark.parametrize("bad", [
    {"display_name": ""}, {"display_name": "a" * 101},
    {"display_name": "Alice\x00"}, {"display_name": None},
    {"topics": ["a"] * 9}, {"topics": "Logement"},
    {"topics": [""]}, {"topics": ["a" * 101]}, {"topics": [3]},
    {"topics": ["Sujet\nAutre"]}, {"recent_months": 0},
    {"recent_months": 13}, {"recent_months": True},
    {"recent_months": 2.0}, {"recent_months": "2"},
])
def test_invalid_preferences_do_not_mutate_profile(store, bad):
    alice = identity()
    before = store.get_or_create(alice)
    preferences = {"display_name": "Alice", "topics": ["Logement"], "recent_months": 2}
    with pytest.raises(ProfileError):
        store.update(alice, **(preferences | bad))
    assert store.get_or_create(alice) == before


def test_preferences_are_explicit_bounded_and_preserve_sql_as_data(store):
    injection = "x'); DROP TABLE profiles; --"
    profile = store.update(identity(), display_name=injection,
                           topics=["  Énergie  ", injection, "Énergie"], recent_months=1)
    assert profile["display_name"] == injection
    assert profile["topics"] == ["Énergie", injection]
    assert store.get_or_create(identity()) == profile
    assert store.get_or_create(identity("other"))["topics"] == []


@pytest.mark.parametrize("untrusted", [
    None, "subject", {"user_id": "a" * 64},
    Identity("' OR 1=1 --", "alice@example.org", "Alice"),
    Identity("a" * 64, "not-an-email", "Alice"),
])
def test_storage_operations_require_well_formed_server_identity(store, untrusted):
    for operation in (store.get_or_create, store.delete):
        with pytest.raises(ProfileError):
            operation(untrusted)
    with pytest.raises(ProfileError):
        store.update(untrusted, display_name="Alice", topics=[], recent_months=2)


def test_concurrent_first_login_creates_one_complete_profile(store):
    alice = identity()
    with ThreadPoolExecutor(max_workers=6) as pool:
        profiles = list(pool.map(lambda _: ProfileStore(store.path).get_or_create(alice), range(18)))
    assert all(profile == profiles[0] for profile in profiles)
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT count(*) FROM profiles").fetchone()[0] == 1


def test_no_raw_subject_or_tokens_are_persisted(store):
    data = claims()
    data.update(access_token="never-persist-access", id_token="never-persist-id")
    alice = identity_from_claims(data, is_logged_in=True)
    store.get_or_create(alice)
    content = store.path.read_bytes()
    assert data["sub"].encode() not in content
    assert data["access_token"].encode() not in content
    assert data["id_token"].encode() not in content


def test_storage_failure_is_safe_and_does_not_echo_identity(tmp_path):
    invalid_path = tmp_path / "directory"
    invalid_path.mkdir()
    with pytest.raises(ProfileError, match="stockage des profils") as error:
        ProfileStore(invalid_path)
    assert str(invalid_path) not in str(error.value)
