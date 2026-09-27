"""Dated official events, independent of the original deposit/publication filter.

These are inventory signals, not inferred legal status or LLM-generated claims.
"""
import calendar
from datetime import date, datetime, timedelta, timezone
import io
import json
import re
import zipfile

import httpx

from backend.data_sources import assembly, senate


def _acts(container, path='actesLegislatifs', depth=0):
    if not container:
        return
    if depth > 24 or not isinstance(container, dict):
        raise ValueError('Structure des actes non reconnue.')
    acts = container.get('acteLegislatif') or []
    if isinstance(acts, dict):
        acts = [acts]
    if not isinstance(acts, list):
        raise ValueError('Actes mal formés.')
    for index, act in enumerate(acts):
        if not isinstance(act, dict):
            raise ValueError('Acte mal formé.')
        location = f'{path}.acteLegislatif[{index}]'
        yield act, location
        yield from _acts(act.get('actesLegislatifs'), location + '.actesLegislatifs', depth + 1)


def assembly_events(payload, topic, start, end):
    return _assembly_events(payload, [topic], start, end)


def _matches(terms_by_topic, text):
    if not terms_by_topic:
        return True  # Candidate inventory: semantic relevance is decided by the agent.
    available = senate._terms(text)
    return any(terms <= available for terms in terms_by_topic)


def _assembly_events(payload, topics, start, end):
    # Reuse archive size, path, duplicate and decompression checks.
    assembly.parse_archive(payload)
    terms_by_topic = [senate._terms(topic) for topic in topics]
    events = []
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for member in archive.infolist():
            if not re.fullmatch(r'json/dossierParlementaire/DLR[0-9]+L[0-9]+N[0-9]+\.json', member.filename):
                continue
            if member.file_size > assembly.MAX_MEMBER or member.flag_bits & 1:
                raise ValueError('Dossier trop volumineux ou chiffré.')
            dossier = json.loads(archive.read(member)).get('dossierParlementaire')
            if not isinstance(dossier, dict):
                raise ValueError('Dossier mal formé.')
            if dossier.get('@xsi:type') != 'DossierLegislatif_Type' or str(dossier.get('legislature')) != '17':
                continue
            procedure = (dossier.get('procedureParlementaire') or {}).get('libelle', '').casefold()
            if not procedure.startswith(('projet de loi', 'proposition de loi')):
                continue
            title = (dossier.get('titreDossier') or {}).get('titre', '')
            if not isinstance(title, str) or not _matches(terms_by_topic, title):
                continue
            uid = dossier.get('uid', '')
            if member.filename != f'json/dossierParlementaire/{uid}.json':
                raise ValueError('Identifiant de dossier incohérent.')
            for act, location in _acts(dossier.get('actesLegislatifs')):
                event_date = assembly._iso(act.get('dateActe'))
                if not event_date or not start <= event_date <= end:
                    continue
                label = (act.get('libelleActe') or {}).get('nomCanonique')
                if not isinstance(label, str) or not label.strip():
                    continue
                # Keep the recorded decision distinct from the type of procedural act.
                conclusion = (act.get('statutConclusion') or {}).get('libelle')
                events.append({'id': f'assemblee:{uid}:{act.get("uid") or location}',
                               'title': title, 'event_date': event_date, 'event': label,
                               'decision': conclusion if isinstance(conclusion, str) else None,
                               'provider': 'assemblee', 'date_kind': 'dateActe',
                               'source_url': assembly.DATASET_URL,
                               'source_location': member.filename + ':' + location,
                               'dossier_url': f'https://www.assemblee-nationale.fr/dyn/17/dossiers/{uid}'})
    return events


def senate_events(payload, topic, start, end):
    return _senate_events(payload, [topic], start, end)


def _senate_events(payload, topics, start, end):
    terms_by_topic = [senate._terms(topic) for topic in topics]
    events = []
    for record in senate.parse_csv(payload):
        if not _matches(terms_by_topic, record.title + ' ' + record.themes):
            continue
        for value, kind, label in ((record.initial_date, 'Date initiale', 'Dépôt initial'),
                                   (record.promulgation_date, 'Date de promulgation', 'Promulgation')):
            if value and start <= value <= end:
                events.append({'id': f'{record.id}:{kind}:{value}', 'title': record.title, 'themes': record.themes,
                               'event_date': value, 'event': label, 'decision': None,
                               'provider': 'senat', 'date_kind': kind,
                               'source_url': senate.DATASET_URL,
                               'source_location': f'Dossier {record.id}, colonne {kind}',
                               'dossier_url': record.dossier_url})
    return events


def search_recent(topic: str, days: int = 3, *, months=None, today=None, transport=None):
    if not isinstance(topic, str) or not 3 <= len(topic.strip()) <= 300 or not senate._terms(topic):
        raise ValueError('Indiquer un sujet précis de 3 à 300 caractères.')
    start, end = _period(days, months, today)
    return _search([topic.strip()], start, end, transport=transport)


def search_topics(topics: list[str], days: int = 3, *, months=None, today=None, transport=None):
    """Union of independent topics, with a single fetch/parse of each inventory.

    All significant words within one topic must match, but separate topics are
    combined with OR. Feed and debate collectors retain their own bounded
    retrieval and are run once per distinct topic. No IA call or automatic retry.
    """
    if not isinstance(topics, list) or not 1 <= len(topics) <= 8:
        raise ValueError('Choisir entre un et huit sujets.')
    selected, seen = [], set()
    for topic in topics:
        if (not isinstance(topic, str) or not 3 <= len(topic.strip()) <= 100
                or any(ord(char) < 32 or ord(char) == 127 for char in topic)
                or not senate._terms(topic)):
            raise ValueError('Chaque sujet doit contenir de 3 à 100 caractères significatifs.')
        topic = topic.strip()
        if topic.casefold() not in seen:
            selected.append(topic)
            seen.add(topic.casefold())
    start, end = _period(days, months, today)
    result = _search(selected, start, end, transport=transport)
    result['topics'] = selected
    return result


def _period(days, months, today):
    if type(days) is not int or not 1 <= days <= 90:
        raise ValueError('Choisir entre 1 et 90 jours.')
    today = today or date.today()
    if months is not None:
        if type(months) is not int or not 1 <= months <= 12:
            raise ValueError('Choisir entre 1 et 12 mois.')
        absolute_month = today.year * 12 + today.month - 1 - months
        year, month = divmod(absolute_month, 12)
        month += 1
        start_date = date(year, month, min(today.day, calendar.monthrange(year, month)[1]))
    else:
        start_date = today - timedelta(days=days - 1)
    return start_date.isoformat(), today.isoformat()


def _stable_key(item):
    # Another retrieval time alone is not a new document version. Preserve every
    # other difference, including source hashes, exact passages and procedural acts.
    return json.dumps({key: value for key, value in item.items() if key != 'retrieved_at'},
                      sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def collect_candidates(*, days=3, months=None, today=None, transport=None):
    """Bounded dated inventory without a keyword relevance filter."""
    start, end = _period(days, months, today)
    return _search([], start, end, transport=transport, candidate_limit=120)


def _search(topics, start, end, *, transport=None, candidate_limit=None):
    events, datasets = [], []
    limits = [
        'Signaux des inventaires officiels, sans synthèse IA : les pages des dossiers ne sont pas relues ici.',
        'Assemblée : actes datés des dossiers législatifs de la 17e législature, y compris leurs étapes au Sénat.',
        'Export Sénat : dépôts initiaux et promulgations uniquement ; les autres évolutions ne sont pas couvertes par cet export.',
        'Recherche lexicale sur titres/thèmes, non exhaustive. Dates inconnues ou futures exclues. '
        'Une réunion inscrite au dossier ne prouve pas à elle seule qu’elle a effectivement eu lieu.',
        'La date de collecte ne garantit pas la date de mise à jour du producteur ; aucun statut en vigueur n’est déduit.',
    ]
    if len(topics) > 1:
        limits.extend([
            'Recherche par union : un événement peut correspondre à un seul des sujets choisis. '
            'Les mots significatifs de chaque sujet restent recherchés ensemble.',
            'Les inventaires Assemblée/Sénat sont téléchargés et analysés une fois. '
            'Les flux et débats sont consultés séparément pour chaque sujet : '
            'des pages peuvent être téléchargées plusieurs fois et la collecte peut être plus longue.',
        ])
    for provider, module, parse in (('assemblee', assembly, _assembly_events), ('senat', senate, _senate_events)):
        try:
            payload, provenance = module.fetch_dataset(transport=transport)
            found = parse(payload, topics, start, end)
            for event in found:
                event['retrieved_at'] = provenance['retrieved_at']
                event['dataset_sha256'] = provenance['sha256']
            events.extend(found)
            datasets.append(dict(provenance, provider=provider, status='ok'))
        except (httpx.HTTPError, ValueError, UnicodeError, zipfile.BadZipFile, RuntimeError) as exc:
            datasets.append({'provider': provider, 'status': 'unavailable', 'error_type': type(exc).__name__})
            limits.append(f'Inventaire {provider} indisponible ou format non reconnu : couverture partielle.')
    from backend.data_sources.live_feeds import collect
    from backend.data_sources.debates import collect as collect_debates
    for topic in topics or [None]:
        for provider, collector in (('flux-officiels', collect), ('debats-officiels', collect_debates)):
            try:
                found, source_datasets, source_limits = collector(topic, start, end, transport=transport)
                events.extend(found)
                datasets.extend(source_datasets)
                limits.extend(source_limits)
            except (httpx.HTTPError, ValueError, UnicodeError, RuntimeError) as exc:
                datasets.append({'provider': provider, 'status': 'unavailable',
                                 'error_type': type(exc).__name__, 'topic': topic})
                limits.append(f'Collecte {provider} indisponible pour « {topic} » : couverture partielle.')
    for event in events:
        event.setdefault('category', 'procedure')
        event.setdefault('publication_date', event.get('published_at', '')[:10] or None)
    # Preserve distinct versions/acts. Exact repetitions alone are removed.
    unique: dict[str, dict] = {}
    for event in events:
        unique.setdefault(_stable_key(event), event)
    ordered = sorted(unique.values(), key=lambda e: (e['event_date'], e['id']), reverse=True)
    if candidate_limit is not None:
        # Feeds may download adjacent days; never offer out-of-window notices to IA.
        ordered = [event for event in ordered if start <= event['event_date'] <= end]
        # Round-robin over providers prevents one prolific feed hiding the others.
        from collections import defaultdict, deque
        groups = defaultdict(deque)
        for event in ordered:
            groups[event['provider']].append(event)
        candidates = []
        while len(candidates) < candidate_limit and any(groups.values()):
            for group in groups.values():
                if group and len(candidates) < candidate_limit:
                    candidates.append(group.popleft())
        displayed = candidates
        limits = [line for line in limits if not line.startswith('Recherche lexicale')]
        limits.append(f'Sélection IA sur {len(candidates)} notices datées parmi {len(ordered)} collectées, '
                      'sans filtre lexical ; priorité aux plus récentes par fournisseur. Couverture partielle.')
    else:
        displayed = ordered[:20]
    if candidate_limit is None and len(ordered) > 20:
        limits.append(f'Affichage limité aux 20 événements les plus récents sur {len(ordered)} repérés.')
    unique_datasets = {}
    for dataset in datasets:
        unique_datasets.setdefault(_stable_key(dataset), dataset)
    return {'topic': ' · '.join(topics), 'start': start, 'end': end,
            'collected_at': datetime.now(timezone.utc).isoformat(),
            'events': displayed, 'total_events': len(ordered),
            'datasets': list(unique_datasets.values()),
            'limitations': list(dict.fromkeys(limits))}
