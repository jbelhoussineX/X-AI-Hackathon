"""Bounded official publication feeds. No inference, redirects, or credentials."""
import csv
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import html
import io
import re
from time import monotonic
from urllib.parse import urlsplit, urlunsplit
from xml.etree import ElementTree as ET

import httpx

from backend.data_sources.senate import _terms

SENATE_FEEDS = ('https://www.senat.fr/rss/textes.rss', 'https://www.senat.fr/rss/rapports.rss',
                'https://www.senat.fr/rss/presse.rss')
PUBLICATIONS = 'https://www.assemblee-nationale.fr/dyn/opendata/list-publication/publication_'
MAX_BYTES = 2_000_000
MAX_DETAILS = 12


def official_link(url, host):
    p = urlsplit(url)
    if (p.scheme not in ('http', 'https') or p.hostname != host or p.port is not None
            or p.username is not None or p.password is not None or p.query or p.fragment
            or '\\' in url or any(c.isspace() or ord(c) < 32 for c in url)):
        raise ValueError('Lien de flux non autorisé.')
    return urlunsplit(('https', host, p.path, '', ''))


def xml_root(payload):
    if len(payload) > MAX_BYTES or b'\x00' in payload or re.search(br'<!\s*(DOCTYPE|ENTITY)', payload, re.I):
        raise ValueError('XML refusé.')
    try:
        return ET.fromstring(payload)
    except ET.ParseError as exc:
        raise ValueError('XML non reconnu.') from exc


def plain(text):
    return ' '.join(html.unescape(re.sub(r'<[^>]*>', ' ', html.unescape(text))).split())


def fetch(client, url, deadline, *, max_bytes=MAX_BYTES):
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise ValueError('Budget de collecte atteint.')
    with client.stream('GET', url, timeout=min(6, remaining)) as response:
        response.raise_for_status()
        if response.status_code != 200:
            raise ValueError('Réponse non exploitable.')
        body = bytearray()
        for chunk in response.iter_bytes():
            body.extend(chunk)
            if len(body) > max_bytes or monotonic() > deadline:
                raise ValueError('Flux trop volumineux ou délai dépassé.')
    return bytes(body), {'source_url': url, 'retrieved_at': datetime.now(timezone.utc).isoformat(),
                         'sha256': hashlib.sha256(body).hexdigest()}


def rss_events(payload, topic, start, end, url):
    root = xml_root(payload)
    if root.tag != 'rss' or root.find('channel') is None:
        raise ValueError('Flux RSS non reconnu.')
    events = []
    for item in root.findall('./channel/item')[:1000]:
        title, description = plain(item.findtext('title', '')), plain(item.findtext('description', ''))
        if not title or not _terms(topic) <= _terms(title + ' ' + description):
            continue
        try:
            instant = parsedate_to_datetime(item.findtext('pubDate', ''))
            if instant.tzinfo is None:
                continue
            day = instant.date().isoformat()
            link = official_link(item.findtext('link', ''), 'www.senat.fr')
        except (ValueError, TypeError, OverflowError):
            continue
        if not start <= day <= end:
            continue
        events.append({'id': f'senat-rss:{link}:{instant.isoformat()}', 'title': title,
                       'event_date': day, 'event': 'Publication signalée dans le flux RSS',
                       'decision': None, 'provider': 'senat-rss', 'date_kind': 'pubDate du flux (pas date de dépôt)',
                       'source_url': url, 'source_location': 'item/link=' + link,
            'dossier_url': link, 'description': description, 'published_at': instant.isoformat(),
            'category': 'actualite' if url.endswith('/presse.rss') else 'publication'})
    return events


def publication_rows(payload, day):
    rows = []
    for index, row in enumerate(csv.reader(io.StringIO(payload.decode('utf-8-sig')), delimiter=';'), 1):
        if not row:
            continue
        if len(row) != 2:
            raise ValueError('Liste de publications non reconnue.')
        instant = datetime.fromisoformat(row[0])
        if instant.date().isoformat() != day:
            continue
        url = official_link(row[1], 'www.assemblee-nationale.fr')
        # Only amendments, explicitly referenced as XML; never invent detail URLs.
        if re.fullmatch(r'/dyn/opendata/AMANR[0-9]+L17[A-Za-z0-9]+\.xml', urlsplit(url).path):
            rows.append((instant.isoformat(), url, index))
    return rows


def amendment_event(payload, topic, timestamp, url, list_url, line):
    root = xml_root(payload)
    for element in root.iter():
        element.tag = element.tag.split('}')[-1]
    uid = root.findtext('uid', '')
    if root.tag != 'amendement' or not url.endswith('/' + uid + '.xml') or root.findtext('legislature') != '17':
        raise ValueError('Amendement non reconnu.')
    content = plain(' '.join(root.findtext(path, '') for path in (
        './corps/contenuAuteur/dispositif', './corps/contenuAuteur/exposeSommaire')))
    if not _terms(topic) <= _terms(content):
        return None
    return {'id': f'assemblee-publication:{uid}:{timestamp}', 'title': 'Amendement ' + root.findtext('./identification/numeroLong', uid),
            'event_date': timestamp[:10], 'event': 'Publication ou republication d’un amendement',
            'decision': None, 'provider': 'assemblee-publications',
            'date_kind': 'Horodatage de mise en ligne (pas adoption ni dépôt)',
            'source_url': list_url, 'source_location': f'ligne {line} ; détail XML {url}',
            'dossier_url': url, 'published_at': timestamp, 'category': 'amendement',
            'content_passages': [content[:12000]],
            'description': 'Sujet repéré dans le dispositif ou l’exposé sommaire ; cela ne signifie pas que l’amendement est adopté.'}


def collect(topic, start, end, *, transport=None):
    events: list[dict] = []
    datasets: list[dict] = []
    limits = [
        'Flux Sénat : derniers éléments disponibles, sans garantie de couvrir toute la période.',
        'Amendements Assemblée : listes des deux derniers jours seulement, au plus 12 fichiers XML lus '
        '(les plus récents), correspondance dans le dispositif/exposé ; couverture partielle.',
        'Dates de flux = mise en ligne ou republication, pas nécessairement date du texte ou adoption. '
        'Actualisation au clic uniquement, pas de surveillance automatique.']
    deadline = monotonic() + 35
    with httpx.Client(transport=transport, trust_env=False, follow_redirects=False) as client:
        feeds = list(SENATE_FEEDS)
        if 'logement' in _terms(topic):
            feeds.append('https://www.senat.fr/themes/rss/therss16.rss')
        for url in feeds:
            try:
                payload, meta = fetch(client, url, deadline)
                found = rss_events(payload, topic, start, end, url)
                events.extend(dict(e, retrieved_at=meta['retrieved_at'], dataset_sha256=meta['sha256']) for e in found)
                datasets.append(dict(meta, provider='senat-rss', status='ok'))
            except (httpx.HTTPError, ValueError):
                datasets.append({'provider': 'senat-rss', 'source_url': url, 'status': 'unavailable'})
        candidates: list[tuple] = []
        for offset in range(2):
            day = (date.fromisoformat(end) - timedelta(days=offset)).isoformat()
            url = PUBLICATIONS + day + '.csv'
            try:
                payload, meta = fetch(client, url, deadline)
                rows = publication_rows(payload, day)
                candidates.extend((stamp, detail, line, url, meta) for stamp, detail, line in rows)
                datasets.append(dict(meta, provider='assemblee-publications', status='ok'))
            except (httpx.HTTPError, ValueError):
                datasets.append({'provider': 'assemblee-publications', 'source_url': url, 'status': 'unavailable'})
        # Several republications of one amendement: read its current file only once.
        seen: set[str] = set()
        for stamp, url, line, list_url, meta in sorted(candidates, key=lambda r: r[:2], reverse=True):
            if url in seen:
                continue
            if len(seen) >= MAX_DETAILS:
                limits.append('Limite de 12 amendements atteinte : autres publications non examinées.')
                break
            seen.add(url)
            try:
                payload, detail_meta = fetch(client, url, deadline)
                event = amendment_event(payload, topic, stamp, url, list_url, line)
                if event:
                    events.append(dict(event, retrieved_at=detail_meta['retrieved_at'],
                                       dataset_sha256=meta['sha256'], detail_sha256=detail_meta['sha256']))
            except (httpx.HTTPError, ValueError):
                limits.append('Un amendement n’a pas pu être lu : ' + url)
    return events, datasets, limits
