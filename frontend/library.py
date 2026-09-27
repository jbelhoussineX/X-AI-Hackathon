"""Account-scoped history and bookmarks; opening an entry never calls a provider."""
import json

import streamlit as st

from backend.profiles import ProfileStore, ProfileError
from frontend import profile


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


def favorite_button(event, *, key):
    try:
        account = account_store()
        if not account:
            return
        identity, store = account
        item_id = store.favorite_id(event)
        saved = any(item['id'] == item_id for item in store.items(identity, 'favorite'))
        if st.button('Retirer des favoris' if saved else '☆ Ajouter aux favoris', key=key):
            if saved:
                store.remove_item(identity, 'favorite', item_id)
            else:
                store.save_item(identity, 'favorite', event)
            st.rerun()
    except (ProfileError, OSError):
        st.warning('Les favoris sont momentanément indisponibles.')


def render_library(identity, kind):
    st.title('Historique' if kind == 'history' else 'Favoris')
    if identity is None:
        st.caption('Mode invité : conservé uniquement dans cette session. Exportez vos données pour les garder.')
    st.caption('Recherches des sept derniers jours. Ouvrir un résultat ne relance ni la collecte ni l’IA.'
               if kind == 'history' else 'Vos résultats enregistrés, conservés jusqu’à leur retrait.')
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
                        for state_key in ('recent_brief', 'recent_brief_error', 'recent_categories', 'recent_order', 'recent_consent'):
                            st.session_state.pop(state_key, None)
                        st.session_state['recent_result'] = data
                        st.session_state['recent_from_history'] = True
                        st.session_state['recent_topic'] = data['topic']
                        st.session_state['b_next_page'] = 'Recherche'
                        st.rerun()
                else:
                    st.caption(f"{data['event_date']} · {data['event']}")
                    from frontend.interface_b import url_publique
                    if url_publique(data.get('dossier_url')):
                        st.link_button('Lire la source officielle', data['dossier_url'])
                if st.button('Supprimer de l’historique' if kind == 'history' else 'Retirer des favoris', key='profile_remove_' + item['id']):
                    store.remove_item(identity, kind, item['id'])
                    st.rerun()
        if items:
            st.download_button('Exporter', json.dumps(items, ensure_ascii=False, indent=2),
                               file_name=kind + '.json', mime='application/json', on_click='ignore')
    except (ProfileError, OSError):
        st.error('Vos enregistrements sont momentanément indisponibles.')
