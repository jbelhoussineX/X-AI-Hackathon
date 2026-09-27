"""Build a bounded recent corpus and reject ungrounded citations before display."""
import asyncio
import hashlib
import json
import os
from datetime import datetime, timezone

from backend.clients import require_enabled
from backend.data_sources.pages import collect_sources
from backend.data_sources.debates import passages
from backend.source_verification import normalize, allowed_url
from backend.generated.recent_brief.models import Request, Brief
from backend.pipelex_recent import summarize
from pydantic import ValidationError


class BriefError(ValueError):
    """Safe, actionable message; never contains provider output or credentials."""


def check_freshness(result):
    try:
        collected = datetime.fromisoformat(result["collected_at"])
        if collected.tzinfo is None:
            raise ValueError
        age = (datetime.now(timezone.utc) - collected).total_seconds()
    except (ValueError, TypeError, KeyError):
        raise BriefError("Date de collecte invalide. Clique sur Consulter les actualités officielles. Aucun appel IA lancé.") from None
    if age > 3600:
        raise BriefError("Collecte de plus d’une heure. Clique sur Consulter les actualités officielles pour l’actualiser. Aucun appel IA lancé.")
    if age < -300:
        raise BriefError("Date de collecte dans le futur. Vérifie l’horloge puis actualise la collecte. Aucun appel IA lancé.")



def quote_options(text):
    """Deterministic, contiguous excerpts; the model selects identifiers only."""
    quotes: list[dict[str, str]] = []
    start = 0
    while start < len(text):
        end = min(start + 500, len(text))
        if end < len(text):
            boundary = text.rfind(' ', start + 25, end)
            if boundary > start:
                end = boundary
        excerpt = text[start:end].strip()
        if len(excerpt) >= 25:
            quotes.append({'quote_id': f'q{len(quotes)}', 'excerpt': excerpt})
        start = end
        while start < len(text) and text[start].isspace():
            start += 1
    return quotes


def prepare(result, *, transport=None):
    sources, limits = [], list(result['limitations'])
    selected = result['events'][:6]
    urls = list(dict.fromkeys(e['dossier_url'] for e in selected if not e.get('content_passages')))
    pages, _, issues = collect_sources(urls, transport=transport) if urls else ([], {}, [])
    limits.extend(issues)
    by_url = {p['url']: p for p in pages}
    for index, event in enumerate(selected):
        if not result['start'] <= event['event_date'] <= result['end'] or not allowed_url(event['dossier_url']):
            raise BriefError('Événement hors période ou source non autorisée. Actualise la collecte. Aucun appel IA lancé.')
        chunks = event.get('content_passages', [])
        page = by_url.get(event['dossier_url'])
        if page:
            chunks = [chunk for text in (page['pdf_pages'] or [page['text']])
                      for chunk in passages(text, result['topic'], limit=1)][:3]
        for part, text in enumerate(chunks[:3]):
            text = normalize(text)[:4000]
            if len(text) < 25:
                continue
            sources.append({'source_id': f'e{index}p{part}', 'event_id': event['id'],
                            'title': event['title'], 'category': event['category'],
                            'event_label': event.get('event'), 'recorded_decision': event.get('decision'),
                            'event_date': event['event_date'], 'publication_date': event.get('publication_date'),
                            'date_kind': event['date_kind'], 'url': event['dossier_url'],
                            'retrieved_at': page['retrieved_at'] if page else event['retrieved_at'],
                            'text': text, 'quotes': quote_options(text), 'sha256': hashlib.sha256(text.encode()).hexdigest()})
        if not chunks:
            limits.append('Aucun passage pertinent exploitable pour la synthèse : ' + event['title'])
    limits.append('Synthèse limitée aux six premiers événements affichés et à des passages partiels. '
                  'Présence des citations contrôlée ; interprétation à relire. '
                  'Une page relue peut avoir changé depuis la publication du signal.')
    return {'topic': result['topic'], 'start': result['start'], 'end': result['end'],
            'sources': sources, 'limitations': limits}


def verify(brief: Brief, corpus):
    if len(brief.items) > 6 or len(brief.limitations) > 12:
        raise BriefError('Réponse IA au-delà des limites de taille : synthèse refusée. Des crédits peuvent avoir été consommés ; aucune relance automatique.')
    sources = {s['source_id']: s for s in corpus['sources']}
    seen, items = set(), []
    duplicates = 0
    for item in brief.items:
        source = sources.get(item.source_id)
        quote = next((q for q in source.get('quotes', []) if q['quote_id'] == item.quote_id), None) if source else None
        reason = None
        if source is None:
            reason = 'La réponse IA cite une référence absente du corpus transmis.'
        elif not item.summary.strip() or len(item.summary) > 2000:
            reason = 'Le résumé IA est vide ou trop long.'
        elif quote is None:
            reason = 'La réponse IA choisit un identifiant de citation absent du passage.'
        elif quote['excerpt'] not in source['text']:
            reason = 'Le corpus de citations est incohérent.'
        if reason:
            raise BriefError(reason + ' Synthèse refusée. Des crédits peuvent avoir été consommés ; aucune relance automatique.')
        assert source is not None  # Unknown references were rejected above.
        assert quote is not None
        if source['event_id'] in seen:
            duplicates += 1
            continue
        seen.add(source['event_id'])
        items.append({**source, 'summary': item.summary, 'excerpt': quote['excerpt'], 'quote_id': item.quote_id})
    notes = ([f'{duplicates} répétition(s) du même événement écartée(s) ; première synthèse vérifiée conservée.']
             if duplicates else [])
    return {'topic': corpus['topic'], 'start': corpus['start'], 'end': corpus['end'],
            'generated_at': datetime.now(timezone.utc).isoformat(), 'items': items, 'duplicate_count': duplicates,
            'limitations': [*corpus['limitations'], *brief.limitations, *notes]}


def build(result, *, transport=None):
    require_enabled('PIPELEX')
    engine = os.environ.get('PIPELEX_EXECUTION_MODE', 'hosted')
    if engine not in ('hosted', 'local'):
        raise BriefError('Configuration invalide : PIPELEX_EXECUTION_MODE doit valoir hosted ou local. Aucun appel IA lancé.')
    check_freshness(result)
    corpus = prepare(result, transport=transport)
    if not corpus['sources']:
        return verify(Brief(items=[], limitations=['Aucun passage exploitable : aucun appel IA.']), corpus)
    request = Request(topic=result['topic'], corpus_json=json.dumps(corpus, ensure_ascii=False))
    try:
        if engine == 'hosted':
            output = asyncio.run(summarize(request))
        else:
            from src.recent_worker import run_local
            output = run_local(request)
    except ValidationError:
        raise BriefError('Le fournisseur a retourné un format de synthèse invalide. Des crédits peuvent avoir été consommés ; aucune relance automatique.') from None
    return verify(output, corpus)
