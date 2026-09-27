"""Contrat partagé. Ces contrôles vérifient la structure, PAS la vérité des sources."""
from __future__ import annotations
import ipaddress
import json
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / 'schemas/report.schema.json').read_text(encoding='utf-8'))

class ReportError(ValueError):
    """Une sortie ne respecte pas le contrat convenu entre l'agent et l'interface."""

def public_url(value: str) -> bool:
    """Filtre syntaxique de liens. Ne fait PAS de DNS, de requête ou de contrôle factuel."""
    try:
        u = urlsplit(value)
        if u.scheme != 'https' or not u.hostname or u.username or u.password:
            return False
        if u.port not in (None, 443):
            return False
        h = u.hostname.lower()
        if '.' not in h or h.endswith(('.local', '.localhost', '.internal')):
            return False
        if any(c.isspace() for c in value):
            return False
        try:
            return ipaddress.ip_address(h).is_global
        except ValueError:
            return True
    except (ValueError, TypeError):
        return False

def _check_evidence(items: list[dict]) -> None:
    for item in items:
        if not public_url(item['url']):
            raise ReportError('Un lien de source ne respecte pas les règles HTTPS publiques.')
        if not item['excerpt'].strip():
            raise ReportError('Un extrait justificatif est vide.')

def validate_report(report: dict) -> dict:
    errors = list(Draft202012Validator(SCHEMA).iter_errors(report))
    if errors:
        # Éviter de recopier le contenu de l'utilisateur dans un message d'erreur.
        raise ReportError('La réponse ne respecte pas report.schema.json.')
    if len(report['documents']) > 4 or len(report['contacts']) > 3:
        raise ReportError('Limite du prototype : quatre documents et trois interlocuteurs.')
    if not report['topic'].strip() or not report['scope'].strip():
        raise ReportError('Le sujet ou le périmètre est vide.')
    ids = [d['id'] for d in report['documents']]
    if len(ids) != len(set(ids)):
        raise ReportError('Les identifiants de documents doivent être uniques.')
    for d in report['documents']:
        if not all(d[x].strip() for x in ('id', 'title', 'summary')):
            raise ReportError('Un document contient un champ obligatoire vide.')
        for field in ('publication_date', 'stage_date'):
            if d[field] is not None:
                try:
                    if date.fromisoformat(d[field]).isoformat() != d[field]:
                        raise ValueError
                except ValueError as exc:
                    raise ReportError('Les dates doivent être YYYY-MM-DD ou null.') from exc
        _check_evidence(d['evidence'])
        purposes = {x['purpose'] for x in d['evidence']}
        if 'contenu' not in purposes:
            raise ReportError('Un document ne possède pas de preuve de contenu.')
        if d['stage'] is not None and ('statut' not in purposes or not d['stage'].strip()):
            raise ReportError('Un statut annoncé doit avoir une preuve dédiée.')
        if d['stage'] is None and d['stage_date'] is not None:
            raise ReportError('La date de statut nécessite un statut renseigné.')
    for c in report['contacts']:
        if not all(c[x].strip() for x in ('name', 'role', 'relation')):
            raise ReportError('Un interlocuteur contient un champ obligatoire vide.')
        if not c['document_ids'] or not set(c['document_ids']).issubset(ids):
            raise ReportError('Un interlocuteur doit renvoyer à un document présent.')
        _check_evidence(c['evidence'])
        if not any(e['purpose'] == 'relation' for e in c['evidence']):
            raise ReportError('Le lien de l’interlocuteur avec le sujet doit être sourcé.')
        if c['contact_url'] is not None:
            if not public_url(c['contact_url']):
                raise ReportError('La page de contact doit être une URL HTTPS publique.')
            if not any(e['purpose'] == 'contact' and e['url'] == c['contact_url'] for e in c['evidence']):
                raise ReportError('La page de contact doit avoir un extrait dédié.')
    if not report['documents'] and not report['limitations']:
        raise ReportError('Une recherche vide doit expliquer ses limites.')
    return report

def parse_report(text: str) -> dict:
    """Accepte du JSON pur ou un unique bloc ```json ; ne devine pas un JSON caché."""
    if not isinstance(text, str) or len(text) > 200_000:
        raise ReportError('Réponse vide, invalide ou trop volumineuse.')
    text = text.strip()
    if text.startswith('```'):
        lines = text.splitlines()
        if lines[-1].strip() != '```' or lines[0].strip() not in ('```', '```json'):
            raise ReportError('Bloc JSON incomplet.')
        text = '\n'.join(lines[1:-1])
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise ReportError('Réponse non JSON : vérifier le format structuré de l’agent.') from exc
    return validate_report(data)
