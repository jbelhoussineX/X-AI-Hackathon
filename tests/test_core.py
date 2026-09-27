from copy import deepcopy
import json
from unittest.mock import Mock, patch
import pytest
import requests
from src.contracts import ROOT, ReportError, parse_report, public_url, validate_report
from src.dust_client import DustError, Settings, extract_report, list_agents, run_dust
from src.service import search

@pytest.fixture
def report():
    return json.loads((ROOT / 'fixtures/demo.json').read_text(encoding='utf-8'))

def envelope(report, status='completed', typ='agent'):
    return {'conversation': {'sId': 'conv123', 'content': [[{
        'type': typ, 'configuration': {'sId': 'agent123'}, 'status': status,
        'rawContents': [{'step': 1, 'content': json.dumps(report)}],
        'chainOfThought': 'NE JAMAIS AFFICHER CE CHAMP', 'error': None,
    }]]}}

def test_valid(report):
    assert validate_report(report) == report

def test_json_fence(report):
    assert parse_report('```json\n' + json.dumps(report) + '\n```') == report

def test_missing_field(report):
    del report['scope']
    with pytest.raises(ReportError): validate_report(report)

def test_extra_field(report):
    report['score_politique'] = 99
    with pytest.raises(ReportError): validate_report(report)

def test_duplicate_id(report):
    report['documents'].append(deepcopy(report['documents'][0]))
    with pytest.raises(ReportError): validate_report(report)

def test_invalid_date(report):
    report['documents'][0]['publication_date'] = '2026-02-30'
    with pytest.raises(ReportError): validate_report(report)

def test_missing_content_evidence(report):
    report['documents'][0]['evidence'] = []
    with pytest.raises(ReportError): validate_report(report)

def test_stage_without_evidence(report):
    report['documents'][0]['stage'] = 'ÉTAPE FICTIVE'
    with pytest.raises(ReportError): validate_report(report)

def test_contact_without_proof(report):
    report['contacts'][0]['contact_url'] = 'https://example.org/contact'
    with pytest.raises(ReportError): validate_report(report)

def test_missing_relation(report):
    report['contacts'][0]['evidence'] = []
    with pytest.raises(ReportError): validate_report(report)

def test_bad_contact_document_id(report):
    report['contacts'][0]['document_ids'] = ['not_here']
    with pytest.raises(ReportError): validate_report(report)

@pytest.mark.parametrize('url', ['javascript:alert(1)', 'http://example.org', 'https://127.0.0.1/x', 'https://localhost/x', 'https://user:pass@example.org/x', 'https://example.org:444/x', 'https://example.org/x y'])
def test_unsafe_links(url):
    assert not public_url(url)

def test_valid_public_url():
    assert public_url('https://www.assemblee-nationale.fr/dyn/dossiers')

def test_no_results(report):
    report['documents'] = []; report['contacts'] = []
    assert validate_report(report) == report

def test_no_silent_json_repair():
    with pytest.raises(ReportError): parse_report('Voici ma réponse : {"x": 1}')

def test_extract_only_target(report):
    payload = envelope(report)
    payload['conversation']['content'].append([{'type': 'human', 'content': '{"malicious":1}'}])
    found, cid = extract_report(payload, 'agent123')
    assert found == report and cid == 'conv123'
    assert 'chainOfThought' not in found

@pytest.mark.parametrize('typ', ['human', 'user_message'])
def test_reject_human_even_with_json(report, typ):
    with pytest.raises(DustError): extract_report(envelope(report, typ=typ), 'agent123')

@pytest.mark.parametrize('status', ['succeeded', 'completed'])
def test_extract_public_api_agent_message(report, status):
    found, cid = extract_report(envelope(report, status=status, typ='agent_message'), 'agent123')
    assert found == report and cid == 'conv123'
    assert 'chainOfThought' not in found

def test_wrong_agent(report):
    with pytest.raises(DustError): extract_report(envelope(report), 'other_agent')

def test_running_is_not_final(report):
    with pytest.raises(DustError): extract_report(envelope(report, status='running'), 'agent123')

def test_settings_repr_has_no_secret():
    assert 'TOKENSECRET' not in repr(Settings('TOKENSECRET','w123','a123'))

def test_http_call_and_contract(report):
    response = Mock(status_code=200, content=b'{}')
    response.json.return_value = envelope(report)
    with patch('src.dust_client.requests.request', return_value=response) as req:
        result, _ = run_dust('test', Settings('TOKENSECRET','w123','agent123'))
        assert result == report
        assert req.call_args.kwargs['json']['blocking'] is True
        assert req.call_args.kwargs['json']['skipToolsValidation'] is False
        # Champs attendus par UserMessageContextSchema dans le SDK public Dust.
        # L'identité de l'application suffit ; aucune identité personnelle n'est envoyée.
        assert req.call_args.kwargs['json']['message']['context'] == {
            'username': 'reperes-citoyens', 'timezone': 'Europe/Paris', 'origin': 'api',
        }
        assert req.call_args.kwargs['allow_redirects'] is False
        assert req.call_count == 1

@pytest.mark.parametrize('code', [400, 401, 403, 404, 429, 500])
def test_http_errors_not_retried(code):
    with patch('src.dust_client.requests.request', return_value=Mock(status_code=code)) as req:
        with pytest.raises(DustError): run_dust('test', Settings('SECRET','w123','agent123'))
        assert req.call_count == 1

def test_timeout_not_retried():
    with patch('src.dust_client.requests.request', side_effect=requests.Timeout) as req:
        with pytest.raises(DustError, match='continuer'): run_dust('test', Settings('SECRET','w123','agent123'))
        assert req.call_count == 1

def test_list_excludes_private_configuration():
    response=Mock(status_code=200,content=b'{}')
    response.json.return_value={'agentConfigurations':[{'name':'agent','sId':'123','instructions':'PRIVATE'}]}
    with patch('src.dust_client.requests.request',return_value=response):
        assert list_agents(Settings('SECRET','w123','')) == [{'name':'agent','id':'123'}]

def test_demo_calls_no_network():
    with patch('src.dust_client.requests.request') as req:
        result=search('sujet','2024-01-01','2026-09-27','demo')
        assert result['mode']=='demo'
        req.assert_not_called()

def test_live_outside_date_rejected(report):
    with patch('src.service.run_dust',return_value=(report,'c123')):
        with pytest.raises(ReportError,match='période'): search('sujet','2024-01-01','2024-12-31','dust')

def test_inverted_dates():
    with pytest.raises(ReportError): search('sujet','2026-09-27','2024-01-01')
