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
    # Reuse archive size, path, duplicate and decompression checks.
    assembly.parse_archive(payload)
    terms = senate._terms(topic)
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
            if not isinstance(title, str) or not terms <= senate._terms(title):
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
    terms = senate._terms(topic)
    events = []
    for record in senate.parse_csv(payload):
        if not terms <= senate._terms(record.title + ' ' + record.themes):
            continue
        for value, kind, label in ((record.initial_date, 'Date initiale', 'Dépôt initial'),
                                   (record.promulgation_date, 'Date de promulgation', 'Promulgation')):
            if value and start <= value <= end:
                events.append({'id': f'{record.id}:{kind}:{value}', 'title': record.title,
                               'event_date': value, 'event': label, 'decision': None,
                               'provider': 'senat', 'date_kind': kind,
                               'source_url': senate.DATASET_URL,
                               'source_location': f'Dossier {record.id}, colonne {kind}',
                               'dossier_url': record.dossier_url})
    return events


def search_recent(topic: str, days: int = 3, *, months=None, today=None, transport=None):
    if not isinstance(topic, str) or not 3 <= len(topic.strip()) <= 300 or not senate._terms(topic):
        raise ValueError('Indiquer un sujet précis de 3 à 300 caractères.')
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
    start, end = start_date.isoformat(), today.isoformat()
    events, datasets = [], []
    limits = [
        'Signaux des inventaires officiels, sans synthèse IA : les pages des dossiers ne sont pas relues ici.',
        'Assemblée : actes datés des dossiers législatifs de la 17e législature, y compris leurs étapes au Sénat.',
        'Export Sénat : dépôts initiaux et promulgations uniquement ; les autres évolutions ne sont pas couvertes par cet export.',
        'Recherche lexicale sur titres/thèmes, non exhaustive. Dates inconnues ou futures exclues. '
        'Une réunion inscrite au dossier ne prouve pas à elle seule qu’elle a effectivement eu lieu.',
        'La date de collecte ne garantit pas la date de mise à jour du producteur ; aucun statut en vigueur n’est déduit.',
    ]
    for provider, module, parse in (('assemblee', assembly, assembly_events), ('senat', senate, senate_events)):
        try:
            payload, provenance = module.fetch_dataset(transport=transport)
            found = parse(payload, topic, start, end)
            for event in found:
                event['retrieved_at'] = provenance['retrieved_at']
                event['dataset_sha256'] = provenance['sha256']
            events.extend(found)
            datasets.append(dict(provenance, provider=provider, status='ok'))
        except (httpx.HTTPError, ValueError, UnicodeError, zipfile.BadZipFile, RuntimeError) as exc:
            datasets.append({'provider': provider, 'status': 'unavailable', 'error_type': type(exc).__name__})
            limits.append(f'Inventaire {provider} indisponible ou format non reconnu : couverture partielle.')
    from backend.data_sources.live_feeds import collect
    fresh, feed_datasets, feed_limits = collect(topic, start, end, transport=transport)
    events.extend(fresh)
    datasets.extend(feed_datasets)
    limits.extend(feed_limits)
    from backend.data_sources.debates import collect as collect_debates
    debates, debate_datasets, debate_limits = collect_debates(topic, start, end, transport=transport)
    events.extend(debates)
    datasets.extend(debate_datasets)
    limits.extend(debate_limits)
    for event in events:
        event.setdefault('category', 'procedure')
        event.setdefault('publication_date', event.get('published_at', '')[:10] or None)
    # Preserve distinct versions/acts. Exact repetitions alone are removed.
    unique: dict[tuple, dict] = {}
    for event in events:
        key = (event['id'], event['event_date'], event['event'], event['decision'])
        unique.setdefault(key, event)
    ordered = sorted(unique.values(), key=lambda e: (e['event_date'], e['id']), reverse=True)
    if len(ordered) > 20:
        limits.append(f'Affichage limité aux 20 événements les plus récents sur {len(ordered)} repérés.')
    return {'topic': topic.strip(), 'start': start, 'end': end,
            'collected_at': datetime.now(timezone.utc).isoformat(),
            'events': ordered[:20], 'total_events': len(ordered), 'datasets': datasets,
            'limitations': limits}
