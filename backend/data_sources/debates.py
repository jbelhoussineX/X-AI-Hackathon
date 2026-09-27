"""Recent official debate pages, fetched on demand with bounded coverage."""
from datetime import date
from html.parser import HTMLParser
import re
from time import monotonic
from urllib.parse import urljoin, urlsplit

import httpx

from backend.data_sources.live_feeds import fetch, official_link
from backend.data_sources.senate import _terms
from backend.source_verification import PageText, normalize

INDEXES = {
    'assemblee-debats': 'https://www.assemblee-nationale.fr/dyn/17/comptes-rendus/seance',
    'senat-debats': 'https://www.senat.fr/seances/comptes-rendus.html',
}
MONTHS = 'janvier février mars avril mai juin juillet août septembre octobre novembre décembre'.split()


class Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            href = dict(attrs).get('href')
            if href and len(self.links) < 10000:
                self.links.append(href)


def dated_links(body, base):
    parser = Links()
    parser.feed(body.decode('utf-8'))
    found = {}
    for href in parser.links:
        try:
            url = official_link(urljoin(base, href).split('#')[0], urlsplit(base).hostname)
            path = urlsplit(url).path
            if 'assemblee-nationale' in base:
                if not path.startswith('/dyn/17/comptes-rendus/seance/'):
                    continue
                match = re.search(r'-(\d{1,2})-([a-zéûô]+)-(\d{4})$', path)
                if not match or match[2] not in MONTHS:
                    continue
                day = date(int(match[3]), MONTHS.index(match[2]) + 1, int(match[1]))
            else:
                match = re.fullmatch(r'/cra/s(\d{8})/s\1_som.html', path)
                if not match:
                    continue
                day = date(int(match[1][:4]), int(match[1][4:6]), int(match[1][6:]))
            found[url] = day.isoformat()
        except (ValueError, UnicodeError):
            continue
    return sorted(found.items(), key=lambda item: (item[1], item[0]), reverse=True)


def passages(text, topic, limit=3):
    """Keep separate contiguous windows; never join them into a fake quotation."""
    text = normalize(text)
    terms = _terms(topic)
    result = []
    for start in range(0, len(text), 1600):
        chunk = text[max(0, start - 600):start + 2400]
        if terms and terms <= _terms(chunk):
            result.append(chunk)
            if len(result) == limit:
                break
    return result


def collect(topic, start, end, *, transport=None):
    events, datasets = [], []
    limits = ['Débats : première page des index officiels, six séances au plus par chambre ; '
              'comptes rendus analytiques au Sénat. Couverture partielle, hors commissions.',
              'Date de séance distincte de la publication (non confirmée). Passages sélectionnés '
              'par mots-clés ; un compte rendu peut être corrigé après publication.']
    with httpx.Client(transport=transport, trust_env=False, follow_redirects=False) as client:
        for provider, index in INDEXES.items():
            deadline = monotonic() + 25
            try:
                body, meta = fetch(client, index, deadline, max_bytes=4_000_000)
                candidates = dated_links(body, index)
                datasets.append(dict(meta, provider=provider, status='ok',
                                     latest_session_date=max((day for _, day in candidates), default=None)))
            except (httpx.HTTPError, ValueError, UnicodeError):
                datasets.append({'provider': provider, 'source_url': index, 'status': 'unavailable'})
                continue
            selected = [(url, day) for url, day in candidates if start <= day <= end]
            if len(selected) > 6:
                limits.append(f'{provider} : seules les six dernières séances sont examinées.')
            for url, day in selected[:6]:
                try:
                    body, meta = fetch(client, url, deadline, max_bytes=4_000_000)
                    if provider == 'senat-debats':
                        # Follow an observed full-page link, never invent a content URL.
                        links = Links()
                        links.feed(body.decode('utf-8'))
                        full = [urljoin(url, href) for href in links.links
                                if re.fullmatch(r's\d{8}(?:_mono)?\.html', href)]
                        if not full:
                            raise ValueError('Compte rendu complet absent du sommaire.')
                        url = official_link(full[0], 'www.senat.fr')
                        body, meta = fetch(client, url, deadline, max_bytes=4_000_000)
                    parser = PageText()
                    parser.feed(body.decode('utf-8'))
                    text = normalize(' '.join(parser.main_parts if parser.has_main else parser.parts))
                    d = date.fromisoformat(day)
                    # Confirm the session date in the retrieved page, not only in its URL.
                    if f'{d.day} {MONTHS[d.month - 1]} {d.year}' not in text.casefold():
                        raise ValueError('Date de séance non confirmée dans la page.')
                    chunks = passages(text, topic)
                    if not chunks:
                        continue
                    events.append({'id': 'debat:' + url, 'title': f'Compte rendu de séance du {day}',
                                   'event_date': day, 'publication_date': None, 'event': 'Débat parlementaire',
                                   'decision': None, 'provider': provider, 'category': 'debat',
                                   'date_kind': 'Date de séance, confirmée dans le compte rendu',
                                   'source_url': url, 'dossier_url': url, 'source_location': 'Passages du compte rendu',
                                   'retrieved_at': meta['retrieved_at'], 'dataset_sha256': meta['sha256'],
                                   'content_passages': chunks,
                                   'description': 'Passages pertinents retrouvés dans le compte rendu ; aucune adoption déduite.'})
                except (httpx.HTTPError, ValueError, UnicodeError):
                    limits.append('Compte rendu non exploitable : ' + url)
    return events, datasets, limits
