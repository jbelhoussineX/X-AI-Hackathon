"""Profiles for server-validated Google identities, separate from shared watches.

Only ``identity_from_claims`` should construct identities for the application.
Its claims must come from Streamlit's authenticated ``st.user``, never a form,
query parameter, unverified token, or client-provided email. This module does
not authenticate a token and never stores tokens or Google's raw subject.
"""

import hashlib
import json
import os
import re
import sqlite3
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from pathlib import Path


GOOGLE_ISSUER = "https://accounts.google.com"
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+\Z")
_USER_ID = re.compile(r"[a-f0-9]{64}\Z")

QUESTIONNAIRE = {
    'genre': ('Genre', ['Femme', 'Homme', 'Autre']),
    'couple': ('Situation conjugale', ['Célibataire', 'En couple', 'Marié(e)', 'Pacsé(e)', 'Divorcé(e)', 'Veuf / veuve']),
    'emploi': ('Situation professionnelle', ['Salarié(e)', 'Entrepreneur / entrepreneuse', 'Indépendant(e)', 'Fonctionnaire', 'En recherche d’emploi', 'Étudiant(e)', 'Retraité(e)', 'Sans activité professionnelle', 'Autre']),
    'enfants': ('Enfants', ['Sans enfant', 'Avec enfant(s)']),
    'animaux': ('Animaux de compagnie', ['Sans animal', 'Avec animal / animaux']),
    'logement': ('Logement', ['Propriétaire', 'Locataire', 'Hébergé(e)', 'Logement de fonction', 'Autre']),
}
NO_ANSWER = 'Je préfère ne pas répondre'


class ProfileError(ValueError):
    """A safe, user-facing validation or persistence failure."""


@dataclass(frozen=True)
class Identity:
    user_id: str
    email: str = field(repr=False)
    name: str = field(repr=False)


def _text(value, *, maximum, label):
    if not isinstance(value, str) or _CONTROL.search(value):
        raise ProfileError(f"{label} invalide.")
    value = value.strip()
    if not value or len(value) > maximum:
        raise ProfileError(f"{label} requis, {maximum} caractères maximum.")
    return value


def _email(value):
    value = _text(value, maximum=254, label="Adresse Google")
    if not _EMAIL.fullmatch(value):
        raise ProfileError("Adresse Google invalide.")
    return value


def identity_from_claims(claims: Mapping, *, is_logged_in: bool) -> Identity | None:
    """Accept Google claims only after the OIDC provider validated the login."""
    if is_logged_in is not True:
        return None
    if not isinstance(claims, Mapping):
        raise ProfileError("Identité Google invalide. Reconnectez-vous.")
    issuer = claims.get("iss")
    subject = claims.get("sub")
    if (issuer not in (GOOGLE_ISSUER, "accounts.google.com")
            or not isinstance(subject, str) or not 1 <= len(subject) <= 255
            or not subject.isascii() or any(char.isspace() for char in subject)
            or _CONTROL.search(subject)):
        raise ProfileError("Identité Google invalide. Reconnectez-vous.")
    if claims.get("email_verified") is not True:
        raise ProfileError("Google doit confirmer une adresse e-mail vérifiée.")
    email = _email(claims.get("email"))
    raw_name = claims.get("name")
    name = _text(email.split("@", 1)[0] if raw_name is None else raw_name,
                 maximum=100, label="Nom d’affichage")
    user_id = hashlib.sha256(f"{GOOGLE_ISSUER}\0{subject}".encode("utf-8")).hexdigest()
    return Identity(user_id=user_id, email=email, name=name)


def _validate_identity(identity):
    # Internal callers must pass an authenticated Identity, not arbitrary IDs.
    if not isinstance(identity, Identity) or not isinstance(identity.user_id, str):
        raise ProfileError("Connexion Google requise.")
    if not _USER_ID.fullmatch(identity.user_id):
        raise ProfileError("Identité Google invalide. Reconnectez-vous.")
    _email(identity.email)
    _text(identity.name, maximum=100, label="Nom d’affichage")


def _preferences(display_name, topics, recent_months):
    display_name = _text(display_name, maximum=100, label="Nom d’affichage")
    if not isinstance(topics, list) or len(topics) > 8:
        raise ProfileError("Choisissez au maximum huit sujets.")
    normalized = [_text(topic, maximum=100, label="Sujet") for topic in topics]
    # Repeated input does not create an inferred preference or duplicate entry.
    normalized = list(dict.fromkeys(normalized))
    if type(recent_months) is not int or not 1 <= recent_months <= 12:
        raise ProfileError("La période doit être comprise entre 1 et 12 mois.")
    return display_name, normalized, recent_months


def _now():
    return datetime.now(timezone.utc).isoformat()


def _profile(row):
    if row is None:
        raise ProfileError("Profil introuvable.")
    try:
        topics = json.loads(row["topics_json"])
    except (TypeError, ValueError) as exc:
        raise ProfileError("Le profil enregistré est illisible.") from exc
    display_name, topics, recent_months = _preferences(
        row["display_name"], topics, row["recent_months"])
    return {
        "user_id": row["user_id"], "email": row["email"],
        "display_name": display_name, "topics": topics,
        "recent_months": recent_months,
        "created_at": row["created_at"], "updated_at": row["updated_at"],
    }


class ProfileStore:
    """Local persistence scoped to the authenticated identity on every operation."""

    def __init__(self, path):
        self.path = Path(path)
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            # POSIX private permissions; Windows uses the directory's inherited ACLs.
            descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
            os.close(descriptor)
            self.path.chmod(0o600)
        except OSError as exc:
            raise ProfileError("Le stockage des profils est indisponible.") from exc
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS profiles (
                    user_id TEXT PRIMARY KEY NOT NULL,
                    email TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    topics_json TEXT NOT NULL,
                    recent_months INTEGER NOT NULL CHECK(recent_months BETWEEN 1 AND 12),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            db.execute('''CREATE TABLE IF NOT EXISTS questionnaires (
                user_id TEXT PRIMARY KEY, answers_json TEXT NOT NULL)''')
            db.execute('''CREATE TABLE IF NOT EXISTS saved_items (
                user_id TEXT NOT NULL, kind TEXT NOT NULL, item_id TEXT NOT NULL,
                saved_at TEXT NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY(user_id, kind, item_id))''')

    @contextmanager
    def _connect(self):
        db = None
        try:
            db = sqlite3.connect(self.path, timeout=10)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                yield db
        except sqlite3.Error as exc:
            raise ProfileError("Le stockage des profils est indisponible.") from exc
        finally:
            if db is not None:
                db.close()

    def get_or_create(self, identity: Identity) -> dict:
        _validate_identity(identity)
        timestamp = _now()
        with self._connect() as db:
            db.execute("""
                INSERT INTO profiles
                    (user_id, email, display_name, topics_json, recent_months, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    email=excluded.email,
                    updated_at=CASE WHEN profiles.email != excluded.email
                        THEN excluded.updated_at ELSE profiles.updated_at END
            """, (identity.user_id, identity.email, identity.name, "[]", 2,
                  timestamp, timestamp))
            return _profile(db.execute(
                "SELECT * FROM profiles WHERE user_id=?", (identity.user_id,)).fetchone())

    def update(self, identity: Identity, *, display_name: str,
               topics: list[str], recent_months: int) -> dict:
        _validate_identity(identity)
        display_name, topics, recent_months = _preferences(display_name, topics, recent_months)
        timestamp = _now()
        with self._connect() as db:
            db.execute("""
                INSERT INTO profiles
                    (user_id, email, display_name, topics_json, recent_months, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    email=excluded.email, display_name=excluded.display_name,
                    topics_json=excluded.topics_json, recent_months=excluded.recent_months,
                    updated_at=excluded.updated_at
            """, (identity.user_id, identity.email, display_name,
                  json.dumps(topics, ensure_ascii=False), recent_months, timestamp, timestamp))
            return _profile(db.execute(
                "SELECT * FROM profiles WHERE user_id=?", (identity.user_id,)).fetchone())

    def delete(self, identity: Identity) -> None:
        _validate_identity(identity)
        with self._connect() as db:
            db.execute("DELETE FROM profiles WHERE user_id=?", (identity.user_id,))
            db.execute('DELETE FROM questionnaires WHERE user_id=?', (identity.user_id,))
            db.execute('DELETE FROM saved_items WHERE user_id=?', (identity.user_id,))

    def answers(self, identity: Identity) -> dict:
        _validate_identity(identity)
        with self._connect() as db:
            row = db.execute('SELECT answers_json FROM questionnaires WHERE user_id=?', (identity.user_id,)).fetchone()
        return json.loads(row[0]) if row else {}

    def save_answers(self, identity: Identity, answers: dict) -> None:
        _validate_identity(identity)
        if not isinstance(answers, dict) or any(
            key not in QUESTIONNAIRE or value not in [NO_ANSWER, *QUESTIONNAIRE[key][1]]
            for key, value in answers.items()
        ):
            raise ProfileError('Réponses au questionnaire invalides.')
        with self._connect() as db:
            db.execute('INSERT OR REPLACE INTO questionnaires VALUES (?, ?)',
                       (identity.user_id, json.dumps(answers, ensure_ascii=False)))

    @staticmethod
    def favorite_id(event: dict) -> str:
        fields = {key: event.get(key) for key in ('id', 'provider', 'dossier_url', 'event_date', 'event', 'title', 'source_location')}
        return hashlib.sha256(json.dumps(fields, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def save_item(self, identity: Identity, kind: str, payload: dict) -> str:
        _validate_identity(identity)
        if kind not in ('history', 'favorite') or not isinstance(payload, dict):
            raise ProfileError('Enregistrement invalide.')
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        if len(encoded.encode('utf-8')) > 2_000_000:
            raise ProfileError('Ce résultat est trop volumineux pour être enregistré.')
        item_id = uuid4().hex if kind == 'history' else self.favorite_id(payload)
        with self._connect() as db:
            self._prune_history(db)
            db.execute('INSERT OR IGNORE INTO saved_items VALUES (?, ?, ?, ?, ?)',
                       (identity.user_id, kind, item_id, _now(), encoded))
        return item_id

    @staticmethod
    def _prune_history(db):
        # Expiration globale au prochain accès au stockage, sans tâche planifiée.
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        db.execute("DELETE FROM saved_items WHERE kind='history' AND saved_at < ?", (cutoff,))

    def items(self, identity: Identity, kind: str) -> list[dict]:
        _validate_identity(identity)
        if kind not in ('history', 'favorite'):
            raise ProfileError('Collection invalide.')
        with self._connect() as db:
            self._prune_history(db)
            rows = db.execute('SELECT * FROM saved_items WHERE user_id=? AND kind=? ORDER BY saved_at DESC, item_id',
                              (identity.user_id, kind)).fetchall()
        return [dict(id=row['item_id'], saved_at=row['saved_at'], data=json.loads(row['payload'])) for row in rows]

    def remove_item(self, identity: Identity, kind: str, item_id: str) -> None:
        _validate_identity(identity)
        with self._connect() as db:
            db.execute('DELETE FROM saved_items WHERE user_id=? AND kind=? AND item_id=?',
                       (identity.user_id, kind, item_id))
