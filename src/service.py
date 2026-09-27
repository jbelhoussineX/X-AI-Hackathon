"""Search contract expected by frontend/interface_b.py; no network on import."""
from copy import deepcopy
from datetime import date
from time import monotonic

from backend.dust.client import research
from backend.dust.adapter import validate_dust_report


def search(topic: str, start: str, end: str, mode: str = 'dust') -> dict:
    if mode != 'dust':
        raise ValueError('La démonstration est gérée par l’interface, sans appel externe.')
    if not isinstance(topic, str) or not 3 <= len(topic.strip()) <= 300:
        raise ValueError('Sujet requis de 3 à 300 caractères.')
    if date.fromisoformat(start).isoformat() != start or date.fromisoformat(end).isoformat() != end or start > end:
        raise ValueError('Période de publication invalide.')
    began = monotonic()
    result = research(topic.strip(), start=start, end=end)
    report = deepcopy(result.report)
    validate_dust_report(report)
    kept = []
    excluded = 0
    for document in report['documents']:
        publication = document['publication_date']
        if publication is not None and not start <= publication <= end:
            excluded += 1
            continue
        if publication is None:
            document['uncertainties'].append('Date de publication inconnue : période non confirmée.')
        kept.append(document)
    report['documents'] = kept
    ids = {d['id'] for d in kept}
    contacts = []
    for contact in report['contacts']:
        contact['document_ids'] = [ident for ident in contact['document_ids'] if ident in ids]
        if contact['document_ids']:
            contacts.append(contact)
    report['contacts'] = contacts
    if excluded:
        report['limitations'].append(f'{excluded} document(s) exclus : publication hors de la période demandée.')
    report['limitations'].append('Les pages sources et leurs extraits ne sont pas revérifiés indépendamment par ce service.')
    if len(kept) > 4 or len(contacts) > 3:
        raise ValueError('Réponse au-delà du périmètre de l’interface.')
    validate_dust_report(report)
    return {'mode': 'dust', 'report': report, 'duration_seconds': monotonic() - began}
