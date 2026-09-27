"""Bounded public-page verification. A matching excerpt is not proof of interpretation."""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
import sys
from time import monotonic
import unicodedata
from urllib.parse import urljoin, urlsplit

import httpx
from src.contracts import validate_report

HOSTS = frozenset({'assemblee-nationale.fr', 'www.assemblee-nationale.fr',
                   'senat.fr', 'www.senat.fr', 'legifrance.gouv.fr', 'www.legifrance.gouv.fr'})
MAX_BYTES = 2_000_000
MAX_PAGES = 8


@dataclass(frozen=True)
class FetchedSource:
    status: str
    text: str
    final_url: str
    pages: list | None = None
    links: list[str] | None = None


def read_pdf(body, deadline):
    remaining = deadline - monotonic()
    if remaining <= 0:
        return {'status': 'budget_exceeded', 'pages': []}
    try:
        process = subprocess.run(
            [sys.executable, str(Path(__file__).with_name('pdf_text_worker.py'))],
            input=body, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=min(8, remaining), check=True,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
        return json.loads(process.stdout)
    except subprocess.TimeoutExpired:
        return {'status': 'pdf_timeout', 'pages': []}
    except (OSError, subprocess.CalledProcessError, ValueError):
        return {'status': 'pdf_extraction_error', 'pages': []}


def allowed_url(url):
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == 'https' and parsed.hostname in HOSTS
                and parsed.port in (None, 443) and parsed.username is None
                and parsed.password is None and '\\' not in url
                and not any(c.isspace() or ord(c) < 32 for c in url))
    except ValueError:
        return False


class PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts = []
        self.main_parts = []
        self.links = []
        self.main_links = []
        self.main_depth = 0
        self.has_main = False

    def append_text(self, value):
        self.parts.append(value)
        if self.main_depth:
            self.main_parts.append(value)

    def handle_starttag(self, tag, attrs):
        if tag == 'main':
            self.has_main = True
            self.main_depth += 1
        if tag in ('script', 'style', 'head', 'noscript', 'template'):
            self.hidden += 1
        if not self.hidden and tag in ('p', 'div', 'br', 'li', 'td', 'tr', 'h1', 'h2', 'h3', 'section', 'article'):
            self.append_text(' ')
        if not self.hidden and tag == 'a':
            href = dict(attrs).get('href')
            if href:
                if len(self.links) < 256:
                    self.links.append(href)
                if self.main_depth and len(self.main_links) < 256:
                    self.main_links.append(href)

    def handle_endtag(self, tag):
        if tag == 'main':
            self.main_depth = max(0, self.main_depth - 1)
        if tag in ('script', 'style', 'head', 'noscript', 'template'):
            self.hidden = max(0, self.hidden - 1)
        if not self.hidden and tag in ('p', 'div', 'li', 'td', 'tr', 'h1', 'h2', 'h3', 'section', 'article'):
            self.append_text(' ')

    def handle_data(self, data):
        if not self.hidden:
            self.append_text(data)


def normalize(text):
    # Only Unicode composition and whitespace; do not change words, numbers or punctuation.
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFC', text)).strip()


def fetch_text(client, url, deadline):
    current = url
    for _ in range(4):
        if not allowed_url(current):
            return FetchedSource('domain_not_allowed', '', current)
        remaining = deadline - monotonic()
        if remaining <= 0:
            return FetchedSource('budget_exceeded', '', current)
        try:
            with client.stream('GET', current, timeout=min(8, remaining)) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    current = urljoin(current, response.headers.get('location', ''))
                    continue
                if response.status_code != 200:
                    return FetchedSource('http_error', '', current)
                media = response.headers.get('content-type', '').split(';')[0].strip().lower()
                if media not in ('text/html', 'application/xhtml+xml', 'text/plain', 'application/pdf'):
                    return FetchedSource('unsupported_format', '', current)
                body = bytearray()
                for chunk in response.iter_bytes():
                    if monotonic() > deadline:
                        return FetchedSource('budget_exceeded', '', current)
                    body.extend(chunk)
                    if len(body) > MAX_BYTES:
                        return FetchedSource('too_large', '', current)
                if media == 'application/pdf':
                    pdf = read_pdf(bytes(body), deadline)
                    return FetchedSource(pdf['status'], '', current, pdf['pages'])
                decoded = bytes(body).decode(response.encoding or 'utf-8', errors='replace')
                links = []
                if media != 'text/plain':
                    parser = PageText()
                    parser.feed(decoded)
                    decoded = ''.join(parser.main_parts if parser.has_main else parser.parts)
                    hrefs = parser.main_links if parser.has_main else parser.links
                    links = list(dict.fromkeys(urljoin(current, href) for href in hrefs
                                               if allowed_url(urljoin(current, href))))
                if not normalize(decoded):
                    return FetchedSource('empty_page', '', current)
                return FetchedSource('retrieved', decoded, current, links=links)
        except (httpx.HTTPError, UnicodeError, LookupError):
            return FetchedSource('unavailable', '', current)
    return FetchedSource('redirect_limit', '', current)


@dataclass(frozen=True)
class SourceVerification:
    report: dict
    checks: list

    @property
    def all_matched(self):
        return bool(self.checks) and all(c['status'] in ('matched', 'matched_whitespace') for c in self.checks)


def verify_sources(report, *, transport=None, fetched_sources=None):
    """With a supplied corpus, verify it exclusively without fetching new URLs."""
    validate_report(report)
    result = deepcopy(report)
    checks = []
    cache: dict[str, FetchedSource] = dict(fetched_sources or {})
    deadline = monotonic() + 30
    with httpx.Client(transport=transport, follow_redirects=False, trust_env=False,
                      headers={'User-Agent': 'SedLex-Hackathon/0.1'}) as client:
        for kind, entities in [('document', result['documents']), ('contact', result['contacts'])]:
            for index, entity in enumerate(entities):
                for evidence_index, evidence in enumerate(entity['evidence'], 1):
                    url = evidence['url']
                    if url not in cache:
                        cache[url] = (FetchedSource('not_in_corpus', '', url) if fetched_sources is not None
                                      else FetchedSource('budget_exceeded', '', url) if len(cache) >= MAX_PAGES
                                      else fetch_text(client, url, deadline))
                    source = cache[url]
                    status, final_url = source.status, source.final_url
                    matched_page = None
                    if status == 'retrieved':
                        excerpt = evidence['excerpt']
                        status = 'not_found'
                        for page_number, page in enumerate(source.pages if source.pages is not None else [source.text], 1):
                            if excerpt in page or normalize(excerpt) in normalize(page):
                                status = 'matched' if excerpt in page else 'matched_whitespace'
                                matched_page = page_number if source.pages is not None else None
                                break
                    check = {'entity_type': kind, 'entity_index': index, 'evidence_index': evidence_index,
                             'url': url, 'final_url': final_url, 'status': status,
                             'pdf_page': matched_page,
                             'checked_at': datetime.now(timezone.utc).isoformat()}
                    checks.append(check)
                    if status not in ('matched', 'matched_whitespace'):
                        message = (f'Source non confirmée : {kind} {index + 1}, extrait {evidence_index} '
                                   f'({evidence["purpose"]}, {status}). La présence du passage n’a pas été confirmée.')
                        result['limitations'].append(message)
                        if kind == 'document':
                            entity['uncertainties'].append(message)
    count = sum(c['status'] in ('matched', 'matched_whitespace') for c in checks)
    result['limitations'].append(
        f'Contrôle des sources : {count}/{len(checks)} extraits retrouvés dans les pages récupérées. '
        'Seuls les espaces et la composition Unicode peuvent être normalisés. '
        'Ce contrôle ne certifie ni le sens de la citation, ni la date, ni l’actualité du statut. '
        'PDF : contrôle de la couche texte uniquement, sans OCR ni validation visuelle ; '
        'les extraits traversant plusieurs pages ne sont pas rapprochés. '
        'Pages nécessitant JavaScript non prises en charge.')
    return SourceVerification(result, checks)
