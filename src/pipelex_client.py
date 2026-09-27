"""Frontière Streamlit / processus Pipelex. Aucun secret ni réseau à l'import."""
from __future__ import annotations

import json
import os
import subprocess
import sys

from src.contracts import ROOT, ReportError, validate_report


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
    'provider': 'La recherche OpenAI a échoué. Aucun nouvel essai automatique.',
}


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
            input=request, text=True, encoding="utf-8", capture_output=True, timeout=240,
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
        code = str(payload.get('error', 'provider'))
        raise PipelexError(ERRORS.get(code, ERRORS['provider'])) from None
    try:
        return validate_report(payload['report']), None
    except (KeyError, ReportError):
        raise PipelexError(ERRORS['format']) from None
