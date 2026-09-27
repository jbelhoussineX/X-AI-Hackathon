"""Agent decisions, evidence and bounded costs, with no external calls."""
from copy import deepcopy
from datetime import date, datetime, timezone
from unittest.mock import Mock

import pytest

from backend import recent_agent as agent
from backend.agent_models import Plan, Selection, Evaluation, AgentBrief
from src.pipelex_client import PipelexError

TODAY = date(2026, 9, 27)
URL = 'https://www.senat.fr/leg/ppl25-001.html'


def result(event_id='initial', *, empty=False):
    now = datetime.now(timezone.utc).isoformat()
    return dict(topic='requête', start='2026-08-27', end='2026-09-27', collected_at=now,
        events=[] if empty else [dict(id=event_id, title='Proposition fictive sur le logement',
            event_date='2026-09-20', event='Dépôt', decision=None, category='procedure',
            date_kind='Dépôt', dossier_url=URL, source_url=URL, provider='senat',
            source_location='Fixture', retrieved_at=now,
            content_passages=['Cette proposition fictive concerne le logement étudiant et les aides au logement.'])],
        datasets=[dict(provider='senat', status='ok')], limitations=['Corpus de test fictif.'])


@pytest.fixture
def mocks(monkeypatch):
    monkeypatch.setenv('PIPELEX_EXECUTION_MODE', 'local')
    monkeypatch.setenv('ENABLE_PIPELEX_CALLS', 'true')
    monkeypatch.setenv('OPENAI_API_KEY', 'fake-key-for-offline-test')
    monkeypatch.setenv('PYTHON_DOTENV_DISABLED', '1')
    pool = result()
    pool['events'].extend(result('complement')['events'])
    initial = Mock(return_value=pool)
    followup = Mock(side_effect=AssertionError('No lexical fallback'))
    monkeypatch.setattr(agent, 'collect_candidates', initial)
    monkeypatch.setattr('backend.data_sources.recent.search_recent', followup)
    monkeypatch.setattr('backend.recent_brief.collect_sources', Mock(side_effect=AssertionError('Network forbidden')))
    return initial, followup


def install_model(monkeypatch, *, supplement=False, empty=False, fail=None):
    def execute(stage, topic, payload):
        if stage == fail:
            raise PipelexError('Limite OpenAI atteinte.')
        if stage == 'select':
            ids = [row['candidate_id'] for row in payload['candidates'][:1]]
            if empty and not payload['focus']:
                ids = []
            return Selection(queries=['logement étudiant', 'aides au logement'], event_ids=ids)
        if stage == 'evaluate':
            return Evaluation(coverage='vide' if empty else 'partiel' if supplement else 'suffisant',
                relevant_sources=[] if empty else ['e0p0'], gaps=['Sujet à mieux documenter.'] if supplement else [],
                followup_query='bourses' if supplement else '')
        assert stage == 'summarize'
        assert len(payload['sources']) <= 18
        return AgentBrief(items=[dict(source_id=source['source_id'], quote_id=source['quotes'][0]['quote_id'],
            summary='Une proposition traite du logement étudiant.', relevance='Le sujet logement est abordé.',
            relevance_fields=list(payload.get('profile_context', {})),
            uncertainty='Le dépôt ne constitue pas une adoption.') for source in payload['sources']], limitations=[])
    model = Mock(side_effect=execute)
    monkeypatch.setattr(agent, 'call_stage', model)
    return model


@pytest.mark.parametrize('supplement', [False, True])
def test_agent_plans_evaluates_optionally_completes_and_summarizes(monkeypatch, mocks, supplement):
    initial, followup = mocks
    model = install_model(monkeypatch, supplement=supplement)
    output = agent.research(['logement', 'étudiant'], months=1, today=TODAY)
    assert [call.args[0] for call in model.call_args_list] == (['select', 'evaluate', 'select', 'summarize'] if supplement else ['select', 'evaluate', 'summarize'])
    initial.assert_called_once_with(months=1, days=3, today=TODAY, transport=None)
    followup.assert_not_called()
    assert output['topics'] == ['logement', 'étudiant']
    assert output['topic'] == 'logement · étudiant'
    analysis = output['agent_analysis']
    assert analysis['status'] == 'completed'
    assert len(analysis['queries']) == (3 if supplement else 2)
    assert len(analysis['brief']['items']) == (2 if supplement else 1)
    for item in analysis['brief']['items']:
        assert item['excerpt'] in item['text']
        assert item['url'] == URL
        assert item['relevance'] == ''  # No personal paragraph without profile answers.
        assert item['uncertainty']


def test_empty_corpus_can_trigger_complement_before_a_sourced_summary(monkeypatch, mocks):
    mocks[0].return_value = result('complement')
    model = install_model(monkeypatch, supplement=True, empty=True)
    output = agent.research(['logement'], months=1, today=TODAY)
    assert model.call_count == 4
    assert output['agent_analysis']['brief']['items'][0]['event_id'] == 'complement'


def test_no_evidence_skips_final_model_without_fake_results(monkeypatch, mocks):
    mocks[0].return_value = result(empty=True)
    model = install_model(monkeypatch, empty=True)
    output = agent.research(['logement'], months=1, today=TODAY)
    model.assert_not_called()
    mocks[1].assert_not_called()
    assert output['agent_analysis']['brief']['items'] == []
    assert output['agent_analysis']['queries'] == []


@pytest.mark.parametrize('stage', ['select', 'evaluate', 'summarize'])
def test_provider_failure_stops_without_retry_and_retains_collected_sources(monkeypatch, mocks, stage):
    model = install_model(monkeypatch, fail=stage)
    with pytest.raises(agent.AgentError, match='Limite OpenAI') as caught:
        agent.research(['logement'], months=1, today=TODAY)
    assert model.call_count == ['select', 'evaluate', 'summarize'].index(stage) + 1
    mocks[1].assert_not_called()
    if stage == 'select':
        assert caught.value.result['events'] == []
        mocks[0].assert_called_once()
    else:
        assert caught.value.result['events']
        assert caught.value.result['agent_analysis']['status'] == 'failed'
        assert 'brief' not in caught.value.result['agent_analysis']


@pytest.mark.parametrize('evaluation', [
    dict(coverage='partiel', relevant_sources=['invented'], gaps=[], followup_query='retraites'),
    dict(coverage='suffisant', relevant_sources=['e0p0'], gaps=[], followup_query='retraites'),
    dict(coverage='vide', relevant_sources=['e0p0'], gaps=[], followup_query=''),
])
def test_invalid_evaluation_never_triggers_supplement(monkeypatch, mocks, evaluation):
    model = Mock(side_effect=[Selection(queries=['logement'], event_ids=['c0']), Evaluation(**evaluation)])
    monkeypatch.setattr(agent, 'call_stage', model)
    with pytest.raises(agent.AgentError, match='incohérente'):
        agent.research(['logement'], months=1, today=TODAY)
    assert model.call_count == 2
    mocks[1].assert_not_called()


def test_repeated_query_is_not_retried(monkeypatch, mocks):
    model = install_model(monkeypatch)
    original = model.side_effect
    def call(stage, topic, payload):
        if stage == 'evaluate':
            return Evaluation(coverage='partiel', relevant_sources=['e0p0'], gaps=[], followup_query='LOGEMENT ÉTUDIANT')
        return original(stage, topic, payload)
    model.side_effect = call
    agent.research(['logement'], months=1, today=TODAY)
    mocks[1].assert_not_called()
    assert model.call_count == 3


def test_fabricated_quote_rejected_without_silent_fallback(monkeypatch, mocks):
    model = install_model(monkeypatch)
    original = model.side_effect
    def call(stage, topic, payload):
        output = original(stage, topic, payload)
        if stage == 'summarize':
            output.items[0].quote_id = 'invented'
        return output
    model.side_effect = call
    with pytest.raises(agent.AgentError, match='citation absent') as caught:
        agent.research(['logement'], months=1, today=TODAY)
    assert caught.value.result['events']
    assert 'brief' not in caught.value.result['agent_analysis']


def test_month_period_invalid_fails_before_ai(monkeypatch, mocks):
    model = install_model(monkeypatch)
    with pytest.raises(ValueError):
        agent.research(['logement'], months=13, today=TODAY)
    model.assert_not_called()
    mocks[0].assert_not_called()


def test_no_key_fails_before_collection_or_ai(monkeypatch, mocks):
    model = install_model(monkeypatch)
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    with pytest.raises(agent.AgentError, match='OPENAI_API_KEY'):
        agent.research(['logement'], months=1, today=TODAY)
    model.assert_not_called()
    mocks[0].assert_not_called()


def test_merge_preserves_distinct_versions_and_original_data():
    first = result()
    extra = deepcopy(first)
    extra['events'][0]['event'] = 'Adoption'
    original = deepcopy(first)
    merged = agent._merge(first, extra)
    assert len(merged['events']) == 2
    assert first == original
    assert len(agent._merge(first, first)['events']) == 1


def test_empty_supplement_does_not_discard_initial_evidence():
    initial = result()
    initial['events'] = [dict(initial['events'][0], id=f'e{index}') for index in range(6)]
    corpus = agent.prepare(initial)
    final = agent._final_corpus(initial, corpus, [source['source_id'] for source in corpus['sources']],
                                result(empty=True), ['logement'], None)
    assert len(final['sources']) == 6


@pytest.mark.parametrize('queries', [[], ['un', 'deux', 'trois'], ['logement', 'LOGEMENT'], ['https://example.com'], ['logement\nsecret']])
def test_invalid_generated_queries_are_rejected(queries):
    with pytest.raises(ValueError):
        Plan(queries=queries)

def test_gateway_is_not_used_when_local_stage_is_selected(monkeypatch):
    from backend.generated.recent_brief.models import Request
    from backend.agent_models import Plan
    from src import recent_agent_worker
    monkeypatch.setenv('PIPELEX_EXECUTION_MODE', 'local')
    local = Mock(return_value=Plan(queries=['logement']))
    monkeypatch.setattr(recent_agent_worker, 'run_stage', local)
    hosted = Mock(side_effect=AssertionError('No provider fallback'))
    monkeypatch.setattr(agent, 'run_hosted_method', hosted)
    output = agent.call_stage('plan', 'logement', {})
    assert output.queries == ['logement']
    local.assert_called_once()
    hosted.assert_not_called()


def test_agent_worker_errors_and_timeout_are_redacted(monkeypatch):
    import subprocess
    from types import SimpleNamespace
    from backend.generated.recent_brief.models import Request
    from src.recent_agent_worker import run_stage
    request = Request(topic='logement', corpus_json='{}')
    completed = SimpleNamespace(returncode=1,
        stdout='{"ok": false, "error": "credentials", "diagnostic": {"code": "SECRET", "http_status": 401}}',
        stderr='SECRET raw log')
    process = Mock(return_value=completed)
    monkeypatch.setattr('src.recent_agent_worker.subprocess.run', process)
    with pytest.raises(PipelexError) as caught:
        run_stage('plan', request)
    assert 'SECRET' not in str(caught.value)
    assert '401' in str(caught.value)
    process.assert_called_once()
    process.reset_mock()
    process.side_effect = subprocess.TimeoutExpired('SECRET', 180, output='SECRET')
    with pytest.raises(PipelexError, match='continuer') as caught:
        run_stage('plan', request)
    assert 'SECRET' not in str(caught.value)
    process.assert_called_once()


def test_unknown_worker_stage_does_not_create_process(monkeypatch):
    from backend.generated.recent_brief.models import Request
    from src.recent_agent_worker import run_stage
    process = Mock(side_effect=AssertionError('No subprocess'))
    monkeypatch.setattr('src.recent_agent_worker.subprocess.run', process)
    with pytest.raises(PipelexError):
        run_stage('../../SECRET', Request(topic='logement', corpus_json='{}'))
    process.assert_not_called()


def test_unknown_provider_does_not_collect_or_fallback(monkeypatch, mocks):
    monkeypatch.setenv('PIPELEX_EXECUTION_MODE', 'unknown')
    model = install_model(monkeypatch)
    with pytest.raises(agent.AgentError, match='Configuration'):
        agent.research(['logement'], months=1, today=TODAY)
    mocks[0].assert_not_called()
    model.assert_not_called()
