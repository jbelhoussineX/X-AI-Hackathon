"""Group the same official page without conflating titles or legislative versions."""
import json
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def document_key(url):
    parts = urlsplit(url)
    host = parts.netloc.lower()
    if host.startswith('www.'):
        host = host[4:]
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
             if not key.lower().startswith('utm_') and key.lower() not in ('fbclid', 'gclid')]
    # This key is never fetched. Keep meaningful query parameters and path case.
    return urlunsplit(('https', host, parts.path.rstrip('/'), urlencode(sorted(query)), ''))


def group_events(events):
    groups, seen = {}, set()
    repetitions = 0
    for event in events:
        page = document_key(event['dossier_url']) if event.get('dossier_url') else ''
        # Ignore collector-specific IDs and provenance, never content or version hashes.
        comparable = {key: value for key, value in event.items() if key not in (
            'id', 'provider', 'source_url', 'source_location', 'retrieved_at', 'dossier_url')}
        identity = json.dumps([page, comparable], sort_keys=True, ensure_ascii=False)
        if identity in seen:
            repetitions += 1
            continue
        seen.add(identity)
        groups.setdefault(page or identity, []).append(event)
    return list(groups.values()), repetitions


def group_summaries(items):
    groups, seen = {}, set()
    for index, item in enumerate(items):
        url = item.get('dossier_url') or item.get('url')
        key = document_key(url) if url else f'missing:{index}'
        identity = (key, item.get('event_date'), item.get('event_label'),
                    item.get('sha256') or item.get('text') or item.get('summary'))
        if identity in seen:
            continue
        seen.add(identity)
        groups.setdefault(key, []).append(item)
    return list(groups.values())
