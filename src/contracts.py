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
REPORT_ITEM_LIMITS = {'documents': 4, 'contacts': 3}
REQUIRED_TEXT_FIELDS = {
    '': ('topic', 'scope'),
    'documents': ('id', 'title', 'summary'),
    'contacts': ('name', 'role', 'relation'),
}

class ReportError(ValueError):
    """Une sortie ne respecte pas le contrat convenu entre l'agent et l'interface."""

    def __init__(self, message: str, *, reason: str = 'report_contract', field: str | None = None):
        self.reason = reason
        self.field = field
        super().__init__(message)

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
            raise ReportError('Un lien de source ne respecte pas les règles HTTPS publiques.', reason='source_url')
        if not item['excerpt'].strip():
            raise ReportError('Un extrait justificatif est vide.', reason='empty_excerpt')

def validate_report(report: dict) -> dict:
    errors = list(Draft202012Validator(SCHEMA).iter_errors(report))
    if errors:
        # Éviter de recopier le contenu de l'utilisateur dans un message d'erreur.
        raise ReportError('La réponse ne respecte pas report.schema.json.', reason='report_schema')
    if any(len(report[group]) > limit for group, limit in REPORT_ITEM_LIMITS.items()):
        raise ReportError('Limite du prototype : quatre documents et trois interlocuteurs.', reason='item_limit')
    for field in REQUIRED_TEXT_FIELDS['']:
        if not report[field].strip():
            raise ReportError('Le sujet ou le périmètre est vide.', reason='empty_field', field=field)
    ids = [d['id'] for d in report['documents']]
    if len(ids) != len(set(ids)):
        raise ReportError('Les identifiants de documents doivent être uniques.', reason='duplicate_document_id')
    for d in report['documents']:
        for field in REQUIRED_TEXT_FIELDS['documents']:
            if not d[field].strip():
                raise ReportError('Un document contient un champ obligatoire vide.',
                                  reason='empty_field', field='documents.' + field)
        for field in ('publication_date', 'stage_date'):
            if d[field] is not None:
                try:
                    if date.fromisoformat(d[field]).isoformat() != d[field]:
                        raise ValueError
                except ValueError as exc:
                    raise ReportError('Les dates doivent être YYYY-MM-DD ou null.', reason='invalid_date') from exc
        _check_evidence(d['evidence'])
        purposes = {x['purpose'] for x in d['evidence']}
        if 'contenu' not in purposes:
            raise ReportError('Un document ne possède pas de preuve de contenu.', reason='missing_content_evidence')
        if d['stage'] is not None and ('statut' not in purposes or not d['stage'].strip()):
            raise ReportError('Un statut annoncé doit avoir une preuve dédiée.', reason='invalid_stage_evidence')
        if d['stage'] is None and d['stage_date'] is not None:
            raise ReportError('La date de statut nécessite un statut renseigné.', reason='stage_date_without_stage')
    for c in report['contacts']:
        for field in REQUIRED_TEXT_FIELDS['contacts']:
            if not c[field].strip():
                raise ReportError('Un interlocuteur contient un champ obligatoire vide.',
                                  reason='empty_field', field='contacts.' + field)
        if not c['document_ids'] or not set(c['document_ids']).issubset(ids):
            raise ReportError('Un interlocuteur doit renvoyer à un document présent.', reason='contact_document_reference')
        _check_evidence(c['evidence'])
        if not any(e['purpose'] == 'relation' for e in c['evidence']):
            raise ReportError('Le lien de l’interlocuteur avec le sujet doit être sourcé.', reason='missing_relation_evidence')
        if c['contact_url'] is not None:
            if not public_url(c['contact_url']):
                raise ReportError('La page de contact doit être une URL HTTPS publique.', reason='contact_url')
            if not any(e['purpose'] == 'contact' and e['url'] == c['contact_url'] for e in c['evidence']):
                raise ReportError('La page de contact doit avoir un extrait dédié.', reason='missing_contact_evidence')
    if not report['documents'] and not report['limitations']:
        raise ReportError('Une recherche vide doit expliquer ses limites.', reason='missing_limitations')
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
