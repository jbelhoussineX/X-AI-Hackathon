"""Recent official inventory events; deliberately separate from publication search."""
import json
import os
from datetime import date
from html import escape

import streamlit as st

from backend.data_sources.recent import search_recent
from backend.recent_brief import build, BriefError

CATEGORIES = {'procedure': 'Étape législative', 'publication': 'Publication parlementaire',
              'amendement': 'Amendement', 'debat': 'Débat / intervention', 'actualite': 'Actualité institutionnelle'}


def date_label(value):
    try:
        return date.fromisoformat(value).strftime('%d/%m/%Y')
    except (ValueError, TypeError):
        return 'Date non renseignée'


def render(*, allow_ai=False):
    with st.container():
        with st.form('recent_activity_form'):
            topic = st.text_input('Sujet des actualités', max_chars=300, key='recent_topic',
                                  placeholder='Ex. : logement, énergie, transports…')
            period, units = st.columns([1, 1])
            amount = period.number_input('Sur les derniers…', min_value=1, max_value=90,
                                     value=3, step=1, key='recent_amount',
                                     help='1 à 12 mois calendaires ou 1 à 90 jours. Aujourd’hui inclus.')
            unit = units.selectbox('Unité de la période', ['mois', 'jours'], key='recent_unit')
            submitted = st.form_submit_button('Rechercher', type='primary', width='stretch')
        if submitted:
            st.session_state.pop('recent_from_history', None)
            st.session_state.pop('recent_categories', None)
            st.session_state.pop('recent_result', None)
            st.session_state.pop('recent_brief', None)
            st.session_state.pop('recent_brief_error', None)
            try:
                with st.spinner('Consultation des inventaires et flux officiels…'):
                    st.session_state['recent_result'] = (search_recent(topic, months=int(amount))
                                                       if unit == 'mois' else search_recent(topic, int(amount)))
                from frontend.library import remember
                remember(st.session_state['recent_result'])
            except ValueError:
                st.error('Indique un sujet de 3 à 300 caractères et une durée de 1 à 12 mois ou de 1 à 90 jours.')
        result = st.session_state.get('recent_result')
        if result is None:
            return
        st.divider()
        st.subheader('Consulter les résultats')
        if st.session_state.get('recent_from_history'):
            st.info('Recherche enregistrée : les données datent de cette collecte. Cliquez sur Rechercher pour les actualiser avant une nouvelle synthèse.')
        st.text(result['topic'])
        st.caption(f"Du {date_label(result['start'])} au {date_label(result['end'])} inclus · "
                   'Résultats de la dernière recherche validée')
        total, sources = st.columns(2)
        total.metric('Événements retrouvés', len(result['events']))
        sources.metric('Sources disponibles', f"{sum(d['status'] == 'ok' for d in result['datasets'])} / {len(result['datasets'])}")
        for dataset in result['datasets']:
            if dataset['status'] != 'ok':
                st.warning(f"Source {dataset['provider']} indisponible : résultats partiels.")
        if not result['events']:
            st.info('Aucun événement daté retrouvé dans cette fenêtre et ce corpus. '
                    'Cela ne signifie pas qu’il n’existe aucune actualité sur ce sujet.')
        else:
            st.subheader('Comprendre les nouveautés')
            st.caption('Facultatif · La synthèse porte sur la collecte complète, dans les limites du corpus lu. Les filtres ci-dessous ne la modifient pas.')
            engine = os.environ.get('PIPELEX_EXECUTION_MODE', 'hosted')
            provider = 'API Pipelex' if engine == 'hosted' else 'Pipelex local et OpenAI'
            consent = st.checkbox(f'Autoriser une synthèse IA via {provider} (crédits fournisseur)',
                                  key='recent_consent', disabled=not allow_ai)
            if not allow_ai:
                st.caption('Sélectionnez « Avec synthèse » dans le menu de gauche pour activer cette option.')
            enabled = os.environ.get('ENABLE_PIPELEX_CALLS', '').lower() == 'true'
            if allow_ai and not enabled:
                st.info('La synthèse IA est désactivée sur ce serveur. Les sources restent consultables ci-dessous.')
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
                    st.caption(f"{CATEGORIES.get(item['category'], item['category'])} · {date_label(item['event_date'])}")
                    st.markdown(f'<div class="safe-text">{escape(item["summary"])}</div>', unsafe_allow_html=True)
                    st.text('Extrait vérifié : ' + item['excerpt'])
                    st.link_button('Lire la source de cette synthèse', item['url'])
                if not brief['items']:
                    st.info('Aucune synthèse suffisamment étayée dans le corpus disponible.')
                with st.expander('Limites de la synthèse'):
                    for limit in brief['limitations']:
                        st.text(limit)
                st.download_button('Exporter la synthèse récente', json.dumps(brief, ensure_ascii=False, indent=2),
                                   file_name='synthese_recente.json', mime='application/json', on_click='ignore')
        st.subheader('Événements et sources')
        categories = sorted({event.get('category', 'procedure') for event in result['events']})
        selected = st.multiselect('Filtrer par type d’événement', categories,
                                  format_func=lambda value: CATEGORIES.get(value, value),
                                  placeholder='Tous les types', key='recent_categories')
        order = st.selectbox('Ordre des événements', ['Plus récents d’abord', 'Plus anciens d’abord'], key='recent_order')
        events = [event for event in result['events'] if not selected or event.get('category', 'procedure') in selected]
        events = sorted(events, key=lambda event: event['event_date'], reverse=order == 'Plus récents d’abord')
        st.caption(f"{len(events)} événement(s) affiché(s) sur {len(result['events'])}. Filtres sans nouvel appel réseau ou IA.")
        for index, event in enumerate(events):
            with st.container(border=True):
                st.caption(f"{date_label(event['event_date'])} · {CATEGORIES.get(event.get('category', 'procedure'), 'Publication officielle')}")
                st.markdown(f'<div class="doc-title">{escape(event["title"])}</div>', unsafe_allow_html=True)
                st.text(event['event'])
                if event['decision']:
                    st.text('Décision indiquée dans cet acte : ' + event['decision'])
                st.link_button('Lire la source officielle', event['dossier_url'])
                from frontend.library import favorite_button
                favorite_button(event, key=f'recent_favorite_{index}')
                with st.expander('Détails et provenance'):
                    if event.get('description'):
                        st.text(event['description'])
                    st.caption(f"Source : {event['provider']} · Nature de la date : {event['date_kind']} · "
                               f"Collecté le {event['retrieved_at']}")
                    st.link_button('Ouvrir les données sources', event['source_url'])
                    st.text('Localisation dans la source : ' + event['source_location'])
        with st.expander('Couverture et limites de la recherche'):
            st.caption('Collecte : ' + result['collected_at'])
            for dataset in result['datasets']:
                if dataset.get('latest_session_date'):
                    st.text(f"{dataset['provider']} : dernière séance repérée dans l’index, {date_label(dataset['latest_session_date'])}.")
            for limitation in result['limitations']:
                st.text(limitation)
        st.download_button('Exporter les actualités en JSON', json.dumps(result, ensure_ascii=False, indent=2),
                           file_name='actualites_officielles.json', mime='application/json', on_click='ignore')
