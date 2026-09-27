"""Search, bounded official-source retrieval, then a source-grounded Pipelex report."""
import asyncio
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
import os
from time import monotonic

import httpx

from backend.clients import require_enabled
from backend.generated.political_search.models import SearchRequest, SearchResult
from backend.generated.political_report.models import ReportRequest
from backend.pipelex_search import find_sources
from backend.pipelex_report import build_report
from backend.report_contract import validate_report
from backend.source_verification import FetchedSource, allowed_url, fetch_text, verify_sources, normalize

MAX_SOURCES = 6
MAX_SOURCE_CHARS = 15_000
MAX_CORPUS_CHARS = 60_000


@dataclass(frozen=True)
class ResearchResult:
    report: dict
    checks: list
    # Keep provider metadata available without exposing it in the frontend.
    runs: tuple = ()


def collect_sources(search: SearchResult, *, transport=None) -> tuple[list, dict, list]:
    """Only URLs guide collection; generated answers, titles and snippets are discarded."""
    corpus: list[dict] = []
    fetched: dict[str, FetchedSource] = {}
    limitations = []
    seen: set[str] = set()
    remaining = MAX_CORPUS_CHARS
    deadline = monotonic() + 30
    with httpx.Client(transport=transport, follow_redirects=False, trust_env=False,
                      headers={'User-Agent': 'ReperesCitoyens-Hackathon/0.1'}) as client:
        for candidate in search.sources[:MAX_SOURCES]:
            url = candidate.url
            if url in seen:
                continue
            seen.add(url)
            if not allowed_url(url):
                limitations.append('Une URL de recherche écartée : domaine ou protocole non autorisé.')
                continue
            if remaining <= 0:
                limitations.append('Limite globale du corpus atteinte : certaines sources non lues.')
                break
            source = fetch_text(client, url, deadline)
            if source.status != 'retrieved':
                limitations.append(f'Page non exploitable ({source.status}) : {url}')
                continue
            budget = min(MAX_SOURCE_CHARS, remaining)
            original = source.pages if source.pages is not None else [normalize(source.text)]
            pages = []
            for page in original:
                pages.append(page[:budget])
                budget -= len(pages[-1])
                if budget <= 0:
                    break
            used = sum(len(page) for page in pages)
            remaining -= used
            truncated = used < sum(len(page) for page in original)
            if truncated:
                limitations.append(f'Texte tronqué avant analyse : {url}')
            limited = FetchedSource('retrieved', pages[0] if source.pages is None else '',
                                    source.final_url, pages if source.pages is not None else None)
            fetched[url] = limited
            fetched.setdefault(source.final_url, limited)
            corpus.append({'url': url, 'final_url': source.final_url,
                           'retrieved_at': datetime.now(timezone.utc).isoformat(),
                           'text': limited.text, 'pdf_pages': limited.pages, 'truncated': truncated})
    limitations.append(f'Corpus collecté : {len(corpus)} page(s), au plus {MAX_SOURCES} résultats de recherche, '
                       'Assemblée nationale, Sénat et Légifrance uniquement. Recherche non exhaustive.')
    return corpus, fetched, limitations


def research(topic: str, *, start: str, end: str, transport=None) -> ResearchResult:
    if not isinstance(topic, str) or not 3 <= len(topic.strip()) <= 300:
        raise ValueError('Sujet requis de 3 à 300 caractères.')
    if (date.fromisoformat(start).isoformat() != start or
            date.fromisoformat(end).isoformat() != end or start > end):
        raise ValueError('Période de publication invalide.')
    require_enabled('PIPELEX')
    topic = topic.strip()
    runs: tuple = ()
    source_mode = os.environ.get('POLITICAL_DATA_SOURCE', 'official')
    if source_mode == 'official':
        from backend.data_sources.official import prepare, fetched_corpus
        prepared = prepare(topic, start, end, transport=transport)
        corpus, limitations = prepared['corpus'], prepared['limitations']
        fetched = fetched_corpus(corpus)
    elif source_mode == 'web':
        search_run = asyncio.run(find_sources(SearchRequest(topic=topic, start=start, end=end)))
        corpus, fetched, limitations = collect_sources(search_run.output, transport=transport)
        runs = (search_run.results,)
    else:
        raise ValueError('POLITICAL_DATA_SOURCE doit valoir official ou web.')
    report: dict
    if not corpus:
        report = {'schema_version': '1.0', 'topic': topic, 'scope': 'Aucune page officielle exploitable.',
                  'documents': [], 'contacts': [],
                  'limitations': [*limitations, 'Aucune conclusion documentaire possible ; aucun rapport généré.']}
        return ResearchResult(report, [], runs)
    report_run = asyncio.run(build_report(ReportRequest(
        topic=topic, start=start, end=end, corpus_json=json.dumps(corpus, ensure_ascii=False))))
    # Check raw output before generated models can discard unexpected fields.
    report = deepcopy(report_run.results.main_stuff)
    validate_report(report)
    if report['topic'] != topic or len(report['documents']) > 4 or len(report['contacts']) > 3:
        raise ValueError('Rapport hors du périmètre demandé.')
    for doc in report['documents']:
        if doc['kind'] not in ('projet_de_loi', 'proposition_de_loi'):
            raise ValueError('Cette version traite uniquement les projets et propositions de loi.')
        if doc['stage'] is not None and not any(e['purpose'] == 'statut' for e in doc['evidence']):
            raise ValueError('Étape de procédure sans preuve de statut.')
        if doc['stage_date'] is not None and doc['stage'] is None:
            raise ValueError('Date de procédure sans étape.')
    report['limitations'].extend(limitations)
    verification = verify_sources(report, fetched_sources=fetched)
    if verification.checks and not verification.all_matched:
        raise ValueError('Rapport refusé : une citation est absente du corpus effectivement lu.')
    return ResearchResult(verification.report, verification.checks, (*runs, report_run.results))
