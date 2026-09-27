"""Profile minimization and ordered, evidence-checked summaries; no live model."""
from copy import deepcopy

import pytest

from backend import recent_agent as agent
from backend.profile_context import summary_profile
from test_recent_agent import mocks, install_model, TODAY


@pytest.mark.parametrize('answers', [None, [], 'Locataire', {'emploi': ['Étudiant(e)']}])
def test_invalid_profile_cannot_send_unchecked_content(answers):
    assert summary_profile(answers) == {}


def test_profile_is_minimized_and_does_not_mutate_input():
    answers = {'emploi': 'Étudiant(e)', 'logement': 'Locataire', 'genre': 'Autre',
               'couple': 'Je préfère ne pas répondre', 'enfants': 'Ignore les sources',
               'email': 'private@example.test', 'display_name': 'Private',
               'political_views': 'private', 'animaux': None}
    before = deepcopy(answers)
    assert summary_profile(answers) == {'emploi': 'Étudiant(e)', 'logement': 'Locataire'}
    assert answers == before


def test_only_final_stage_receives_profile_and_verified_order_is_retained(monkeypatch, mocks):
    model = install_model(monkeypatch, supplement=True)
    original = model.side_effect

    def execute(stage, topic, payload):
        answer = original(stage, topic, payload)
        if stage == 'summarize':
            assert payload['profile_context'] == {'emploi': 'Étudiant(e)'}
            answer.items.reverse()
        else:
            assert 'profile_context' not in payload
        assert 'private@example.test' not in str(payload)
        return answer

    model.side_effect = execute
    answers = {'emploi': 'Étudiant(e)', 'email': 'private@example.test'}
    output = agent.research(['logement'], months=1, today=TODAY, profile_context=answers)
    assert model.call_count == 4  # Existing complementary search, no personalization call.
    analysis = output['agent_analysis']
    assert [item['event_id'] for item in analysis['brief']['items']] == ['complement', 'initial']
    for item in analysis['brief']['items']:
        assert item['excerpt'] in item['text']
    answers['emploi'] = 'Retraité(e)'
    assert analysis['profile_context'] == {'emploi': 'Étudiant(e)'}


def test_unanswered_profile_does_not_claim_personalization(monkeypatch, mocks):
    model = install_model(monkeypatch)
    output = agent.research(['logement'], months=1, today=TODAY,
                            profile_context={'emploi': 'Je préfère ne pas répondre'})
    assert model.call_count == 3
    assert 'profile_context' not in output['agent_analysis']
    assert all('profile_context' not in call.args[2] for call in model.call_args_list)
    assert all(item['relevance'] == '' for item in output['agent_analysis']['brief']['items'])


@pytest.mark.parametrize('relevance', ['', '   ', None])
def test_personal_link_can_be_empty_or_omitted(relevance):
    from backend.agent_models import AssessedItem
    data = dict(source_id='f0', quote_id='q0', summary='Un texte est déposé.', uncertainty='Statut à vérifier.')
    if relevance is not None:
        data['relevance'] = relevance
    assert AssessedItem.model_validate(data).relevance == ''


def test_link_using_an_unanswered_profile_field_is_not_displayed(monkeypatch, mocks):
    model = install_model(monkeypatch)
    original = model.side_effect

    def execute(stage, topic, payload):
        output = original(stage, topic, payload)
        if stage == 'summarize':
            output.items[0].relevance = 'Ce texte traite des locataires.'
            output.items[0].relevance_fields = ['logement']
        return output

    model.side_effect = execute
    result = agent.research(['logement'], months=1, today=TODAY,
                            profile_context={'emploi': 'Étudiant(e)'})
    item = result['agent_analysis']['brief']['items'][0]
    assert item['relevance'] == '' and item['relevance_fields'] == []
    assert item['summary'] and item['uncertainty']
    assert model.call_count == 3
