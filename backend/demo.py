"""Deterministic fictional demo. No network, no LLM, no political findings."""
from copy import deepcopy
from backend.storage import now

URL = 'https://example.org/fictif/texte'
TEXT = "Consultation fictive sur l'accessibilité des transports. La consultation se termine le {} octobre 2026."


def snapshot(day='10', unavailable=False):
    return {'source_url': URL, 'retrieved_at': now(),
            'retrieval_status': 'unavailable' if unavailable else 'ok',
            'scope': 'full_document', 'text': '' if unavailable else TEXT.format(day)}


def analyze(envelope):
    request = envelope['request']
    previous, current = request.get('previous'), request['current']
    report = {'document_id': request['document_id'], 'change_type': 'unconfirmed',
              'description': 'Vérification non concluante (simulation).', 'changes': [],
              'evidence': [], 'limitations': ['Données fictives ; aucune recherche ni analyse IA exécutée.']}
    if current['retrieval_status'] != 'ok':
        report['limitations'].append('Récupération indisponible simulée ; dernière version conservée.')
        return report
    for version, state in [('previous', previous), ('current', current)]:
        if state:
            report['evidence'].append({'version': version, 'source_url': state['source_url'],
                                       'retrieved_at': state['retrieved_at'], 'quote': state['text']})
    if previous is None:
        report.update(change_type='new_document', description='Premier document fictif ajouté à cette veille.')
    elif previous['text'] == current['text']:
        report.update(change_type='unchanged', description='Le texte fictif est identique à la dernière version.')
    else:
        report.update(change_type='modified', description='La date de clôture du document fictif a changé.')
        report['changes'] = [{'description': report['description'], 'evidence': deepcopy(report['evidence'])}]
    return report
