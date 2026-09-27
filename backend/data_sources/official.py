"""Two official inventories -> bounded corpus. No inference or silent web fallback."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import zipfile

import httpx

from backend.data_sources import assembly, senate
from backend.data_sources.senate_documents import collect_dossiers
from backend.source_verification import FetchedSource, normalize


def prepare(topic: str, start: str, end: str, *, transport=None) -> dict:
    senate.select([], topic, start, end)
    datasets: list[dict] = []
    records: list[dict] = []
    limits = ['Repérage lexical sur titres/thèmes, avec filtre sur le dépôt initial, '
              'distinct de la date de publication contrôlée ensuite dans le rapport.',
              'Couverture Sénat et notices des 15e, 16e et 17e législatures de l’Assemblée selon la période ; '
              'aucune prétention d’exhaustivité ou de vigueur actuelle.',
              'Au plus trois notices par institution et par collecte sont lues, '
              'parmi les correspondances lexicales les plus récentes ; le rapport contient au plus quatre documents.',
              'L’API Légifrance/PISTE n’est pas connectée ; aucun statut de droit en vigueur n’est certifié.']
    senate_corpus: list[dict] = []
    assembly_corpus: list[dict] = []
    try:
        body, provenance = senate.fetch_dataset(transport=transport)
        chosen = senate.select(senate.parse_csv(body), topic, start, end, limit=3)
        datasets.append(dict(provenance, provider='senat', status='ok'))
        records.extend(dict(asdict(r), provider='senat') for r in chosen)
        senate_corpus, _, issues = collect_dossiers([r.dossier_url for r in chosen], transport=transport)
        limits.extend(issues)
    except (httpx.HTTPError, ValueError, UnicodeError) as exc:
        datasets.append({'provider': 'senat', 'status': 'unavailable', 'error_type': type(exc).__name__})
        limits.append('Source Sénat indisponible ou format non reconnu ; aucune donnée inventée en remplacement.')
    try:
        selected = assembly.inventory(topic, start, end, transport=transport)
        datasets.extend(selected['datasets'])
        for dataset in selected['datasets']:
            if dataset['status'] != 'ok':
                limits.append(f"Archive Assemblée {dataset['legislature']}e législature indisponible ; couverture partielle.")
        if start < '2017-06-21':
            limits.append('Les législatures antérieures à la 15e ne sont pas couvertes côté Assemblée (avant juin 2017).')
        records.extend(dict(r, provider='assemblee') for r in selected['records'])
        # Reuse the same bounded URL/page verifier as the existing web route.
        from backend.data_sources.pages import collect_sources
        urls = []
        for record in selected['records']:
            urls.append(record['document_url'])
            if record['dossier_url']:
                urls.append(record['dossier_url'])
        assembly_corpus, _, issues = collect_sources(urls, transport=transport)
        limits.extend(issues)
    except (httpx.HTTPError, ValueError, UnicodeError, zipfile.BadZipFile, RuntimeError) as exc:
        datasets.append({'provider': 'assemblee', 'status': 'unavailable', 'error_type': type(exc).__name__})
        limits.append('Source Assemblée indisponible ou format non reconnu ; aucune donnée inventée en remplacement.')
    # Interleave both sources so one institution cannot consume the whole prompt budget.
    corpus = []
    seen = set()
    remaining = 60_000
    for index in range(max(len(senate_corpus), len(assembly_corpus))):
        for source in (senate_corpus, assembly_corpus):
            if index >= len(source):
                continue
            item = dict(source[index])
            if item['url'] in seen:
                continue
            seen.add(item['url'])
            if remaining <= 0:
                limits.append('Sources omises après atteinte de la limite globale de 60 000 caractères.')
                continue
            pages = item['pdf_pages'] if item['pdf_pages'] is not None else [normalize(item['text'])]
            clipped = []
            budget = remaining
            for page in pages:
                clipped.append(page[:budget])
                budget -= len(clipped[-1])
                if budget <= 0:
                    break
            used = sum(map(len, clipped))
            remaining -= used
            item['truncated'] = item['truncated'] or used < sum(map(len, pages))
            item['text'] = clipped[0] if item['pdf_pages'] is None else ''
            item['pdf_pages'] = clipped if item['pdf_pages'] is not None else None
            if item['truncated']:
                limits.append('Source transmise partiellement : ' + item['url'])
            content = {'text': item['text'], 'pdf_pages': item['pdf_pages']}
            item['content_sha256'] = hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            corpus.append(item)
    return {'schema_version': '1.0', 'topic': topic, 'start': start, 'end': end,
            'datasets': datasets, 'records': records, 'limitations': limits, 'corpus': corpus,
            'pipelex_inputs': {'request': {'topic': topic, 'start': start, 'end': end,
                                          'corpus_json': json.dumps(corpus, ensure_ascii=False)}} if corpus else None}


def fetched_corpus(corpus: list) -> dict[str, FetchedSource]:
    result = {}
    for item in corpus:
        source = FetchedSource('retrieved', item['text'], item['final_url'], item['pdf_pages'])
        result[item['url']] = source
        result.setdefault(item['final_url'], source)
    return result


def merge_prepared(initial: dict, supplement: dict) -> dict:
    """Keep the initial corpus and add unique supplemental pages within the same cap."""
    from copy import deepcopy
    result = deepcopy(initial)
    result['limitations'].extend(supplement['limitations'])
    result['datasets'].extend(supplement['datasets'])
    result['records'].extend(supplement['records'])
    seen = {item['url'] for item in result['corpus']}
    remaining = 60_000 - sum(len(item['text']) + sum(map(len, item['pdf_pages'] or []))
                             for item in result['corpus'])
    for source in supplement['corpus']:
        if source['url'] in seen:
            continue
        if remaining <= 0:
            result['limitations'].append('Complément non transmis : limite globale de 60 000 caractères atteinte.')
            break
        item = deepcopy(source)
        pages = item['pdf_pages'] if item['pdf_pages'] is not None else [item['text']]
        clipped = []
        for page in pages:
            clipped.append(page[:remaining])
            remaining -= len(clipped[-1])
            if remaining <= 0:
                break
        truncated = sum(map(len, clipped)) < sum(map(len, pages))
        item['truncated'] = item['truncated'] or truncated
        item['text'] = clipped[0] if item['pdf_pages'] is None else ''
        item['pdf_pages'] = clipped if item['pdf_pages'] is not None else None
        item['content_sha256'] = hashlib.sha256(json.dumps(
            {'text': item['text'], 'pdf_pages': item['pdf_pages']}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if truncated:
            result['limitations'].append('Complément transmis partiellement : ' + item['url'])
        result['corpus'].append(item)
        seen.add(item['url'])
    # This envelope is regenerated from the exact merged corpus.
    result['pipelex_inputs'] = None
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description='Collecte officielle sans appel IA.')
    parser.add_argument('--topic', required=True)
    parser.add_argument('--start', required=True)
    parser.add_argument('--end', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error('Choisir un nouveau fichier de sortie.')
    result = prepare(args.topic, args.start, args.end)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(f"{len(result['corpus'])} sources préparees ; aucun appel IA. {args.output}")
    return 0 if result['corpus'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
