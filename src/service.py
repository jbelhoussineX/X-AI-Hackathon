"""Search contract expected by frontend/interface_b.py; no network on import."""
from copy import deepcopy
from datetime import date
from time import monotonic
from backend.clients import require_enabled

from backend.pipelex_research import research
from backend.report_contract import validate_report


def search(topic: str, start: str, end: str, mode: str = 'pipelex') -> dict:
    if mode != 'pipelex':
        raise ValueError('La démonstration est gérée par l’interface, sans appel externe.')
    if not isinstance(topic, str) or not 3 <= len(topic.strip()) <= 300:
        raise ValueError('Sujet requis de 3 à 300 caractères.')
    if date.fromisoformat(start).isoformat() != start or date.fromisoformat(end).isoformat() != end or start > end:
        raise ValueError('Période de publication invalide.')
    require_enabled('PIPELEX')
    began = monotonic()
    result = research(topic.strip(), start=start, end=end)
    report = deepcopy(result.report)
    validate_report(report)
    kept: list[dict] = []
    excluded = 0
    indices = {}
    for index, document in enumerate(report['documents']):
        publication = document['publication_date']
        if publication is not None and not start <= publication <= end:
            excluded += 1
            continue
        if publication is None:
            document['uncertainties'].append('Date de publication inconnue : période non confirmée.')
        indices[('document', index)] = len(kept)
        kept.append(document)
    report['documents'] = kept
    ids = {d['id'] for d in kept}
    contacts: list[dict] = []
    for index, contact in enumerate(report['contacts']):
        contact['document_ids'] = [ident for ident in contact['document_ids'] if ident in ids]
        if contact['document_ids']:
            indices[('contact', index)] = len(contacts)
            contacts.append(contact)
    report['contacts'] = contacts
    if excluded:
        report['limitations'].append(f'{excluded} document(s) exclus : publication hors de la période demandée.')
    if len(kept) > 4 or len(contacts) > 3:
        raise ValueError('Réponse au-delà du périmètre de l’interface.')
    validate_report(report)
    # Remap evidence checks after filtering documents and linked contacts.
    checks = []
    for original in result.checks:
        key = (original['entity_type'], original['entity_index'])
        if key in indices:
            check = deepcopy(original)
            check['entity_index'] = indices[key]
            checks.append(check)
    return {'mode': 'pipelex', 'report': report, 'duration_seconds': monotonic() - began,
            'source_checks': checks}
