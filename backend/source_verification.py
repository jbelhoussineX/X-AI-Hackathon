"""Bounded public-page verification. A matching excerpt is not proof of interpretation."""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import re
from time import monotonic
import unicodedata
from urllib.parse import urljoin, urlsplit

import httpx
from backend.dust.adapter import validate_dust_report

HOSTS = frozenset({'assemblee-nationale.fr', 'www.assemblee-nationale.fr',
                   'senat.fr', 'www.senat.fr', 'legifrance.gouv.fr', 'www.legifrance.gouv.fr'})
MAX_BYTES = 2_000_000
MAX_PAGES = 8


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

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'head', 'noscript', 'template'):
            self.hidden += 1
        if not self.hidden and tag in ('p', 'div', 'br', 'li', 'td', 'tr', 'h1', 'h2', 'h3', 'section', 'article'):
            self.parts.append(' ')

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'head', 'noscript', 'template'):
            self.hidden = max(0, self.hidden - 1)
        if not self.hidden and tag in ('p', 'div', 'li', 'td', 'tr', 'h1', 'h2', 'h3', 'section', 'article'):
            self.parts.append(' ')

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def normalize(text):
    # Only Unicode composition and whitespace; do not change words, numbers or punctuation.
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFC', text)).strip()


def fetch_text(client, url, deadline):
    current = url
    for _ in range(4):
        if not allowed_url(current):
            return 'domain_not_allowed', '', current
        remaining = deadline - monotonic()
        if remaining <= 0:
            return 'budget_exceeded', '', current
        try:
            with client.stream('GET', current, timeout=min(8, remaining)) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    current = urljoin(current, response.headers.get('location', ''))
                    continue
                if response.status_code != 200:
                    return 'http_error', '', current
                media = response.headers.get('content-type', '').split(';')[0].strip().lower()
                if media not in ('text/html', 'application/xhtml+xml', 'text/plain'):
                    return 'unsupported_format', '', current
                body = bytearray()
                for chunk in response.iter_bytes():
                    if monotonic() > deadline:
                        return 'budget_exceeded', '', current
                    body.extend(chunk)
                    if len(body) > MAX_BYTES:
                        return 'too_large', '', current
                decoded = bytes(body).decode(response.encoding or 'utf-8', errors='replace')
                if media != 'text/plain':
                    parser = PageText()
                    parser.feed(decoded)
                    decoded = ''.join(parser.parts)
                if not normalize(decoded):
                    return 'empty_page', '', current
                return 'retrieved', decoded, current
        except (httpx.HTTPError, UnicodeError, LookupError):
            return 'unavailable', '', current
    return 'redirect_limit', '', current


@dataclass(frozen=True)
class SourceVerification:
    report: dict
    checks: list

    @property
    def all_matched(self):
        return bool(self.checks) and all(c['status'] in ('matched', 'matched_whitespace') for c in self.checks)


def verify_sources(report, *, transport=None):
    validate_dust_report(report)
    result = deepcopy(report)
    checks = []
    cache = {}
    deadline = monotonic() + 30
    with httpx.Client(transport=transport, follow_redirects=False, trust_env=False,
                      headers={'User-Agent': 'ReperesCitoyens-Hackathon/0.1'}) as client:
        for kind, entities in [('document', result['documents']), ('contact', result['contacts'])]:
            for index, entity in enumerate(entities):
                for evidence_index, evidence in enumerate(entity['evidence'], 1):
                    url = evidence['url']
                    if url not in cache:
                        cache[url] = (('budget_exceeded', '', url) if len(cache) >= MAX_PAGES
                                      else fetch_text(client, url, deadline))
                    status, page, final_url = cache[url]
                    if status == 'retrieved':
                        excerpt = evidence['excerpt']
                        status = ('matched' if excerpt in page else
                                  'matched_whitespace' if normalize(excerpt) in normalize(page) else 'not_found')
                    check = {'entity_type': kind, 'entity_index': index, 'evidence_index': evidence_index,
                             'url': url, 'final_url': final_url, 'status': status,
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
        'PDF et pages nécessitant JavaScript non pris en charge.')
    return SourceVerification(result, checks)
