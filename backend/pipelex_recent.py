"""Typed hosted Pipelex call; prepare_inputs is needed for file-bearing methods only."""
import os

import httpx
from pydantic import ValidationError
from pipelex_sdk.errors import (
    ApiResponseError, ApiUnreachableError, MissingMainStuffError,
    PipelineExecuteTimeoutError, RunFailedError, RunLifecycleUnavailableError,
    RunTimeoutError,
)
from pipelex_sdk.runs import WaitForResultOptions
from backend.clients import pipelex_client, require_enabled
from backend.method_bundle import read_bundle
from backend.generated.recent_brief.models import Request, Brief


class RecentProviderError(RuntimeError):
    """Only fixed public messages: never raw SDK errors, bodies or credentials."""


_MESSAGES = {
    'credentials': 'Clé API Pipelex refusée ou accès non autorisé. Vérifie PIPELEX_API_KEY et les droits de cette clé dans Pipelex.',
    'access': 'Accès à l’API Pipelex hébergée refusé. Le code 403 ne permet pas de conclure que la clé est invalide. '
              'Vérifie le type de clé et demande à l’équipe Pipelex de confirmer les droits API de ton compte. '
              'Consulte aussi l’activité Pipelex avant de relancer : le refus peut survenir pendant le suivi d’une génération.',
    'quota': 'Limite Pipelex atteinte. Vérifie les crédits et les limites de ta clé API dans Pipelex avant de relancer.',
    'request': 'L’API Pipelex a refusé la requête. Vérifie la méthode et les paramètres envoyés.',
    'configuration': 'Configuration de la méthode Pipelex indisponible ou incompatible. Vérifie le modèle et les accès de ton projet Pipelex.',
    'network': 'Connexion à l’API Pipelex impossible. Vérifie la connexion réseau et la disponibilité de Pipelex.',
    'timeout': 'Délai d’attente de l’API Pipelex dépassé. Une génération distante peut continuer ; vérifie son état dans Pipelex avant de relancer.',
    'server': 'Le service API Pipelex a rencontré une erreur. Vérifie son état et l’activité de ton compte avant de relancer.',
    'format': 'L’API Pipelex a retourné une synthèse au format invalide. Aucun résumé affiché.',
    'provider': 'La génération sur l’API Pipelex a échoué. Consulte l’activité de ton compte Pipelex avant de relancer.',
}


def _failure(code: str, status=None) -> RecentProviderError:
    message = _MESSAGES.get(code, _MESSAGES['provider'])
    # Strict allowlist: values not recognized by the client stay private.
    if type(status) is int and status in (400, 401, 403, 404, 408, 409, 422, 429, 500, 502, 503, 504):
        message += f' Diagnostic : HTTP {status}.'
    return RecentProviderError(message + ' Aucune relance automatique.')


def _response_failure(exc: ApiResponseError) -> RecentProviderError:
    # Structured classification first, with HTTP status as a conservative fallback.
    if exc.code == 'pipelex_api_key_limit_reached':
        code = 'quota'
    elif exc.error_domain == 'config':
        code = 'configuration'
    elif exc.error_domain == 'input':
        code = 'request'
    elif exc.status == 403:
        code = 'access'
    elif exc.status == 401:
        code = 'credentials'
    elif exc.status == 429:
        code = 'quota'
    elif exc.status in (408, 504):
        code = 'timeout'
    elif exc.status in (400, 422):
        code = 'request'
    elif exc.status == 404:
        code = 'configuration'
    elif type(exc.status) is int and 500 <= exc.status < 600:
        code = 'server'
    else:
        code = 'provider'
    return _failure(code, exc.status)


async def summarize(request: Request) -> Brief:
    require_enabled('PIPELEX')
    if not os.environ.get('PIPELEX_API_KEY', '').strip():
        raise RecentProviderError('Clé API Pipelex absente. Renseigne PIPELEX_API_KEY dans la configuration locale, '
                                  'puis redémarre Streamlit. Aucun appel IA lancé.')
    try:
        contents = read_bundle('recent_brief')
    except (OSError, RuntimeError, ValueError):
        raise _failure('configuration') from None
    return await run_hosted_method(request, contents, 'recent_brief.summarize', Brief)


async def run_hosted_method(request, contents, pipe_code, output_type):
    require_enabled('PIPELEX')
    if not os.environ.get('PIPELEX_API_KEY', '').strip():
        raise RecentProviderError('Clé API Pipelex absente. Renseigne PIPELEX_API_KEY puis redémarre Streamlit. Aucun appel IA lancé.')
    try:
        async with pipelex_client() as client:
            result = await client.start_and_wait(
                pipe_code=pipe_code, mthds_contents=contents,
                inputs={'request': request.model_dump()},
                wait_options=WaitForResultOptions(timeout_seconds=180))
        return output_type.model_validate(result.main_stuff)
    except ApiResponseError as exc:
        raise _response_failure(exc) from None
    except ApiUnreachableError as exc:
        raise _failure('timeout' if exc.code == 'ABORT_TIMEOUT' else 'network') from None
    except (RunTimeoutError, PipelineExecuteTimeoutError, httpx.TimeoutException):
        raise _failure('timeout') from None
    except RunFailedError as exc:
        domain = getattr(exc.error, 'error_domain', None)
        code = ('timeout' if exc.status == 'TIMED_OUT' else
                'configuration' if domain == 'config' else
                'request' if domain == 'input' else 'provider')
        raise _failure(code) from None
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        code = ('access' if status == 403 else 'credentials' if status == 401 else 'quota' if status == 429 else
                'timeout' if status in (408, 504) else 'server' if status >= 500 else 'request')
        raise _failure(code, status) from None
    except httpx.RequestError:
        raise _failure('network') from None
    except RunLifecycleUnavailableError:
        raise _failure('configuration') from None
    except (MissingMainStuffError, ValidationError):
        raise _failure('format') from None
    except Exception:
        raise _failure('provider') from None
