"""Select citations by ID; only locally collected text can enter report evidence."""
from copy import deepcopy

from backend.source_verification import normalize


def passages_from_corpus(corpus: list[dict]) -> dict[str, dict]:
    """Partition each page without crossing PDF boundaries or adding/removing words.

    Whitespace and Unicode composition follow the final verifier's existing rules.
    A passage is at most 600 characters; nothing from an omitted page is indexed.
    """
    passages = {}
    for source in corpus:
        pages = source['pdf_pages'] if source['pdf_pages'] is not None else [source['text']]
        for page_number, page in enumerate(pages, 1):
            text = normalize(page)
            while text:
                cut = min(len(text), 600)
                if cut < len(text):
                    boundary = text.rfind(' ', 0, cut + 1)
                    if boundary > 0:
                        cut = boundary
                excerpt, text = text[:cut], text[cut:].lstrip()
                passage_id = f'p{len(passages) + 1:04d}'
                passages[passage_id] = {
                    'url': source['url'], 'excerpt': excerpt,
                    'location': f'Page {page_number} (couche texte PDF)' if source['pdf_pages'] is not None else None,
                }
    return passages


def selection_schema(report_schema: dict, passages: dict) -> dict:
    """Internal model output only: the shared report contract stays unchanged."""
    if not passages:
        raise ValueError('Aucun passage disponible.')
    schema = deepcopy(report_schema)
    schema.setdefault('$defs', {})['passage_id'] = {'type': 'string', 'enum': list(passages)}
    for group in ('documents', 'contacts'):
        evidence = schema['properties'][group]['items']['properties']['evidence']
        purpose = evidence['items']['properties']['purpose']
        evidence['items'] = {
            'type': 'object', 'additionalProperties': False,
            'properties': {'purpose': purpose, 'passage_id': {'$ref': '#/$defs/passage_id'}},
            'required': ['purpose', 'passage_id'],
        }
    return schema


def resolve_passages(draft: dict, passages: dict) -> dict:
    """Call only after validating the internal schema. Never trust model quote text."""
    report = deepcopy(draft)
    for group in ('documents', 'contacts'):
        for item in report[group]:
            item['evidence'] = [dict(passages[proof['passage_id']], purpose=proof['purpose'])
                                for proof in item['evidence']]
    return report
