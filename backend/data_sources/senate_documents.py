"""Bounded traversal: dossier -> explicitly linked Senate legislative texts.

URLs are discovered in the retrieved HTML, never reconstructed from dossier IDs.
The HTML link establishes a link, not the legal identity of different versions.
"""
from datetime import datetime, timezone
import hashlib
import json
import re
from time import monotonic
from urllib.parse import urlsplit, urlunsplit

import httpx

from backend.source_verification import FetchedSource, allowed_url, fetch_text, normalize

MAX_DOSSIERS = 3
MAX_TEXTS_PER_DOSSIER = 2
MAX_CHARS = 60_000


def text_links(links: list[str]) -> list[str]:
    """Prefer HTML to an explicitly linked PDF of the same URL stem; keep versions."""
    documents: dict[str, str] = {}
    for url in links:
        if not allowed_url(url):
            continue
        parsed = urlsplit(url)
        if (parsed.hostname not in ('senat.fr', 'www.senat.fr') or parsed.query or
                not re.fullmatch(r'/leg/(?:ppl|pjl|tas|tasc|ta)[0-9][a-zA-Z0-9_-]*\.(?:html|pdf)', parsed.path)):
            continue
        clean = urlunsplit(('https', 'www.senat.fr', parsed.path, '', ''))
        stem = clean.rsplit('.', 1)[0]
        if stem not in documents or clean.endswith('.html'):
            documents[stem] = clean
    return list(documents.values())


def collect_dossiers(dossier_urls: list[str], *, transport=None) -> tuple[list, list, list]:
    """Return exact corpus, discovered links with outcomes, and explicit limits.

At most three dossiers and two texts each, 45s cooperative budget, 60k characters.
Repeated URLs reuse the same fetch. PDF page boundaries remain intact.
"""
    corpus: list[dict] = []
    inventory: list[dict] = []
    limits = ['Collecte limitée à trois dossiers et deux textes liés par dossier, dans l’ordre des liens ; '
              'les autres versions et les documents de l’Assemblée ne sont pas parcourus.',
              'Le lien HTML établit un rattachement au dossier, pas l’équivalence juridique de deux versions.']
    cache: dict[str, FetchedSource] = {}
    sent: dict[str, dict] = {}
    remaining = MAX_CHARS
    deadline = monotonic() + 45
    unique = list(dict.fromkeys(dossier_urls))
    if len(unique) > MAX_DOSSIERS:
        limits.append(f'{len(unique) - MAX_DOSSIERS} dossier(s) sélectionné(s) non parcouru(s) : limite de collecte.')

    def add_source(url, source, role, dossier_url, cap):
        nonlocal remaining
        if url in sent:
            if dossier_url not in sent[url]['dossier_urls']:
                sent[url]['dossier_urls'].append(dossier_url)
            return 'included'
        if source.status != 'retrieved':
            limits.append(f'Source non exploitable ({source.status}) : {url}')
            return source.status
        if remaining <= 0:
            limits.append(f'Source non transmise : limite de caractères atteinte ({url}).')
            return 'corpus_limit'
        # HTML indentation must not consume the corpus budget before actual content.
        # The verifier already permits only whitespace/NFC normalization.
        original = source.pages if source.pages is not None else [normalize(source.text)]
        budget = min(cap, remaining)
        pages = []
        for page in original:
            pages.append(page[:budget])
            budget -= len(pages[-1])
            if budget <= 0:
                break
        size = sum(len(p) for p in pages)
        remaining -= size
        content = {'text': pages[0] if source.pages is None else '',
                   'pdf_pages': pages if source.pages is not None else None}
        truncated = size < sum(len(p) for p in original)
        if truncated:
            limits.append(f'Texte tronqué avant analyse : {url}')
        item = {'url': url, 'final_url': source.final_url, 'source_role': role,
                'dossier_urls': [dossier_url], 'retrieved_at': cache_times[url],
                'text_normalization': 'none' if source.pages is not None else 'NFC + whitespace',
                'truncated': truncated, **content,
                'content_sha256': hashlib.sha256(json.dumps(content, ensure_ascii=False,
                                                           sort_keys=True).encode('utf-8')).hexdigest()}
        corpus.append(item)
        sent[url] = item
        return 'included'

    cache_times: dict[str, str] = {}
    with httpx.Client(transport=transport, follow_redirects=False, trust_env=False,
                      headers={'User-Agent': 'SedLex-Hackathon/0.1'}) as client:
        def get(url):
            if url not in cache:
                cache[url] = fetch_text(client, url, deadline)
                cache_times[url] = datetime.now(timezone.utc).isoformat()
            return cache[url]

        for dossier in unique[:MAX_DOSSIERS]:
            parsed = urlsplit(dossier)
            if (not allowed_url(dossier) or parsed.hostname not in ('www.senat.fr', 'senat.fr')
                    or not parsed.path.startswith('/dossier-legislatif/')):
                limits.append('URL de dossier refusée avant tout téléchargement.')
                continue
            if remaining <= 0 or monotonic() >= deadline:
                limits.append('Fin de collecte : budget de temps ou de caractères atteint.')
                break
            source = get(dossier)
            add_source(dossier, source, 'dossier', dossier, 4_000)
            links = text_links(source.links or [])
            if not links:
                limits.append(f'Aucun lien de texte parlementaire reconnu dans la page récupérée : {dossier}')
            for index, url in enumerate(links):
                status = 'not_attempted'
                if index < MAX_TEXTS_PER_DOSSIER and remaining > 0 and monotonic() < deadline:
                    status = add_source(url, get(url), 'legislative_text', dossier, 12_000)
                inventory.append({'dossier_url': dossier, 'url': url, 'status': status,
                                  'relation': 'hyperlink_in_retrieved_dossier'})
    limits.append(f'{len(corpus)} source(s) transmise(s), {MAX_CHARS - remaining} caractères ; '
                  'aucune recherche exhaustive, aucun OCR, aucune conclusion sur la vigueur actuelle.')
    return corpus, inventory, limits
