"""Explicit opt-in for external inference; imports alone never create clients."""
import os
from pipelex_sdk.client import PipelexAPIClient


def require_enabled(service: str) -> None:
    if os.environ.get(f'ENABLE_{service}_CALLS', '').lower() != 'true':
        raise RuntimeError(f'Appels {service} désactivés.')


def pipelex_client() -> PipelexAPIClient:
    require_enabled('PIPELEX')
    if not os.environ.get('PIPELEX_API_KEY', '').strip():
        raise RuntimeError('PIPELEX_API_KEY absente de l’environnement local.')
    return PipelexAPIClient(base_url='https://api.pipelex.com', request_timeout_seconds=60)
