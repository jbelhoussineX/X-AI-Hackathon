"""Account-scoped history and bookmarks; opening an entry never calls a provider."""
import hashlib

import streamlit as st

from backend.profiles import ProfileStore, ProfileError
from frontend import profile


_FAVORITE_STYLE = """
<style>
[class*="st-key-sedlex_favorite_"] button {
    background:transparent !important; border:0 !important; box-shadow:none !important;
    color:#FFFFFF !important; min-width:2rem; min-height:2rem;
    padding:0 .25rem !important;
}
[class*="st-key-sedlex_favorite_saved_"] button { color:#FFD43B !important; }
[class*="st-key-sedlex_favorite_"] button p {
    color:inherit !important; font-size:1.2rem !important; line-height:1; -webkit-text-stroke:.65px #161616;
}
[class*="st-key-sedlex_favorite_"] button:hover { background:transparent !important; }
[class*="st-key-sedlex_favorite_"] button:focus-visible {
    outline:2px solid #111111; outline-offset:3px;
}
</style>
"""


def account_store():
    identity = profile.current_identity()
    if identity is None:
        from frontend.guest import GuestStore
        return None, GuestStore(st.session_state)
    if st.session_state.get('_profile_deleted_for') == identity.user_id:
        return None
    return identity, ProfileStore(profile.PROFILE_PATH)


def remember(result):
    try:
        account = account_store()
        if account:
            identity, store = account
            store.save_item(identity, 'history', result)
    except (ProfileError, OSError):
        st.warning('Résultats disponibles, mais la sauvegarde dans l’historique a échoué.')


def _toggle_favorite(event):
    """A callback runs once before rendering; no second explicit rerun is needed."""
    try:
        account = account_store()
        if not account:
            return
        identity, store = account
        item_id = store.favorite_id(event)
        if any(item['id'] == item_id for item in store.items(identity, 'favorite')):
            store.remove_item(identity, 'favorite', item_id)
        else:
            store.save_item(identity, 'favorite', event)
    except (ProfileError, OSError):
        st.warning('Les favoris sont momentanément indisponibles.')


def favorite_button(event, *, key):
    try:
        account = account_store()
        if not account:
            return
        identity, store = account
        item_id = store.favorite_id(event)
        saved = any(item['id'] == item_id for item in store.items(identity, 'favorite'))
        st.markdown(_FAVORITE_STYLE, unsafe_allow_html=True)
        # Only a hash of the internal widget key enters the CSS class, never source text.
        suffix = hashlib.sha256(key.encode('utf-8')).hexdigest()[:16]
        state = 'saved' if saved else 'empty'
        with st.container(key=f'sedlex_favorite_{state}_{suffix}'):
            st.button('★', key=key,
                                help='Retirer des favoris' if saved else 'Ajouter aux favoris',
                                width='content', on_click=_toggle_favorite, args=(event,))
    except (ProfileError, OSError):
        st.warning('Les favoris sont momentanément indisponibles.')


def render_library(identity, kind):
    st.title('Historique' if kind == 'history' else 'Favoris')
    if kind == 'history':
        st.caption('Les sept derniers jours')
    try:
        if identity is None:
            from frontend.guest import GuestStore
            store = GuestStore(st.session_state)
        else:
            store = ProfileStore(profile.PROFILE_PATH)
        items = store.items(identity, kind)
        if not items:
            st.info('Aucune recherche enregistrée cette semaine.' if kind == 'history' else 'Aucun favori pour le moment.')
        for item in items:
            data = item['data']
            with st.container(border=True):
                st.text(data['topic'] if kind == 'history' else data['title'])
                st.caption('Enregistré le ' + item['saved_at'][:10])
                if kind == 'history':
                    st.caption(f"Du {data['start']} au {data['end']} · {len(data['events'])} événement(s)")
                    if st.button('Ouvrir les résultats', key='profile_open_' + item['id']):
                        for state_key in ('recent_brief', 'recent_brief_error', 'recent_categories', 'recent_order', 'recent_consent', 'recent_agent_error', 'recent_agent_consent'):
                            st.session_state.pop(state_key, None)
                        st.session_state.pop('recent_pending_search', None)
                        st.session_state['recent_result'] = data
                        st.session_state['recent_from_history'] = True
                        st.session_state['recent_topics'] = data.get('topics', [data['topic']])
                        st.session_state['recent_topic'] = ''
                        period = data.get('search_period')
                        if period:
                            st.session_state['recent_amount'] = period['amount']
                            st.session_state['recent_unit'] = period['unit']
                        st.session_state['b_next_page'] = 'Recherche'
                        st.rerun()
                else:
                    st.caption(data['event_date'])
                    from frontend.interface_b import url_publique
                    if url_publique(data.get('dossier_url')):
                        st.link_button('Lire la source officielle', data['dossier_url'])
                    favorite_button(data, key='profile_remove_' + item['id'])
                if kind == 'history' and st.button('Supprimer de l’historique', key='profile_remove_' + item['id']):
                    store.remove_item(identity, kind, item['id'])
                    st.rerun()
    except (ProfileError, OSError):
        st.error('Vos enregistrements sont momentanément indisponibles.')
