"""Recent official inventory events; deliberately separate from publication search."""
import os
import hashlib
from datetime import date
from html import escape

import streamlit as st

from backend.recent_agent import research as agent_research, AgentError
from backend.profiles import ProfileError
from backend.profile_context import summary_profile
from backend.document_groups import group_events, group_summaries
from backend.data_sources.recent import _stable_key
from frontend.topics import TopicSelectionError, parse_topics, topic_options

CATEGORIES = {'procedure': 'Étape législative', 'publication': 'Publication parlementaire',
              'amendement': 'Amendement', 'debat': 'Débat / intervention', 'actualite': 'Actualité institutionnelle'}


def date_label(value):
    try:
        return date.fromisoformat(value).strftime('%d/%m/%Y')
    except (ValueError, TypeError):
        return 'Date non renseignée'


def source_favorite_key(event):
    return 'recent_favorite_' + hashlib.sha256(_stable_key(event).encode('utf-8')).hexdigest()[:20]


def group_sources(events):
    return group_events(events)


def render_source_event(event, *, show_title=False):
    st.caption(f"{date_label(event['event_date'])} · {CATEGORIES.get(event.get('category', 'procedure'), 'Publication officielle')}")
    if show_title:
        st.text(event['title'])
    from frontend.library import favorite_button
    favorite_button(event, key=source_favorite_key(event))


def render():
    # Discard requests left by the former profile page; only this form searches.
    st.session_state.pop('recent_pending_search', None)
    extra_topics = list(st.session_state.get('recent_topics', []))
    profile_context = {}
    try:
        from frontend.library import account_store
        account = account_store()
        if account:
            identity, store = account
            preferences = store.get_or_create(identity)
            profile_context = summary_profile(store.answers(identity))
            st.session_state.setdefault('recent_amount', preferences['recent_months'])
            st.session_state.setdefault('recent_unit', 'mois')
    except (ProfileError, OSError):
        pass  # Topic shortcuts remain usable if profile storage is unavailable.
    with st.container():
        enabled = os.environ.get('ENABLE_PIPELEX_CALLS', '').lower() == 'true'
        engine = os.environ.get('PIPELEX_EXECUTION_MODE', 'hosted')
        provider = 'API Pipelex' if engine == 'hosted' else 'Pipelex local et OpenAI'
        with st.form('recent_activity_form'):
            options = topic_options(extra_topics)
            topics = st.pills('Sujets', options, selection_mode='multi',
                              key='recent_topics')
            custom_topic = st.text_input('Autres sujets', max_chars=814, key='recent_topic',
                                         placeholder='Ex. : enseignement supérieur, retraites')
            period, units = st.columns([1, 1])
            amount = period.number_input('Sur les derniers…', min_value=1, max_value=90,
                                     value=3, step=1, key='recent_amount',
                                     help='1 à 12 mois calendaires ou 1 à 90 jours. Aujourd’hui inclus.')
            unit = units.selectbox('Unité de la période', ['mois', 'jours'], key='recent_unit')
            st.caption(f'Recherche assistée par IA · {provider} · utilise des crédits fournisseur au clic.')
            if profile_context:
                st.caption('Résumés et ordre adaptés aux réponses du profil, transmises à l’IA sans votre nom.')
            if not enabled:
                st.info('La recherche IA est momentanément indisponible sur ce serveur.')
            submitted = st.form_submit_button('Rechercher', type='primary', width='stretch', disabled=not enabled)
        if submitted and enabled:
            for key in ('recent_from_history', 'recent_categories', 'recent_order',
                        'recent_result', 'recent_brief', 'recent_brief_error', 'recent_consent', 'recent_agent_error'):
                st.session_state.pop(key, None)
            try:
                selected_topics = parse_topics(topics, custom_topic)
                personalization = {'profile_context': profile_context} if profile_context else {}
                with st.spinner('Recherche et analyse des nouveautés…'):
                    result = (agent_research(selected_topics, months=int(amount), **personalization) if unit == 'mois'
                              else agent_research(selected_topics, days=int(amount), **personalization))
                    result.setdefault('topics', list(selected_topics))
                    result['search_period'] = {'amount': int(amount), 'unit': unit}
                    st.session_state['recent_result'] = result
                from frontend.library import remember
                remember(result)
            except AgentError as exc:
                st.session_state['recent_agent_error'] = str(exc)
                if exc.result is not None:
                    st.session_state['recent_result'] = exc.result
                    from frontend.library import remember
                    remember(exc.result)
            except TopicSelectionError as exc:
                st.error(str(exc))
            except ValueError:
                st.error('Choisis 1 à 8 sujets de trois caractères minimum et une période de 1 à 12 mois ou de 1 à 90 jours.')
            except Exception:
                st.error('La recherche a échoué. Réessaie en cliquant sur Rechercher.')
        if st.session_state.get('recent_agent_error'):
            st.error(st.session_state['recent_agent_error'])
        result = st.session_state.get('recent_result')
        if result is None:
            return
        st.divider()
        st.subheader('Consulter les résultats')
        if st.session_state.get('recent_from_history'):
            st.info('Recherche enregistrée : les données datent de cette collecte. Cliquez sur Rechercher pour les actualiser avant une nouvelle synthèse.')
        st.text(result['topic'])
        st.caption(f"Du {date_label(result['start'])} au {date_label(result['end'])} inclus")
        total, sources = st.columns(2)
        total.metric('Événements retrouvés', len(result['events']))
        sources.metric('Sources disponibles', f"{sum(d['status'] == 'ok' for d in result['datasets'])} / {len(result['datasets'])}")
        for dataset in result['datasets']:
            if dataset['status'] != 'ok':
                st.warning(f"Source {dataset['provider']} indisponible : résultats partiels.")
        analysis = result.get('agent_analysis')
        if analysis:
            if (analysis.get('status') == 'completed' and analysis.get('brief', {}).get('items')
                    and analysis.get('profile_context', {}) != profile_context):
                st.info('Le profil a changé depuis cette recherche. Cliquez sur Rechercher pour adapter les résumés et leur ordre.')
            render_analysis(analysis, profile_context=profile_context)
        if not result['events']:
            st.info('Aucun événement daté retrouvé dans cette fenêtre et ce corpus. '
                    'Cela ne signifie pas qu’il n’existe aucune actualité sur ce sujet.')
        st.subheader('Sources législatives')
        categories = sorted({event.get('category', 'procedure') for event in result['events']})
        selected = st.multiselect('Filtrer par type d’événement', categories,
                                  format_func=lambda value: CATEGORIES.get(value, value),
                                  placeholder='Tous les types', key='recent_categories')
        orders = ['Plus récents d’abord', 'Plus anciens d’abord']
        if (analysis and analysis.get('profile_context')
                and analysis['profile_context'] == profile_context):
            orders.insert(0, 'Pertinence pour mon profil')
        if st.session_state.get('recent_order') not in orders:
            st.session_state.pop('recent_order', None)
        order = st.selectbox('Ordre des événements', orders, key='recent_order')
        events = [event for event in result['events'] if not selected or event.get('category', 'procedure') in selected]
        events = sorted(events, key=lambda event: event['event_date'], reverse=order != 'Plus anciens d’abord')
        if order == 'Pertinence pour mon profil':
            ranked = {(item['event_id'], item.get('dossier_url') or item['url'], item['event_date']): index
                      for index, item in enumerate(analysis['brief']['items'])}
            events.sort(key=lambda event: ranked.get((event['id'], event['dossier_url'], event['event_date']), len(ranked)))
        groups, repetitions = group_sources(events)
        st.caption(f"{len(groups)} source(s) · {sum(len(group) for group in groups)} étape(s) ou version(s)")
        if repetitions:
            st.caption(f'{repetitions} répétition(s) identique(s) regroupée(s).')
        for group in groups:
            event = group[0]
            with st.container(border=True):
                st.markdown(f'<div class="doc-title">{escape(event["title"])}</div>', unsafe_allow_html=True)
                st.link_button('Lire la source officielle', event['dossier_url'])
                render_source_event(event)
                if len(group) > 1:
                    with st.expander(f'Autres étapes et versions ({len(group) - 1})'):
                        for other in group[1:]:
                            render_source_event(other, show_title=other['title'] != event['title'])


def render_analysis(analysis, *, profile_context=None):
    st.subheader('Les nouveautés en bref')
    if analysis.get('status') == 'failed':
        if not st.session_state.get('recent_agent_error'):
            st.error(analysis['error'])
        st.info('Les sources déjà collectées restent disponibles ci-dessous.')
    else:
        brief = analysis['brief']
        groups = group_summaries(brief['items'])
        repeated = len(brief['items']) - sum(len(group) for group in groups)
        if repeated:
            st.caption(f'{repeated} résumé(s) répété(s) regroupé(s).')
        for group in groups:
            def show(item):
                linked = current_profile_link(item, analysis.get('profile_context', {}), profile_context or {})
                render_summary(item, personalized=linked, show_relevance=linked)
            show(group[0])
            if len(group) > 1:
                with st.expander(f'Autres étapes du même texte ({len(group) - 1})'):
                    for item in group[1:]:
                        show(item)
        if not brief['items']:
            st.info('Aucun résumé suffisamment étayé dans le corpus consulté.')
    with st.expander('Recherches effectuées'):
        for query in analysis['queries']:
            st.text(query)


def current_profile_link(item, saved, current):
    fields = item.get('relevance_fields')
    # Old history has no per-link references: only show it with its original profile.
    if fields is None:
        return bool(current) and saved == current
    return bool(fields) and all(key in saved and saved[key] == current.get(key) for key in fields)


def render_summary(item, *, personalized=False, show_relevance=True):
    # Colors indicate document type, never political alignment or a score.
    palette = {'procedure': ('#245C49', '#EDF6F0'), 'publication': ('#285B82', '#EFF5FB'),
               'amendement': ('#745392', '#F5F0FA'), 'debat': ('#8A591D', '#FCF5EA'),
               'actualite': ('#3C6570', '#EFF7F8')}
    category = item.get('category', 'procedure')
    color, background = palette.get(category, ('#245C49', '#EDF6F0'))
    label = CATEGORIES.get(category, 'Source parlementaire')
    title = item.get('title') or label
    with st.container(border=True):
        st.markdown(
            f'<div style="border-left:3px solid {color};padding:4px 0 4px 14px;margin-bottom:14px">'
            f'<span style="display:inline-block;background:{background};color:{color};border-radius:20px;'
            f'padding:4px 10px;font-size:12px;font-weight:600">{escape(label)}</span>'
            f'<span style="color:#536867;font-size:12px;margin-left:10px">{date_label(item.get("event_date"))}</span>'
            f'<h3 style="font-size:21px;line-height:1.35;margin:10px 0 0;overflow-wrap:anywhere">{escape(title)}</h3></div>'
            f'<div class="safe-text">{escape(item["summary"])}</div>', unsafe_allow_html=True)
        relevance_heading = 'Lien avec votre situation' if personalized else 'Lien avec votre sujet'
        for heading, field in ((relevance_heading, 'relevance'), ('À retenir', 'uncertainty')):
            if field == 'relevance' and not show_relevance:
                continue
            if item.get(field, '').strip():
                st.markdown(
                    f'<div style="margin-top:12px"><strong style="font-size:13px;color:{color}">{heading}</strong>'
                    f'<div class="safe-text">{escape(item[field])}</div></div>', unsafe_allow_html=True)
        st.link_button('Lire la source', item['url'])
