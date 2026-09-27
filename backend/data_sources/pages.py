"""Bounded page collection adapted from the team's f5d79fc collector; no inference."""
from datetime import datetime, timezone
from time import monotonic
import httpx
from backend.source_verification import FetchedSource, allowed_url, fetch_text, normalize

MAX_SOURCES = 6
MAX_SOURCE_CHARS = 15_000
MAX_CORPUS_CHARS = 60_000

def collect_sources(urls: list[str], *, transport=None) -> tuple[list, dict, list]:
    """Only URLs guide collection; generated answers, titles and snippets are discarded."""
    corpus: list[dict] = []
    fetched: dict[str, FetchedSource] = {}
    limitations = []
    seen: set[str] = set()
    remaining = MAX_CORPUS_CHARS
    deadline = monotonic() + 30
    with httpx.Client(transport=transport, follow_redirects=False, trust_env=False,
                      headers={'User-Agent': 'ReperesCitoyens-Hackathon/0.1'}) as client:
        for url in urls[:MAX_SOURCES]:
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
