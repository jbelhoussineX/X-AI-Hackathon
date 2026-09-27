"""Hosted synthesis errors are actionable, redacted, and never retried here."""
import asyncio
from datetime import datetime, timezone
import socket
import traceback
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import httpx
from pipelex_sdk.error_models import RunErrorReport
from pipelex_sdk.errors import (
    ApiResponseError, ApiUnreachableError, RunFailedError, RunTimeoutError,
)
from pipelex_sdk.runs import RunStatus

from backend import pipelex_recent as hosted
from backend import recent_brief
from backend.generated.recent_brief.models import Request


RAW = 'SECRET-untrusted-provider-detail'


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    monkeypatch.setenv('PYTHON_DOTENV_DISABLED', '1')
    monkeypatch.setenv('DO_NOT_TRACK', '1')
    monkeypatch.setenv('ENABLE_PIPELEX_CALLS', 'true')
    monkeypatch.setenv('PIPELEX_EXECUTION_MODE', 'hosted')
    monkeypatch.setenv('PIPELEX_API_KEY', 'test-only-pipelex-key')
    monkeypatch.setattr(socket.socket, 'connect',
                        Mock(side_effect=AssertionError('Real network forbidden')))
    monkeypatch.setattr(socket, 'create_connection',
                        Mock(side_effect=AssertionError('Real network forbidden')))
    monkeypatch.setattr(hosted, 'read_bundle', Mock(return_value='test-only method bundle'))
    monkeypatch.setattr('frontend.profile.PROFILE_PATH', tmp_path / 'profiles.sqlite3')
    monkeypatch.setattr('frontend.profile.current_identity', lambda: None)


def client_with(monkeypatch, error=None, *, main_stuff=None):
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False
    if error is not None:
        client.start_and_wait.side_effect = error
    else:
        client.start_and_wait.return_value = SimpleNamespace(main_stuff=main_stuff)
    factory = Mock(return_value=client)
    monkeypatch.setattr(hosted, 'pipelex_client', factory)
    return factory, client


def request():
    return Request(topic='logement', corpus_json='{}')


def response_error(status):
    error = ApiResponseError(
        RAW, api_url='https://api.pipelex.com/?detail=' + RAW, status=status,
        status_text=RAW, response_body='{"untrusted": "' + RAW + '"}',
        server_message=RAW, request_id=RAW, title=RAW,
        problem={'detail': RAW, 'headers': {'Authorization': RAW}}, retryable=True)
    error.headers = {'Authorization': RAW}
    return error


def assert_redacted(error):
    assert RAW not in str(error)
    assert RAW not in repr(error)
    assert RAW not in ''.join(traceback.format_exception(error))
    assert 'Authorization' not in str(error)
    assert 'test-only-pipelex-key' not in str(error)


@pytest.mark.parametrize('key_value', [None, '', '   '])
def test_missing_key_fails_before_constructing_a_client(monkeypatch, key_value):
    if key_value is None:
        monkeypatch.delenv('PIPELEX_API_KEY', raising=False)
    else:
        monkeypatch.setenv('PIPELEX_API_KEY', key_value)
    factory = Mock(side_effect=AssertionError('A client must not be created'))
    monkeypatch.setattr(hosted, 'pipelex_client', factory)

    with pytest.raises(hosted.RecentProviderError, match='PIPELEX_API_KEY') as exc:
        asyncio.run(hosted.summarize(request()))

    factory.assert_not_called()
    assert_redacted(exc.value)


@pytest.mark.parametrize(('status', 'expected'), [
    (401, r'(?i)(clé|accès)'), (403, r'(?i)(clé|accès)'),
    (429, r'(?i)(limite|quota)'),
    (400, r'(?i)(requête|entrée|validation)'),
    (422, r'(?i)(requête|entrée|validation)'),
    (500, r'(?i)service'), (503, r'(?i)service'),
])
def test_http_error_is_fixed_safe_and_does_not_retry(monkeypatch, status, expected):
    factory, client = client_with(monkeypatch, response_error(status))

    with pytest.raises(hosted.RecentProviderError, match=expected) as exc:
        asyncio.run(hosted.summarize(request()))

    factory.assert_called_once_with()
    client.start_and_wait.assert_awaited_once()
    assert_redacted(exc.value)


def test_run_timeout_warns_that_remote_work_can_continue_without_retry(monkeypatch):
    factory, client = client_with(monkeypatch, RunTimeoutError(RAW, RAW, 180))

    with pytest.raises(hosted.RecentProviderError) as exc:
        asyncio.run(hosted.summarize(request()))

    assert 'distant' in str(exc.value).lower()
    assert 'continu' in str(exc.value).lower()
    factory.assert_called_once_with()
    client.start_and_wait.assert_awaited_once()
    assert_redacted(exc.value)


@pytest.mark.parametrize('typed', [True, False])
def test_forbidden_does_not_claim_key_is_invalid_or_no_run_was_started(monkeypatch, typed):
    failure = (response_error(403) if typed else httpx.HTTPStatusError(
        RAW, request=httpx.Request('GET', 'https://api.pipelex.com/v1/runs/test/status'),
        response=httpx.Response(403)))
    _, client = client_with(monkeypatch, failure)

    with pytest.raises(hosted.RecentProviderError) as exc:
        asyncio.run(hosted.summarize(request()))

    message = str(exc.value)
    assert 'ne permet pas de conclure' in message
    assert 'droits API' in message
    assert 'pendant le suivi' in message
    assert 'Aucun appel IA lancé' not in message
    client.start_and_wait.assert_awaited_once()
    assert_redacted(exc.value)


def test_dns_failure_is_a_safe_connection_error_without_retry(monkeypatch):
    failure = ApiUnreachableError(RAW, 'https://api.pipelex.com/?detail=' + RAW,
                                  code='ConnectError')
    _, client = client_with(monkeypatch, failure)

    with pytest.raises(hosted.RecentProviderError, match=r'(?i)connexion') as exc:
        asyncio.run(hosted.summarize(request()))

    client.start_and_wait.assert_awaited_once()
    assert_redacted(exc.value)


@pytest.mark.parametrize(('domain', 'expected'), [
    ('config', r'(?i)config'), ('input', r'(?i)(requête|entrée|validation)'),
])
def test_run_failure_uses_domain_not_the_verbose_provider_text(monkeypatch, domain, expected):
    failure = RunFailedError(RAW, RAW, RunStatus.FAILED,
        RunErrorReport(error_domain=domain, message=RAW, title=RAW, retryable=True,
                       provider_metadata={'message': RAW, 'request_id': RAW}))
    _, client = client_with(monkeypatch, failure)

    with pytest.raises(hosted.RecentProviderError, match=expected) as exc:
        asyncio.run(hosted.summarize(request()))

    client.start_and_wait.assert_awaited_once()
    assert_redacted(exc.value)


def test_invalid_success_body_does_not_expose_validation_input_or_retry(monkeypatch):
    _, client = client_with(monkeypatch, main_stuff={'items': RAW, 'limitations': []})

    with pytest.raises(hosted.RecentProviderError, match=r'(?i)format') as exc:
        asyncio.run(hosted.summarize(request()))

    client.start_and_wait.assert_awaited_once()
    assert_redacted(exc.value)


def result():
    now = datetime.now(timezone.utc).isoformat()
    url = 'https://www.senat.fr/leg/ppl25-001.html'
    return dict(topic='logement', start='2026-09-01', end='2026-09-27',
        collected_at=now, datasets=[], limitations=[], events=[dict(
            id='test-event', title='Texte fictif', event_date='2026-09-20',
            event='Dépôt', category='procedure', decision=None, provider='senat',
            date_kind='publication', dossier_url=url, source_url=url,
            source_location='Test', retrieved_at=now,
            content_passages=['Ce passage fictif du test concerne une proposition sur le logement étudiant.'])])


def test_build_propagates_a_safe_brief_error_from_the_hosted_client(monkeypatch):
    _, client = client_with(monkeypatch, response_error(429))
    monkeypatch.setattr(recent_brief, 'collect_sources',
                        Mock(side_effect=AssertionError('Corpus already supplied by the test')))

    with pytest.raises(recent_brief.BriefError, match=r'(?i)(limite|quota)') as exc:
        recent_brief.build(result())

    client.start_and_wait.assert_awaited_once()
    assert_redacted(exc.value)


def test_ui_displays_safe_hosted_error_without_retry_on_rerun(monkeypatch):
    from streamlit.testing.v1 import AppTest

    _, client = client_with(monkeypatch, response_error(403))
    monkeypatch.setattr('backend.recent_agent.collect_candidates', Mock(return_value=result()))
    app = AppTest.from_string(
        'from frontend.recent_activity import render\nrender()').run()
    assert not app.exception
    app.text_input(key='recent_topic').set_value('logement').run()
    client.start_and_wait.assert_not_awaited()
    next(button for button in app.button if button.label == 'Rechercher').click().run()

    assert not app.exception
    messages = '\n'.join(error.value for error in app.error)
    assert 'clé' in messages.lower() or 'accès' in messages.lower()
    assert RAW not in messages
    assert 'Authorization' not in messages
    assert 'recent_brief' not in app.session_state
    client.start_and_wait.assert_awaited_once()
    app.run()
    assert not app.exception
    client.start_and_wait.assert_awaited_once()
