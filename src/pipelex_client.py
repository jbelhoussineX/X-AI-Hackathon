"""Frontière Streamlit / processus Pipelex. Aucun secret ni réseau à l'import."""
from __future__ import annotations

import json
import os
import subprocess
import sys

from src.contracts import ROOT, REQUIRED_TEXT_FIELDS, ReportError, validate_report


class PipelexError(RuntimeError):
    """Erreur publique : ne contient jamais les journaux bruts du fournisseur."""


ERRORS = {
    'credentials': 'Clé OpenAI absente ou refusée. Vérifier OPENAI_API_KEY dans les variables du processus.',
    'quota': 'Limite OpenAI atteinte. Vérifier les crédits ou les limites de débit avant de relancer.',
    'timeout': 'Délai dépassé. Une génération distante peut continuer ; vérifier son état avant de relancer.',
    'network': 'Connexion à OpenAI impossible. Aucun nouvel essai automatique.',
    'sources': 'La recherche n’a pas fourni de sources exploitables. Aucun résultat fictif ne la remplace.',
    'format': 'Le rapport ne respecte pas les contrôles du projet. Aucun résultat affiché.',
    'configuration': 'Configuration Pipelex indisponible ou incompatible. Consulter le guide d’installation.',
    'request': 'OpenAI a refusé la requête : vérifier le modèle, les paramètres ou le format JSON demandé. Aucun nouvel essai automatique.',
    'model': 'Le modèle demandé est introuvable ou inaccessible pour ce projet OpenAI. Aucun nouvel essai automatique.',
    'server': 'OpenAI a renvoyé une erreur de service. Aucun nouvel essai automatique.',
    'internal': 'Le traitement local a échoué. Aucun nouvel essai automatique.',
    'provider': 'La recherche OpenAI a échoué. Aucun nouvel essai automatique.',
}


# Fixed vocabulary only: never forward raw API messages, headers, request bodies
# or arbitrary field names. These details also survive Pipelex's exception wrappers.
VALIDATION_REASONS = {
    'excerpt_not_found': 'Un extrait du rapport est absent du texte officiel effectivement collecté.',
    'report_contract': 'Une règle de validation du rapport a échoué.',
    'report_schema': 'La structure JSON ne correspond pas au schéma du rapport.',
    'item_limit': 'Le rapport dépasse quatre documents ou trois interlocuteurs.',
    'empty_field': 'Un champ obligatoire est vide.',
    'duplicate_document_id': 'Plusieurs documents ont le même identifiant.',
    'invalid_date': 'Une date est invalide ou ne respecte pas YYYY-MM-DD.',
    'source_url': 'Une URL de preuve ne respecte pas les règles HTTPS publiques.',
    'empty_excerpt': 'Un extrait justificatif est vide.',
    'missing_content_evidence': 'Un document manque de preuve de contenu.',
    'invalid_stage_evidence': 'Un statut est vide ou manque de preuve dédiée.',
    'stage_date_without_stage': 'Une date de statut est fournie sans statut.',
    'contact_document_reference': 'Un interlocuteur ne référence pas un document présent.',
    'missing_relation_evidence': 'La relation d’un interlocuteur manque de preuve.',
    'contact_url': 'Une page de contact ne respecte pas les règles HTTPS publiques.',
    'missing_contact_evidence': 'Une page de contact manque de preuve dédiée.',
    'missing_limitations': 'Le rapport vide ne précise pas ses limites.',
    'document_kind': 'Un document n’est ni un projet ni une proposition de loi.',
    'publication_outside_period': 'La publication d’un document sort de la période demandée.',
    'unobserved_source': 'Une preuve utilise une URL absente des sources de recherche.',
    'invalid_json': 'La réponse reçue n’est pas un JSON valide.',
    'max_output_tokens': 'La réponse a été tronquée à la limite de tokens de sortie.',
    'content_filter': 'La réponse a été interrompue par le filtre du fournisseur.',
    'response_incomplete': 'Le fournisseur n’a pas terminé la réponse.',
    'response_refusal': 'Le modèle a renvoyé un refus au lieu du rapport.',
    'empty_response': 'Le fournisseur a renvoyé une réponse sans texte.',
}

DIAGNOSTIC_VALUES: dict[str, set[str | int]] = {
    'reason': set(VALIDATION_REASONS),
    'field': {f'{group}.{name}' if group else name
              for group, fields in REQUIRED_TEXT_FIELDS.items() for name in fields},
    'stage': {'collecter', 'evaluer', 'completer', 'rediger'},
    'http_status': {400, 401, 403, 404, 408, 409, 422, 429, 500, 502, 503, 504},
    'type': {'BadRequestError', 'NotFoundError', 'UnprocessableEntityError', 'InternalServerError',
             'AuthenticationError', 'PermissionDeniedError', 'RateLimitError', 'APIConnectionError',
             'APITimeoutError', 'APIStatusError', 'TypeError', 'ValueError', 'KeyError', 'AttributeError'},
    'code': {'unsupported_parameter', 'unsupported_value', 'invalid_value', 'invalid_type',
             'invalid_request_error', 'model_not_found', 'invalid_api_key', 'invalid_json_schema',
             'context_length_exceeded', 'rate_limit_exceeded', 'insufficient_quota',
             'server_error', 'content_policy_violation'},
    'param': {'model', 'tools', 'tools[0]', 'tools[0].type', 'tools[0].filters',
              'tools[0].filters.allowed_domains', 'tools[0].search_context_size',
              'tool_choice', 'max_tool_calls', 'max_output_tokens', 'include', 'include[0]',
              'text', 'text.format', 'text.format.schema', 'text.format.name', 'text.format.strict',
              'input', 'instructions', 'store'},
}


def safe_diagnostic(value: object) -> dict:
    if not isinstance(value, dict):
        return {}
    return {key: value[key] for key, allowed in DIAGNOSTIC_VALUES.items()
            if type(value.get(key)) in (str, int) and value[key] in allowed}


def failure_message(code: object, diagnostic: object = None) -> str:
    message = ERRORS.get(code, ERRORS['provider']) if isinstance(code, str) else ERRORS['provider']
    details = safe_diagnostic(diagnostic)
    reason = details.pop('reason', None)
    if reason:
        message += ' Motif : ' + VALIDATION_REASONS[reason]
    if details:
        labels = {'stage': 'étape', 'http_status': 'HTTP', 'type': 'type', 'code': 'code',
                  'param': 'paramètre', 'field': 'champ'}
        message += ' Diagnostic : ' + ', '.join(f'{labels[key]}={value}' for key, value in details.items()) + '.'
    return message


def run_pipelex(topic: str, start: str, end: str) -> tuple[dict, None]:
    from backend.clients import require_enabled
    require_enabled('PIPELEX')
    request = json.dumps({'topic': topic, 'start': start, 'end': end}, ensure_ascii=False)
    environment = os.environ.copy()
    environment['DO_NOT_TRACK'] = '1'
    environment['PYTHONIOENCODING'] = 'utf-8'
    environment['PYTHON_DOTENV_DISABLED'] = '1'
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'src.pipelex_worker'], cwd=ROOT,
            input=request, text=True, encoding="utf-8", capture_output=True, timeout=420,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            env=environment, check=False,
        )
    except subprocess.TimeoutExpired:
        raise PipelexError(ERRORS['timeout']) from None
    except OSError:
        raise PipelexError(ERRORS['configuration']) from None
    try:
        if len(result.stdout) > 250_000:
            raise ValueError
        payload = json.loads(result.stdout)
        if not isinstance(payload, dict):
            raise ValueError
    except (ValueError, TypeError):
        raise PipelexError(ERRORS['configuration']) from None
    if result.returncode != 0 or payload.get('ok') is not True:
        code = payload.get('error')
        raise PipelexError(failure_message(code, payload.get('diagnostic'))) from None
    try:
        return validate_report(payload['report']), None
    except ReportError as exc:
        raise PipelexError(failure_message('format', {'reason': exc.reason, 'field': exc.field})) from None
    except KeyError:
        raise PipelexError(ERRORS['format']) from None
