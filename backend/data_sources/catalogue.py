"""Export all recognized law notices for a period, without a topic cap or inference.

This is an inventory of metadata, not a mirror of every legislative text or a
database of consolidated law. Reports continue to use a bounded corpus.
"""
import argparse
from dataclasses import asdict
from datetime import date, datetime, timezone
import json
from pathlib import Path

import httpx

from backend.data_sources import assembly, senate


DATE_FIELDS = ('initial_date', 'publication_date', 'web_publication_date', 'promulgation_date')


def build(start: str, end: str, *, transport=None) -> dict:
    if date.fromisoformat(start) > date.fromisoformat(end):
        raise ValueError('Période de catalogue invalide.')
    # Include every supported archive: an old deposit may have a later publication.
    notices, datasets = assembly.load_inventories(assembly.DATASET_URLS, transport=transport)
    records = [dict(asdict(r), provider='assemblee') for r in notices]
    try:
        payload, provenance = senate.fetch_dataset(transport=transport)
        dossiers = senate.parse_csv(payload)
        records.extend(dict(asdict(r), provider='senat') for r in dossiers)
        datasets.append(dict(provenance, provider='senat', status='ok', parsed_law_documents=len(dossiers)))
    except (httpx.HTTPError, ValueError, UnicodeError) as exc:
        datasets.append({'provider': 'senat', 'source_url': senate.DATASET_URL,
                         'status': 'unavailable', 'error_type': type(exc).__name__})
    selected, undated = [], 0
    for record in records:
        dates = {field: record.get(field) for field in DATE_FIELDS if record.get(field)}
        if not dates:
            undated += 1
        matching = [field for field, value in dates.items() if start <= value <= end]
        if matching:
            selected.append(dict(record, period_matched_on=matching))
    selected.sort(key=lambda r: (max(r[field] for field in r['period_matched_on']), r['id']), reverse=True)
    return {
        'schema_version': '1.0', 'created_at': datetime.now(timezone.utc).isoformat(),
        'start': start, 'end': end, 'datasets': datasets,
        'status': 'ok' if all(d['status'] == 'ok' for d in datasets) else 'partial',
        'parsed_notices': len(records), 'undated_notices_excluded': undated,
        'record_count': len(selected), 'records': selected,
        'limitations': [
            'Toutes les notices reconnues de projets/propositions dans ces exports sont examinées ; '
            'aucune limite de sujet ou de nombre de résultats dans ce catalogue.',
            'Une date connue de dépôt, publication ou promulgation doit être dans la période ; '
            'les notices sans date sont comptées séparément et exclues.',
            'Les versions et les notices des deux chambres sont conservées séparément : '
            'le nombre de notices n’est pas un nombre de lois distinctes.',
            'Métadonnées uniquement : les textes intégraux sont lus à la demande par la recherche. '
            'Les URL candidates de l’Assemblée ne sont pas des preuves de consultation.',
            'Assemblée : 15e à 17e législatures ; Sénat : export DOSLEG. '
            'Les lois promulguées sont repérées par les métadonnées Sénat quand elles existent. '
            'Aucune garantie d’exhaustivité de toutes les lois ni du droit en vigueur ; Légifrance non connecté.',
            'Instantané à actualiser en relançant la commande ; pas de synchronisation quotidienne.',
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description='Catalogue de notices parlementaires, sans appel IA.')
    parser.add_argument('--start', default='2017-06-21')
    parser.add_argument('--end', default=date.today().isoformat())
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error('Choisir un nouveau fichier de sortie pour conserver les anciens instantanés.')
    result = build(args.start, args.end)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(f"{result['record_count']} notices ; état {result['status']} ; aucun appel IA. {args.output}")
    return 0 if result['status'] == 'ok' else 1


if __name__ == '__main__':
    raise SystemExit(main())
