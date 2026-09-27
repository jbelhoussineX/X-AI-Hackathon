"""Consent and reruns never cause unrequested agent stages."""
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from backend import recent_agent as agent
from frontend import profile
from src.contracts import ROOT
from frontend.recent_activity import source_favorite_key
from test_recent_agent import result, install_model


@pytest.fixture
def offline(monkeypatch, tmp_path):
    monkeypatch.setenv('PYTHON_DOTENV_DISABLED', '1')
    monkeypatch.setenv('ENABLE_PIPELEX_CALLS', 'true')
    monkeypatch.setenv('PIPELEX_EXECUTION_MODE', 'local')
    monkeypatch.setenv('OPENAI_API_KEY', 'offline-placeholder')
    monkeypatch.setattr(profile, 'current_identity', lambda: None)
    monkeypatch.setattr(profile, 'PROFILE_PATH', tmp_path / 'profiles.sqlite3')
    collect = Mock(return_value=result())
    monkeypatch.setattr(agent, 'collect_candidates', collect)
    monkeypatch.setattr('backend.recent_brief.collect_sources', Mock(side_effect=AssertionError('No network')))
    return collect


def submit(app):
    return next(button for button in app.button if button.label == 'Rechercher')


def app():
    instance = AppTest.from_file(str(ROOT / 'app.py')).run()
    instance.text_input(key='recent_topic').set_value('logement')
    instance.number_input(key='recent_amount').set_value(1)
    return instance


def test_agent_requires_one_submit_then_history_reopens_without_calls(monkeypatch, offline):
    model = install_model(monkeypatch)
    instance = app()
    model.assert_not_called()
    instance.run()
    model.assert_not_called()
    submit(instance).click().run()
    assert not instance.exception
    assert model.call_count == 3
    offline.assert_called_once()
    assert not any('Lien avec votre' in item.value for item in instance.markdown)
    assert any('À retenir' in item.value for item in instance.markdown)
    assert len(instance.session_state['profile_guest_data']['history']) == 1
    instance.run()
    assert model.call_count == 3
    instance.button(key=source_favorite_key(instance.session_state['recent_result']['events'][0])).click().run()
    assert model.call_count == 3
    instance.radio(key='b_page').set_value('Historique').run()
    next(button for button in instance.button if button.label == 'Ouvrir les résultats').click().run()
    assert not instance.exception
    assert model.call_count == 3
    assert not any('Lien avec votre' in item.value for item in instance.markdown)
    assert len(instance.session_state['profile_guest_data']['history']) == 1


def test_no_non_ai_mode_and_search_runs_agent(monkeypatch, offline):
    model = install_model(monkeypatch)
    instance = app()
    assert all(radio.key != 'b_mode' for radio in instance.radio)
    assert not instance.checkbox
    model.assert_not_called()
    submit(instance).click().run()
    assert not instance.exception
    assert model.call_count == 3
    assert not instance.get('download_button')
    assert any(item.value == 'Sources législatives' for item in instance.subheader)
    assert not any(item.label in ('Limites de l’analyse', 'Couverture et limites de la recherche')
                   for item in instance.expander)
    queries = next(item for item in instance.expander if item.label == 'Recherches effectuées')
    assert [item.value for item in queries.text] == instance.session_state['recent_result']['agent_analysis']['queries']


def test_failed_evaluation_preserves_sources_and_does_not_repeat(monkeypatch, offline):
    model = install_model(monkeypatch, fail='evaluate')
    instance = app()
    submit(instance).click().run()
    assert not instance.exception
    assert any('Limite OpenAI' in item.value for item in instance.error)
    assert instance.session_state['recent_result']['events']
    assert model.call_count == 2
    instance.run()
    assert model.call_count == 2
    assert len(instance.session_state['profile_guest_data']['history']) == 1


def test_disabled_agent_cannot_run(monkeypatch, offline):
    model = install_model(monkeypatch)
    monkeypatch.setenv('ENABLE_PIPELEX_CALLS', 'false')
    instance = app()
    assert submit(instance).disabled
    instance.run()
    model.assert_not_called()


def test_summary_titles_and_text_escape_untrusted_content():
    instance = AppTest.from_string('''
from frontend.recent_activity import render_summary
render_summary(dict(title='<img src=x onerror=alert(1)>', category='debat',
                    event_date='2026-09-27', summary='<script>unsafe()</script>',
                    relevance='**texte** <b>brut</b>', uncertainty='Statut inconnu.',
                    url='https://www.senat.fr/'))
''').run()
    assert not instance.exception
    markup = '\n'.join(item.value for item in instance.markdown)
    assert '&lt;img' in markup and '&lt;script&gt;' in markup
    assert '<img' not in markup and '<script>' not in markup
    assert '27/09/2026' in markup
    assert 'Débat / intervention' in markup
