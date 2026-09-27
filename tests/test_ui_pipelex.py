from unittest.mock import Mock

from streamlit.testing.v1 import AppTest

from frontend.interface_b import appeler_service_a, creer_demonstration
from src.contracts import ROOT
from src.pipelex_client import PipelexError


def test_adapter_uses_pipelex(monkeypatch):
    service = Mock(return_value={})
    monkeypatch.setattr('src.service.search', service)
    appeler_service_a({'topic': 'test', 'start': '2024-01-01', 'end': '2026-09-27'})
    service.assert_called_once_with('test', '2024-01-01', '2026-09-27', mode='pipelex')


def test_app_navigation_and_demo_never_call_service(monkeypatch):
    service = Mock(side_effect=AssertionError('Appel réel interdit'))
    monkeypatch.setattr('src.service.search', service)
    monkeypatch.setattr('frontend.profile.current_identity', lambda: None)
    app = AppTest.from_file(str(ROOT / 'app.py')).run()
    assert not app.exception
    assert not app.tabs
    assert [field.key for field in app.text_input] == ['recent_topic']
    assert not any(heading.value.startswith('1.') for heading in app.subheader)
    assert app.radio(key='b_page').options == ['Recherche', 'Mon profil', 'Aide']
    app.radio(key='b_page').set_value('Mon profil').run()
    assert not app.exception
    assert any('Connecte-toi avec Google' in message.value for message in app.info)
    app.radio(key='b_page').set_value('Aide').run()
    assert not app.exception
    service.assert_not_called()


def test_live_requires_click_and_does_not_repeat_on_rerun(monkeypatch):
    query = {'topic': 'Sujet fictif', 'start': '2024-01-01', 'end': '2026-09-27'}
    result = creer_demonstration(query)
    result['mode'] = 'pipelex'  # Mock explicite du test, jamais un repli de l'application.
    service = Mock(return_value=result)
    monkeypatch.setattr('src.service.search', service)
    # Le formulaire historique reste testé isolément, sans être exposé sur l’accueil.
    app = AppTest.from_string('''
import streamlit as st
from frontend.interface_b import initialiser_etat, recherche_documents
initialiser_etat(st.session_state)
st.checkbox('Consentement', key='b_consent')
recherche_documents('pipelex')
''').run()
    service.assert_not_called()
    app.text_input(key='b_topic').set_value('Sujet fictif')
    app.checkbox(key='b_consent').check().run()
    next(button for button in app.button if button.label == 'Rechercher les documents').click().run()
    assert not app.exception
    assert app.session_state['b_last'] is not None
    app.run()
    service.assert_called_once()
    service.side_effect = PipelexError('Limite OpenAI atteinte.')
    next(button for button in app.button if button.label == 'Rechercher les documents').click().run()
    assert app.session_state['b_last'] is None
    assert 'Limite OpenAI' in app.session_state['b_error']
