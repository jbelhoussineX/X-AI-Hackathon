"""Synthesis boundary: model explains evidence; Python preserves source metadata."""
from copy import deepcopy
import json

from backend.comparison_validation import ContractError, _fields, _require, _text
from backend.dust.adapter import validate_dust_report


def prepare_summary(topic: str, report: dict) -> dict:
    _text(topic)
    validate_dust_report(report)
    _require(len(report['documents']) <= 4, 'Au plus quatre documents par synthèse.')
    documents = []
    for doc in report['documents']:
        documents.append({
            'document_id': doc['id'], 'title': doc['title'], 'kind': doc['kind'],
            'publication_date': doc['publication_date'], 'stage': doc['stage'],
            'stage_date': doc['stage_date'], 'uncertainties': deepcopy(doc['uncertainties']),
            'evidence': [dict(deepcopy(e), evidence_id=f'e{index}')
                         for index, e in enumerate(doc['evidence'], 1)],
        })
    corpus = {'documents': documents, 'scope': report['scope'], 'limitations': report['limitations']}
    return {'topic': topic, 'corpus_json': json.dumps(corpus, ensure_ascii=False)}


def validate_summary(report: dict, output: dict) -> dict:
    validate_dust_report(report)
    _fields(output, ('documents',))
    _require(isinstance(output['documents'], list), 'Liste de synthèses attendue.')
    source = {d['id']: d for d in report['documents']}
    seen = set()
    for item in output['documents']:
        _fields(item, ('document_id', 'explanation', 'relevance', 'limitations'))
        ident = item['document_id']
        _text(ident)
        _require(ident in source and ident not in seen, 'Document inventé ou dupliqué.')
        seen.add(ident)
        content_refs = {f'e{i}' for i, e in enumerate(source[ident]['evidence'], 1) if e['purpose'] == 'contenu'}
        for key in ('explanation', 'relevance'):
            claim = item[key]
            _fields(claim, ('text', 'evidence_ids'))
            _text(claim['text'])
            _require(len(claim['text']) <= 4000, 'Explication trop longue.')
            refs = claim['evidence_ids']
            _require(isinstance(refs, list) and bool(refs), 'Références de contenu requises.')
            for ref in refs:
                _text(ref)
            _require(len(refs) == len(set(refs)) and set(refs) <= content_refs,
                     'Référence inconnue, dupliquée ou sans preuve de contenu.')
        _require(isinstance(item['limitations'], list), 'Liste de limites attendue.')
        for limitation in item['limitations']:
            _text(limitation)
    _require(seen == set(source), 'Chaque document doit être expliqué, sans omission.')
    return output


def synthesize_report(topic: str, report: dict, analyze) -> dict:
    """Return the same citoyen_report contract, with sourced explanations in summary.

    Structural provenance is checked, not semantic truth. The injected analyzer
    takes {request: SummaryRequest} and returns a bare InterestSummary.
    """
    original = deepcopy(report)
    request = prepare_summary(topic, original)
    if not original['documents']:
        return original  # No inference for an empty corpus.
    output = analyze({'request': deepcopy(request)})
    validate_summary(original, output)
    by_id = {item['document_id']: item for item in output['documents']}
    for doc in original['documents']:
        item = by_id[doc['id']]
        parts = []
        for key, label in [('explanation', ''), ('relevance', 'Lien avec le sujet : ')]:
            refs = ', '.join(ref[1:] for ref in item[key]['evidence_ids'])
            parts.append(label + item[key]['text'] + f' (Extraits {refs}.)')
        doc['summary'] = '\n\n'.join(parts)
        doc['uncertainties'].extend(item['limitations'])
    original['limitations'].append(
        'Synthèse reformulée par Pipelex à partir des extraits transmis par Dust ; '
        'le modèle ne fait aucune recherche ni vérification supplémentaire des pages. '
        'Les références contrôlées ne garantissent pas la justesse de l’interprétation.')
    validate_dust_report(original)
    return original
