"""Hosted transport failures stay actionable without exposing SDK diagnostics."""
from unittest.mock import Mock

import pytest
from pipelex_sdk.errors import ApiUnreachableError

from src.pipelex_client import PipelexError
from src.service import search


@pytest.mark.parametrize('code,expected', [
    ('ABORT_TIMEOUT', 'délai'),
    ('ConnectError', 'connexion sécurisée'),
    ('Unexpected_SECRET_CODE', 'interrompue'),
])
def test_hosted_error_is_safe_and_never_retried(monkeypatch, code, expected):
    monkeypatch.setenv('ENABLE_PIPELEX_CALLS', 'true')
    monkeypatch.setenv('PIPELEX_EXECUTION_MODE', 'hosted')
    provider = Mock(side_effect=ApiUnreachableError(
        'SECRET_DIAGNOSTIC', api_url='https://SECRET_HOST', code=code))
    monkeypatch.setattr('src.service.research', provider)
    with pytest.raises(PipelexError) as error:
        search('Logement', '2025-01-01', '2026-09-27', 'pipelex')
    assert expected in str(error.value)
    assert 'SECRET' not in str(error.value)
    assert 'avant de relancer' in str(error.value)
    provider.assert_called_once()
