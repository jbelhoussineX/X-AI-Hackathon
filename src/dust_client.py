"""Adaptateur Dust minimal. Aucune requête réelle n'est faite à l'import du module.
Documentation : https://docs.dust.tt/api-reference/conversations/create-a-new-conversation
Authentification réelle et sorties de votre agent à tester dans votre espace partenaire.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import os
import re
import requests
from dotenv import load_dotenv
from src.contracts import ROOT, ReportError, parse_report

class DustError(RuntimeError):
    pass

@dataclass(frozen=True)
class Settings:
    api_key: str = field(repr=False)
    workspace_id: str
    agent_id: str
    timeout: int = 120

    @classmethod
    def load(cls, require_agent: bool = True) -> 'Settings':
        load_dotenv(ROOT / '.env', override=False)
        key = os.getenv('DUST_API_KEY', '').strip()
        wid = os.getenv('DUST_WORKSPACE_ID', '').strip()
        aid = os.getenv('DUST_AGENT_ID', '').strip()
        if not key or not wid or (require_agent and not aid):
            raise DustError('Compléter localement .env : DUST_API_KEY, DUST_WORKSPACE_ID et DUST_AGENT_ID.')
        for value in ([wid, aid] if require_agent else [wid]):
            if not re.fullmatch(r'[A-Za-z0-9_-]+', value):
                raise DustError('Un identifiant est invalide : utiliser son ID, pas son URL ni @nom.')
        try:
            timeout = int(os.getenv('DUST_TIMEOUT_SECONDS', '120'))
        except ValueError as exc:
            raise DustError('DUST_TIMEOUT_SECONDS doit être un entier.') from exc
        if not 15 <= timeout <= 180:
            raise DustError('Choisir un délai entre 15 et 180 secondes.')
        return cls(key, wid, aid, timeout)

def _request(settings: Settings, method: str, suffix: str, payload: dict | None = None) -> dict:
    url = f'https://dust.tt/api/v1/w/{settings.workspace_id}/assistant/{suffix}'
    try:
        response = requests.request(
            method, url,
            headers={'Authorization': f'Bearer {settings.api_key}', 'Content-Type': 'application/json'},
            json=payload, timeout=(10, settings.timeout), allow_redirects=False,
        )
    except requests.Timeout as exc:
        raise DustError('Délai dépassé. Ne pas relancer automatiquement : le calcul peut continuer chez Dust. Vérifier la conversation dans Dust avant un nouvel essai.') from exc
    except requests.RequestException as exc:
        raise DustError('Connexion Dust impossible. Vérifier le réseau ; aucune relance automatique.') from exc
    messages = {
        400: 'Requête refusée : vérifier le schéma de l’API et la configuration de l’agent.',
        401: 'Authentification refusée : vérifier la clé dans .env sans la publier.',
        403: 'Accès refusé : vérifier les permissions et l’accès programmatique de l’espace.',
        404: 'Ressource introuvable : vérifier l’espace, l’agent et l’URL API de votre région.',
        429: 'Limite atteinte : arrêter les essais et vérifier les quotas partenaires.',
    }
    if response.status_code >= 300:
        raise DustError(messages.get(response.status_code, f'Erreur HTTP {response.status_code}. Aucune relance automatique.'))
    if len(response.content) > 8_000_000:
        raise DustError('Réponse API trop volumineuse pour ce prototype.')
    try:
        result = response.json()
    except ValueError as exc:
        raise DustError('La réponse HTTP de Dust n’est pas du JSON.') from exc
    if not isinstance(result, dict):
        raise DustError('La réponse API de Dust n’est pas un objet.')
    return result

def list_agents(settings: Settings) -> list[dict]:
    data = _request(settings, 'GET', 'agent_configurations')
    agents = data.get('agentConfigurations')
    if not isinstance(agents, list):
        raise DustError('Format de liste d’agents inattendu. Consulter la documentation API.')
    # Ne renvoie pas les instructions ni les données privées d'autres agents.
    return [{'name': a.get('name'), 'id': a.get('sId')} for a in agents if isinstance(a, dict)]

def extract_report(payload: dict, agent_id: str) -> tuple[dict, str | None]:
    conversation = payload.get('conversation', {})
    content = conversation.get('content', [])
    if not isinstance(content, list):
        raise DustError('Structure de conversation inattendue.')
    messages = [m for group in content for m in (group if isinstance(group, list) else [group]) if isinstance(m, dict)]
    # On ne lit JAMAIS chainOfThought, les instructions de configuration ou les messages utilisateurs.
    candidates = [m for m in messages if (m.get('configuration') or {}).get('sId') == agent_id and (m.get('type') == 'agent' or (m.get('type') is None and 'rawContents' in m))]
    if not candidates:
        raise DustError('Aucune réponse de l’agent ciblé. Vérifier DUST_AGENT_ID, la publication et les permissions.')
    last = candidates[-1]
    if last.get('error') or last.get('status') not in ('succeeded', 'completed'):
        raise DustError('La génération n’est pas terminée ou a échoué. Ouvrir Dust pour vérifier une éventuelle validation d’outil.')
    raw = last.get('rawContents') or []
    texts = [x['content'] for x in raw if isinstance(x, dict) and isinstance(x.get('content'), str)]
    if isinstance(last.get('content'), str):
        texts.append(last['content'])
    for text in reversed(texts):
        try:
            return parse_report(text), conversation.get('sId')
        except ReportError:
            continue
    raise ReportError('Aucune réponse finale conforme au contrat. Contrôler la réponse dans Dust ; aucune réparation silencieuse par une autre IA.')

def run_dust(message: str, settings: Settings | None = None) -> tuple[dict, str | None]:
    settings = settings or Settings.load()
    data = _request(settings, 'POST', 'conversations', {
        'message': {'content': message, 'mentions': [{'configurationId': settings.agent_id}]},
        'title': 'Recherche citoyenne — prototype',
        'blocking': True,
        'skipToolsValidation': False,
    })
    return extract_report(data, settings.agent_id)
