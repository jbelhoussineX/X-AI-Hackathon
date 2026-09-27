"""Bounded page collection adapted from the team's f5d79fc collector; no inference."""
from datetime import datetime, timezone
from time import monotonic
import re
from urllib.parse import urlsplit
import httpx
from backend.source_verification import FetchedSource, allowed_url, fetch_text, normalize
from backend.data_sources.senate_documents import text_links

MAX_SOURCES = 6
MAX_SOURCE_CHARS = 15_000
MAX_CORPUS_CHARS = 60_000

def linked_legislative_text(links):
    """One observed text link, never a URL reconstructed from an identifier."""
    senate = text_links(links)
    for url in links:
        parsed = urlsplit(url)
        if (allowed_url(url) and parsed.hostname in ('www.assemblee-nationale.fr', 'assemblee-nationale.fr')
                and not parsed.query and re.fullmatch(
                    r'/(?:dyn/opendata/(?:PION|PRJL)ANR[\w-]+\.html|dyn/\d+/textes/[\w-]+|\d+/(?:propositions|projets)/[\w-]+\.(?:asp|html|pdf))', parsed.path)):
            return url
    return senate[0] if senate else None


def collect_sources(urls: list[str], *, transport=None, follow_legislative=False) -> tuple[list, dict, list]:
    """Only URLs guide collection; generated answers, titles and snippets are discarded."""
    corpus: list[dict] = []
    fetched: dict[str, FetchedSource] = {}
    limitations = []
    seen: set[str] = set()
    remaining = MAX_CORPUS_CHARS
    deadline = monotonic() + 30
    queue = [(url, None) for url in list(dict.fromkeys(urls))[:MAX_SOURCES]]
    with httpx.Client(transport=transport, follow_redirects=False, trust_env=False,
                      headers={'User-Agent': 'SedLex-Hackathon/0.1'}) as client:
        while queue:
            url, parent = queue.pop(0)
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
            if parent:
                corpus[-1]['dossier_url'] = parent
            elif follow_legislative and ('/dossiers/' in urlsplit(url).path or '/dossier-legislatif/' in urlsplit(url).path):
                linked = linked_legislative_text(source.links or [])
                if linked and linked not in seen:
                    queue.insert(0, (linked, url))
    limitations.append(f'Corpus collecté : {len(corpus)} page(s), au plus {MAX_SOURCES} résultats de recherche, '
                       'Assemblée nationale, Sénat et Légifrance uniquement. Recherche non exhaustive.')
    if follow_legislative:
        limitations.append('Un texte lié au maximum par dossier, sans parcours récursif ; '
                           'budget global inchangé de 30 secondes et 60 000 caractères. '
                           'Le rattachement par lien ne prouve pas que cette version est la plus récente.')
    return corpus, fetched, limitations
