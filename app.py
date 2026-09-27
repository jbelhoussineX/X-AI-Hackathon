"""Interface locale. Démarrage : python -m streamlit run app.py"""
from datetime import date
import json
import streamlit as st
from src.contracts import ReportError, public_url
from src.dust_client import DustError
from src.service import search

st.set_page_config(page_title='Repères citoyens — prototype', layout='wide')
st.title('Repères citoyens')
st.write('Trouver des textes parlementaires et des interlocuteurs liés au sujet, avec leurs sources.')
st.caption('Prototype documentaire, non exhaustif. Pas de recommandation politique ni d’envoi de messages.')
mode_label = st.radio('Source des résultats', ['Exemple fictif — aucun appel IA', 'Recherche réelle — Dust'], horizontal=True)
mode = 'demo' if mode_label.startswith('Exemple') else 'dust'
if mode == 'demo':
    st.warning('EXEMPLE FICTIF : le résultat est fixe et sert uniquement à tester l’interface, quel que soit le sujet saisi.')
else:
    st.info('La requête sera transmise à Dust. Ne saisir aucune donnée personnelle sensible. Les sources doivent être relues.')
with st.form('search_form'):
    topic = st.text_input('Sujet', placeholder='Un sujet précis, sans préférence électorale', max_chars=500)
    a, b = st.columns(2)
    start = a.date_input('Publication à partir du', value=date(2024, 1, 1))
    end = b.date_input('Publication jusqu’au', value=date.today())
    submitted = st.form_submit_button('Rechercher')
if submitted:
    st.session_state.pop('result', None)
    if mode == 'dust' and st.session_state.get('live_attempts', 0) >= 10:
        st.error('Dix tentatives réelles dans cette session. Vérifier les crédits avant de redémarrer. Ce n’est pas un plafond de facturation fournisseur.')
    else:
        if mode == 'dust':
            st.session_state['live_attempts'] = st.session_state.get('live_attempts', 0) + 1
        try:
            with st.spinner('Requête en cours. Ce message n’est pas un journal des outils exécutés par l’agent.'):
                st.session_state['result'] = search(topic, start.isoformat(), end.isoformat(), mode)
        except (DustError, ReportError) as exc:
            st.error(str(exc))
        except Exception:
            st.error('Erreur inattendue. Demander au responsable intégration de reproduire le problème avec les tests, sans publier .env.')

result = st.session_state.get('result')
if result:
    st.divider()
    if result['mode'] == 'demo':
        st.warning('RÉSULTAT FICTIF — aucune recherche documentaire réelle.')
    else:
        st.info('Résultat de la dernière recherche Dust — ne change pas automatiquement lorsque vous modifiez le formulaire.')
    st.caption(f"Exécution : {result['run_at_utc']} · durée observée : {result['duration_seconds']} s")
    st.caption(result['validation'])
    r = result['report']
    st.subheader(r['topic'])
    st.write(r['scope'])
    if not r['documents']:
        st.warning('Aucun document retrouvé dans cette recherche. Cela ne prouve pas l’absence de texte.')
    documents = sorted(r['documents'], key=lambda d: d['publication_date'] or '', reverse=True)
    for d in documents:
        with st.container(border=True):
            st.subheader(d['title'])
            st.caption(f"{d['kind'].replace('_', ' ')} · publication : {d['publication_date'] or 'non confirmée'}")
            st.write(d['summary'])
            st.write('Étape rapportée :', d['stage'] or 'Non confirmée')
            if d['stage_date']:
                st.caption('Date de cette étape : ' + d['stage_date'])
            with st.expander('Sources et extraits à contrôler'):
                for e in d['evidence']:
                    st.write('Justifie : ' + e['purpose'])
                    if result['mode'] != 'demo' and public_url(e['url']):
                        st.link_button('Ouvrir la source', e['url'])
                    else:
                        st.text(e['url'])
                    st.text(e['excerpt'])
                    if e['location']:
                        st.caption(e['location'])
            for u in d['uncertainties']:
                st.warning(u)
    st.subheader('Interlocuteurs documentés')
    for c in sorted(r['contacts'], key=lambda c: c['name'].casefold()):
        with st.container(border=True):
            st.write(c['name'] + ' — ' + c['role'])
            st.write(c['relation'])
            st.caption('Documents associés : ' + ', '.join(c['document_ids']))
            if c['contact_url'] and result['mode'] != 'demo':
                st.link_button('Page de contact publique', c['contact_url'])
            else:
                st.caption('Page de contact non confirmée.')
            with st.expander('Sources de la relation et du contact'):
                for e in c['evidence']:
                    if result['mode'] != 'demo':
                        st.link_button('Consulter : ' + e['purpose'], e['url'])
                    st.text(e['excerpt'])
    st.subheader('Périmètre et limites')
    for limitation in r['limitations']:
        st.write(limitation)
    st.download_button('Exporter ce résultat en JSON', json.dumps(result, ensure_ascii=False, indent=2), file_name='recherche.json', mime='application/json')
