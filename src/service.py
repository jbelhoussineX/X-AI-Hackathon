"""Search contract expected by frontend/interface_b.py; no network on import."""
from copy import deepcopy
from datetime import date
from time import monotonic
import os

from backend.dust.client import research
from backend.dust.adapter import validate_dust_report
from backend.summary_service import synthesize_report
from backend.pipelex_summary import analyze_summary
from backend.source_verification import verify_sources


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
    if len(kept) > 4 or len(contacts) > 3:
        raise ValueError('Réponse au-delà du périmètre de l’interface.')
    validate_dust_report(report)
    verification = verify_sources(report)
    report = verification.report
    if os.environ.get('ENABLE_PIPELEX_CALLS', '').lower() == 'true' and verification.all_matched:
        report = synthesize_report(topic.strip(), report, analyze_summary)
    elif os.environ.get('ENABLE_PIPELEX_CALLS', '').lower() == 'true':
        report['limitations'].append('Synthèse Pipelex non exécutée : corpus vide ou sources non confirmées. Les résumés proviennent de Dust.')
    else:
        report['limitations'].append('Synthèse Pipelex désactivée : les résumés affichés proviennent de Dust.')
    return {'mode': 'dust', 'report': report, 'duration_seconds': monotonic() - began,
            'source_checks': verification.checks}
