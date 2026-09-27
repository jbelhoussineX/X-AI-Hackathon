"""Recent official inventory events; deliberately separate from publication search."""
import json

import streamlit as st

from backend.data_sources.recent import search_recent


def render():
    with st.expander('Actualités récentes · 7 ou 30 jours', expanded=True):
        st.caption('Retrouver une évolution récente, même sur un texte ancien. '
                   'Consultation des données officielles sans appel IA ; distincte du rapport ci-dessous.')
        with st.form('recent_activity_form'):
            topic = st.text_input('Sujet des actualités', max_chars=300, key='recent_topic',
                                  placeholder='Ex. : logement')
            days = st.radio('Période des événements', [7, 30], index=1,
                            format_func=lambda value: f'{value} derniers jours', horizontal=True)
            submitted = st.form_submit_button('Consulter les actualités officielles')
        if submitted:
            st.session_state.pop('recent_result', None)
            try:
                with st.spinner('Consultation des inventaires et flux officiels…'):
                    st.session_state['recent_result'] = search_recent(topic, days)
            except ValueError:
                st.error('Indique un sujet précis de 3 à 300 caractères.')
        result = st.session_state.get('recent_result')
        if result is None:
            return
        st.write(result['topic'])
        st.caption(f"Événements du {result['start']} au {result['end']} inclus · "
                   f"Collecte : {result['collected_at']}")
        for dataset in result['datasets']:
            if dataset['status'] != 'ok':
                st.warning(f"Source {dataset['provider']} indisponible : résultats partiels.")
        if not result['events']:
            st.info('Aucun événement daté retrouvé dans cette fenêtre et ce corpus. '
                    'Cela ne signifie pas qu’il n’existe aucune actualité sur ce sujet.')
        for event in result['events']:
            with st.container(border=True):
                st.text(event['title'])
                st.text(f"{event['event_date']} — {event['event']}")
                if event['decision']:
                    st.text('Décision indiquée dans cet acte : ' + event['decision'])
                st.caption(f"Source : {event['provider']} · Champ de date : {event['date_kind']} · "
                           f"Collecté le {event['retrieved_at']}")
                if event.get('description'):
                    st.text(event['description'])
                st.link_button('Voir la page ou le document officiel', event['dossier_url'])
                st.link_button('Télécharger la source officielle', event['source_url'])
                st.caption('Localisation dans la source : ' + event['source_location'])
        for limitation in result['limitations']:
            st.caption(limitation)
        st.download_button('Exporter les actualités en JSON', json.dumps(result, ensure_ascii=False, indent=2),
                           file_name='actualites_officielles.json', mime='application/json', on_click='ignore')
