"""Recent official inventory events; deliberately separate from publication search."""
import json
import os

import streamlit as st

from backend.data_sources.recent import search_recent
from backend.recent_brief import build, BriefError

CATEGORIES = {'procedure': 'Étape législative', 'publication': 'Publication parlementaire',
              'amendement': 'Amendement', 'debat': 'Débat / intervention', 'actualite': 'Actualité institutionnelle'}


def render(*, allow_ai=False):
    with st.expander('Actualités récentes · période au choix', expanded=True):
        st.caption('Retrouver une évolution récente, même sur un texte ancien. '
                   'Collecte officielle sans IA, puis synthèse Pipelex facultative des nouveautés.')
        with st.form('recent_activity_form'):
            topic = st.text_input('Sujet des actualités', max_chars=300, key='recent_topic',
                                  placeholder='Ex. : logement')
            unit = st.selectbox('Unité de la période', ['mois', 'jours'], key='recent_unit')
            amount = st.number_input('Durée de la recherche', min_value=1, max_value=90,
                                     value=3, step=1, key='recent_amount',
                                     help='1 à 12 mois calendaires ou 1 à 90 jours. Aujourd’hui inclus.')
            submitted = st.form_submit_button('Consulter les actualités officielles')
        if submitted:
            st.session_state.pop('recent_result', None)
            st.session_state.pop('recent_brief', None)
            st.session_state.pop('recent_brief_error', None)
            try:
                with st.spinner('Consultation des inventaires et flux officiels…'):
                    st.session_state['recent_result'] = (search_recent(topic, months=int(amount))
                                                       if unit == 'mois' else search_recent(topic, int(amount)))
            except ValueError:
                st.error('Indique un sujet de 3 à 300 caractères et une durée de 1 à 12 mois ou de 1 à 90 jours.')
        result = st.session_state.get('recent_result')
        if result is None:
            return
        st.write(result['topic'])
        st.caption(f"Événements du {result['start']} au {result['end']} inclus · "
                   f"Collecte : {result['collected_at']}")
        for dataset in result['datasets']:
            if dataset['status'] != 'ok':
                st.warning(f"Source {dataset['provider']} indisponible : résultats partiels.")
            elif dataset.get('latest_session_date'):
                st.caption(f"{dataset['provider']} : dernière séance repérée dans l’index, {dataset['latest_session_date']}.")
        if not result['events']:
            st.info('Aucun événement daté retrouvé dans cette fenêtre et ce corpus. '
                    'Cela ne signifie pas qu’il n’existe aucune actualité sur ce sujet.')
        else:
            engine = os.environ.get('PIPELEX_EXECUTION_MODE', 'hosted')
            provider = 'API Pipelex' if engine == 'hosted' else 'Pipelex local et OpenAI'
            consent = st.checkbox(f'Autoriser une synthèse IA via {provider} (crédits fournisseur)',
                                  key='recent_consent', disabled=not allow_ai)
            if not allow_ai:
                st.caption('Passe en Recherche réelle · Pipelex pour activer la synthèse. La collecte reste sans IA.')
            enabled = os.environ.get('ENABLE_PIPELEX_CALLS', '').lower() == 'true'
            if st.button('Synthétiser les nouveautés avec Pipelex', disabled=not (consent and enabled and allow_ai),
                         key='recent_summarize'):
                st.session_state.pop('recent_brief', None)
                st.session_state.pop('recent_brief_error', None)
                try:
                    with st.spinner('Lecture des sources et synthèse des nouveautés…'):
                        st.session_state['recent_brief'] = build(result)
                except BriefError as exc:
                    st.session_state['recent_brief_error'] = str(exc)
                except Exception:
                    st.session_state['recent_brief_error'] = (
                        'Synthèse indisponible : erreur technique ou fournisseur. Vérifie les accès et '
                        'l’activité du fournisseur avant de relancer ; un délai local n’annule pas '
                        'forcément une génération distante. Aucune relance automatique.')
            if st.session_state.get('recent_brief_error'):
                st.error(st.session_state['recent_brief_error'])
            brief = st.session_state.get('recent_brief')
            if brief:
                st.subheader('Synthèse des nouveautés')
                if brief.get('duplicate_count'):
                    st.info(f"{brief['duplicate_count']} répétition(s) écartée(s). Une synthèse par événement est conservée.")
                for item in brief['items']:
                    st.caption(f"{CATEGORIES.get(item['category'], item['category'])} · {item['event_date']} · {item['date_kind']}")
                    st.text(item['summary'])
                    st.text('Extrait vérifié : ' + item['excerpt'])
                    st.link_button('Lire la source de cette synthèse', item['url'])
                if not brief['items']:
                    st.info('Aucune synthèse suffisamment étayée dans le corpus disponible.')
                with st.expander('Limites de la synthèse'):
                    for limit in brief['limitations']:
                        st.text(limit)
                st.download_button('Exporter la synthèse récente', json.dumps(brief, ensure_ascii=False, indent=2),
                                   file_name='synthese_recente.json', mime='application/json', on_click='ignore')
        for event in result['events']:
            with st.container(border=True):
                st.text(event['title'])
                st.caption(CATEGORIES.get(event.get('category', 'procedure'), 'Publication officielle'))
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
