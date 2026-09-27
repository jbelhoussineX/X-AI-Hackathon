"""Optional Google identity and explicitly chosen, private local preferences.

Only Streamlit's server-side OIDC user supplies identity. Forms and URL parameters
never supply an owner, token or email. Anonymous searches remain available.
"""
import json
from pathlib import Path
import sqlite3

import streamlit as st

from backend.profiles import Identity, ProfileError, ProfileStore, identity_from_claims

PROFILE_PATH = Path(__file__).resolve().parents[1] / 'data/local/profiles.sqlite3'
_CLAIMS = ('iss', 'sub', 'email', 'email_verified', 'name')


def current_identity() -> Identity | None:
    """Read verified OIDC claims, never an unverified token or browser input."""
    if st.user.get('is_logged_in', False) is not True:
        return None
    return identity_from_claims({key: st.user.get(key) for key in _CLAIMS}, is_logged_in=True)


def clear_personal_session(state) -> None:
    # Both the ordinary search and recent-activity view hold personal selections.
    # Preserve the local attempt counter; changing identity isn't a cost reset.
    for key in list(state):
        if key.startswith(('b_', 'recent_', 'profile_')) and key != 'b_live_attempts':
            del state[key]


def initialize_identity() -> tuple[Identity | None, str | None]:
    """Clear another user's session data before any form widgets are instantiated."""
    error = None
    try:
        identity = current_identity()
    except ProfileError:
        identity = None
        error = 'Ce compte Google ne fournit pas une identité vérifiée utilisable. Reconnecte-toi.'
    owner = identity.user_id if identity else None
    previous = st.session_state.get('_profile_owner')
    if previous != owner:
        clear_personal_session(st.session_state)
        st.session_state.pop('_profile_deleted_for', None)
    st.session_state['_profile_owner'] = owner
    return identity, error


def begin_login() -> None:
    try:
        st.login('google')
    except Exception:
        # Never show provider exceptions: they can include configuration or tokens.
        st.error('La connexion Google est indisponible sur cette installation. '
                 'L’équipe doit vérifier sa configuration. La recherche sans compte reste disponible.')
        return
    st.stop()


def logout() -> None:
    clear_personal_session(st.session_state)
    try:
        st.logout()
    except Exception:
        st.error('La déconnexion n’a pas pu être confirmée. Ferme cet onglet puis réessaie.')
    st.stop()


def sidebar_account(identity: Identity | None, error: str | None) -> None:
    st.caption('MON COMPTE')
    if error:
        st.warning(error)
    if identity:
        st.text(identity.name or identity.email)
        if st.button('Se déconnecter', key='profile_logout'):
            logout()
    elif error:
        if st.button('Déconnecter ce compte', key='profile_invalid_logout'):
            logout()
    elif st.button('Se connecter avec Google', key='profile_login'):
        begin_login()


def prepare_topic(topic: str, months: int) -> None:
    """Prepare the current search after a click, without invoking any service."""
    state = st.session_state
    state['recent_topic'] = topic
    state['recent_unit'] = 'mois'
    state['recent_amount'] = months
    state['b_last'] = state['b_error'] = None
    for key in ('recent_result', 'recent_brief', 'recent_brief_error',
                'recent_categories', 'recent_order', 'recent_consent'):
        state.pop(key, None)
    state['b_next_page'] = 'Recherche'


def render_profile(identity: Identity | None, error: str | None) -> None:
    st.title('Mon profil')
    st.write('Retrouve tes sujets et choisis ta période de recherche habituelle.')
    if not identity:
        if error:
            st.warning(error)
        else:
            st.info('Connecte-toi avec Google depuis le menu pour enregistrer ton profil.')
        st.caption('Google partage ton identité de base : nom et adresse vérifiée. '
                   'Sed Lex ne demande aucun accès à tes emails ou fichiers Google. '
                   'La recherche reste accessible sans compte.')
        return
    if st.session_state.get('_profile_deleted_for') == identity.user_id:
        st.success('Ton profil enregistré a été supprimé. Reconnecte-toi pour en créer un nouveau.')
        return
    try:
        store = ProfileStore(PROFILE_PATH)
        profile = store.get_or_create(identity)
    except (OSError, sqlite3.Error, ProfileError):
        st.error('Ton profil enregistré est momentanément inaccessible. Tu peux continuer à rechercher.')
        return
    st.text('Compte Google : ' + profile['email'])
    st.caption('L’adresse est fournie par Google et ne se modifie pas dans Sed Lex.')
    with st.form('profile_form'):
        display_name = st.text_input('Nom d’affichage', value=profile['display_name'],
                                     max_chars=100, key='profile_display_name')
        topics_text = st.text_area('Mes sujets', value='\n'.join(profile['topics']),
                                   max_chars=807, key='profile_topics',
                                   help='Un sujet par ligne, 8 sujets maximum et 100 caractères par sujet.')
        months = st.number_input('Période des actualités (mois)', min_value=1, max_value=12,
                                 value=profile['recent_months'], step=1, key='profile_months')
        save = st.form_submit_button('Enregistrer mon profil', type='primary')
    if save:
        try:
            profile = store.update(identity, display_name=display_name,
                                   topics=[line.strip() for line in topics_text.splitlines() if line.strip()],
                                   recent_months=months)
            st.success('Profil enregistré. Aucune recherche n’a été lancée.')
        except ProfileError as exc:
            st.error(str(exc))
        except (OSError, sqlite3.Error):
            st.error('Enregistrement impossible pour le moment. Ton ancien profil est conservé.')
    if profile['topics']:
        st.subheader('Explorer un de mes sujets')
        st.caption('Le bouton prépare le formulaire. Tu lanceras ensuite la recherche toi-même.')
        for index, topic in enumerate(profile['topics']):
            with st.container(border=True):
                st.text(topic)
                if st.button('Préparer la recherche', key=f'profile_search_{index}'):
                    prepare_topic(topic, profile['recent_months'])
                    st.rerun()
    st.caption('Le profil est enregistré sur le serveur Sed Lex. Les sujets sont ceux que tu choisis ; '
               'aucune opinion politique n’est déduite. Ton identité Google n’est pas transmise au modèle IA. '
               'Les résultats restent limités à la session.')
    export = {key: profile[key] for key in ('display_name', 'email', 'topics', 'recent_months')}
    st.download_button('Exporter mon profil', json.dumps(export, ensure_ascii=False, indent=2),
                       file_name='profil_sed_lex.json', mime='application/json', on_click='ignore')
    with st.expander('Supprimer mon profil enregistré'):
        st.write('Supprime le nom d’affichage et les préférences enregistrés dans Sed Lex, puis déconnecte ce compte. '
                 'Ton compte Google reste intact. Une prochaine connexion pourra créer un nouveau profil vide.')
        confirmed = st.checkbox('Je confirme la suppression de mon profil Sed Lex', key='profile_delete_confirm')
        if st.button('Supprimer mon profil', disabled=not confirmed, key='profile_delete'):
            try:
                store.delete(identity)
            except (OSError, sqlite3.Error, ProfileError):
                st.error('Suppression impossible pour le moment. Réessaie plus tard.')
                return
            st.session_state['_profile_deleted_for'] = identity.user_id
            logout()
