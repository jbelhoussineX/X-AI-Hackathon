"""Session profile, source ordering and history exercise the real orchestration."""
from copy import deepcopy
import pytest

from frontend.recent_activity import source_favorite_key
from frontend.recent_activity import current_profile_link
from test_recent_agent import install_model
from test_ui_recent_agent import offline, app, submit


def test_link_survives_unrelated_profile_changes_but_not_withdrawn_answer():
    item = {'relevance': 'Le texte traite des locations.', 'relevance_fields': ['logement']}
    saved = {'logement': 'Locataire', 'emploi': 'Étudiant(e)'}
    assert current_profile_link(item, saved, {'logement': 'Locataire'})
    assert current_profile_link(item, saved, {'logement': 'Locataire', 'emploi': 'Salarié(e)'})
    assert not current_profile_link(item, saved, {'emploi': 'Étudiant(e)'})
    assert not current_profile_link(item, saved, {'logement': 'Propriétaire'})
    assert not current_profile_link({'relevance_fields': []}, saved, saved)


def test_editing_employment_keeps_a_housing_link_without_new_calls(monkeypatch, offline):
    model = install_model(monkeypatch)
    original = model.side_effect

    def execute(stage, topic, payload):
        output = original(stage, topic, payload)
        if stage == 'summarize':
            output.items[0].relevance = 'Locataire : ce texte encadre la location.'
            output.items[0].relevance_fields = ['logement']
        return output

    model.side_effect = execute
    instance = app()
    instance.session_state['profile_guest_data']['answers'] = {'logement': 'Locataire', 'emploi': 'Étudiant(e)'}
    submit(instance).click().run()
    assert not instance.exception
    instance.radio(key='b_page').set_value('Mon profil').run()
    instance.selectbox(key='profile_answer_emploi').set_value('Je préfère ne pas répondre')
    next(button for button in instance.button if button.label == 'Enregistrer mon profil').click().run()
    instance.radio(key='b_page').set_value('Recherche').run()
    assert not instance.exception
    assert any('Locataire : ce texte encadre la location.' in item.value for item in instance.markdown)
    assert model.call_count == 3


def test_personalized_search_sort_and_history_without_regeneration(monkeypatch, offline):
    first = offline.return_value['events'][0]
    first['title'] = 'Texte récent'
    second = dict(first, id='older', title='Texte pour locataires', event_date='2026-09-10',
                  dossier_url='https://www.senat.fr/leg/ppl25-002.html')
    offline.return_value['events'].append(second)
    model = install_model(monkeypatch, supplement=True)
    original = model.side_effect

    def execute(stage, topic, payload):
        answer = original(stage, topic, payload)
        if stage == 'summarize':
            answer.items.reverse()
        return answer

    model.side_effect = execute
    instance = app()
    instance.session_state['profile_guest_data']['answers'] = {'logement': 'Locataire'}
    submit(instance).click().run()
    assert not instance.exception
    assert model.call_count == 4
    assert model.call_args.args[2]['profile_context'] == {'logement': 'Locataire'}
    assert any('Lien avec votre situation' in item.value for item in instance.markdown)
    assert instance.selectbox(key='recent_order').value == 'Pertinence pour mon profil'

    def titles():
        return [item.value for item in instance.markdown if 'class="doc-title"' in item.value]

    assert 'Texte pour locataires' in titles()[0]
    instance.selectbox(key='recent_order').set_value('Plus récents d’abord').run()
    assert not instance.exception
    assert 'Texte récent' in titles()[0]
    instance.selectbox(key='recent_order').set_value('Pertinence pour mon profil').run()
    instance.button(key=source_favorite_key(second)).click().run()
    assert not instance.exception
    assert 'Texte pour locataires' in titles()[0]
    assert model.call_count == 4
    saved = deepcopy(instance.session_state['recent_result']['agent_analysis'])

    instance.radio(key='b_page').set_value('Mon profil').run()
    instance.selectbox(key='profile_answer_logement').set_value('Propriétaire')
    next(button for button in instance.button if button.label == 'Enregistrer mon profil').click().run()
    assert not instance.exception
    assert model.call_count == 4
    instance.radio(key='b_page').set_value('Historique').run()
    next(button for button in instance.button if button.label == 'Ouvrir les résultats').click().run()
    assert not instance.exception
    assert instance.session_state['recent_result']['agent_analysis'] == saved
    assert any('Le profil a changé' in item.value for item in instance.info)
    assert model.call_count == 4
    submit(instance).click().run()
    assert not instance.exception
    assert model.call_count == 8
    assert model.call_args.args[2]['profile_context'] == {'logement': 'Propriétaire'}
    history = instance.session_state['profile_guest_data']['history']
    assert len(history) == 2
    assert history[0]['data']['agent_analysis'] == saved


@pytest.mark.parametrize('keep_employment', [False, True])
def test_removed_answer_hides_old_link_and_empty_link_has_no_paragraph(monkeypatch, offline, keep_employment):
    model = install_model(monkeypatch)
    original = model.side_effect

    def execute(stage, topic, payload):
        answer = original(stage, topic, payload)
        if stage == 'summarize':
            for item in answer.items:
                item.relevance = ('Ce passage concerne les locataires.'
                                  if payload.get('profile_context', {}).get('logement') else '')
                item.relevance_fields = ['logement'] if item.relevance else []
        return answer

    model.side_effect = execute
    instance = app()
    instance.session_state['profile_guest_data']['answers'] = {'logement': 'Locataire', 'emploi': 'Étudiant(e)'}
    submit(instance).click().run()
    assert not instance.exception
    assert any('Ce passage concerne les locataires.' in item.value for item in instance.markdown)
    assert model.call_count == 3
    instance.radio(key='b_page').set_value('Mon profil').run()
    instance.selectbox(key='profile_answer_logement').set_value('Je préfère ne pas répondre')
    if not keep_employment:
        instance.selectbox(key='profile_answer_emploi').set_value('Je préfère ne pas répondre')
    next(button for button in instance.button if button.label == 'Enregistrer mon profil').click().run()
    instance.radio(key='b_page').set_value('Recherche').run()
    assert not instance.exception
    assert not any('Lien avec votre' in item.value or 'Ce passage concerne les locataires.' in item.value
                   for item in instance.markdown)
    assert 'Pertinence pour mon profil' not in instance.selectbox(key='recent_order').options
    assert model.call_count == 3
    instance.radio(key='b_page').set_value('Historique').run()
    next(button for button in instance.button if button.label == 'Ouvrir les résultats').click().run()
    assert not instance.exception
    assert not any('Lien avec votre' in item.value for item in instance.markdown)
    assert model.call_count == 3
    submit(instance).click().run()
    assert not instance.exception
    assert model.call_count == 6
    assert not any('Lien avec votre' in item.value for item in instance.markdown)
    assert any('À retenir' in item.value for item in instance.markdown)
