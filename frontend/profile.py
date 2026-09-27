"""Profile preferences for the current browser session, without sign-in."""
from pathlib import Path
import sqlite3

import streamlit as st

from backend.profiles import Identity, ProfileError, ProfileStore, QUESTIONNAIRE, NO_ANSWER

PROFILE_PATH = Path(__file__).resolve().parents[1] / 'data/local/profiles.sqlite3'


def current_identity() -> Identity | None:
    """Authentication is disabled; never read OAuth claims or credentials."""
    return None


def clear_personal_session(state) -> None:
    # Both the ordinary search and recent-activity view hold personal selections.
    # Preserve the local attempt counter; changing identity isn't a cost reset.
    for key in list(state):
        if key.startswith(('b_', 'recent_', 'profile_')) and key != 'b_live_attempts':
            del state[key]


def initialize_identity() -> tuple[Identity | None, str | None]:
    """Clear another user's session data before any form widgets are instantiated."""
    error = None
    identity = current_identity()
    owner = identity.user_id if identity else None
    previous = st.session_state.get('_profile_owner')
    if previous != owner:
        clear_personal_session(st.session_state)
        st.session_state.pop('_profile_deleted_for', None)
    st.session_state['_profile_owner'] = owner
    return identity, error


def render_profile(identity: Identity | None, error: str | None) -> None:
    st.title('Mon profil')
    st.caption('Vos réponses facultatives adaptent les prochaines synthèses et l’ordre des textes. Elles sont transmises à l’IA lors d’une recherche, sans votre nom. « Autre » et les réponses non renseignées sont ignorés.')
    if identity and st.session_state.get('_profile_deleted_for') == identity.user_id:
        st.success('Ce profil enregistré est indisponible.')
        return
    try:
        if identity:
            store = ProfileStore(PROFILE_PATH)
        else:
            from frontend.guest import GuestStore
            store = GuestStore(st.session_state)
        profile = store.get_or_create(identity)
        answers = store.answers(identity)
    except (OSError, sqlite3.Error, ProfileError):
        st.error('Ton profil enregistré est momentanément inaccessible. Tu peux continuer à rechercher.')
        return
    with st.form('profile_form'):
        display_name = st.text_input('Nom d’affichage', value=profile['display_name'],
                                     max_chars=100, key='profile_display_name')
        selections = {}
        left, right = st.columns(2)
        for index, (key, (label, choices)) in enumerate(QUESTIONNAIRE.items()):
            options = [NO_ANSWER, *choices]
            value = answers.get(key, NO_ANSWER)
            selections[key] = (left if index % 2 == 0 else right).selectbox(
                label, options, index=options.index(value) if value in options else 0, key='profile_answer_' + key)
        months = st.number_input('Période des actualités (mois)', min_value=1, max_value=12,
                                 value=profile['recent_months'], step=1, key='profile_months')
        save = st.form_submit_button('Enregistrer mon profil', type='primary')
    if save:
        try:
            profile = store.update(identity, display_name=display_name,
                                   topics=profile['topics'],
                                   recent_months=months)
            store.save_answers(identity, selections)
            st.session_state['recent_amount'] = months
            st.session_state['recent_unit'] = 'mois'
            st.success('Profil enregistré.')
        except ProfileError as exc:
            st.error(str(exc))
        except (OSError, sqlite3.Error):
            st.error('Enregistrement impossible pour le moment. Ton ancien profil est conservé.')
