"""Sénat DOSLEG CSV -> documented records -> optional Pipelex report inputs.

This module runs no inference. CSV metadata is discovery data, not a quote from
the legal text. The initial dossier date is not a verified publication date.
"""
import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
from time import monotonic
import unicodedata
from urllib.parse import urlsplit, urlunsplit

import httpx

DATASET_URL = 'https://data.senat.fr/data/dosleg/dossiers-legislatifs.csv'
DOCUMENTATION_URL = 'https://data.senat.fr/aide/liste-des-dossiers-legislatifs/'
MAX_BYTES = 8_000_000
HEADERS = {'Titre', 'Type de dossier', 'Date initiale', 'URL du dossier',
           'État du dossier', 'Date de promulgation', 'Numéro de la loi', 'Thèmes'}


@dataclass(frozen=True)
class Dossier:
    id: str
    title: str
    kind: str
    original_kind: str
    initial_date: str | None
    dossier_url: str
    original_url: str
    reported_state: str | None
    promulgation_date: str | None
    law_number: str | None
    themes: str


def _date(value: str) -> str | None:
    if not value.strip():
        return None
    try:
        return datetime.strptime(value.strip(), '%d/%m/%Y').date().isoformat()
    except ValueError as exc:
        raise ValueError('Date DOSLEG invalide ; format du fournisseur à vérifier.') from exc


def _url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if (parsed.scheme not in ('http', 'https') or parsed.hostname not in ('www.senat.fr', 'senat.fr')
            or parsed.username is not None or parsed.password is not None or parsed.port is not None
            or not parsed.path.startswith('/dossier-legislatif/') or not parsed.path.endswith('.html')
            or parsed.query or parsed.fragment or '\\' in value
            or any(c.isspace() or ord(c) < 32 for c in value)):
        raise ValueError('URL de dossier non autorisée dans le CSV.')
    return urlunsplit(('https', 'www.senat.fr', parsed.path, '', ''))


def parse_csv(payload: bytes) -> list[Dossier]:
    if len(payload) > MAX_BYTES:
        raise ValueError('Export DOSLEG trop volumineux.')
    # Observed official export: Windows-1252. Also accept a future UTF-8 export.
    try:
        text = payload.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = payload.decode('cp1252')
    reader = csv.DictReader(io.StringIO(text, newline=''), delimiter=';')
    if not HEADERS <= set(reader.fieldnames or []):
        raise ValueError('Colonnes DOSLEG inattendues ; ne pas interpréter un format inconnu.')
    records: dict[str, Dossier] = {}
    for row in reader:
        if None in row or any(row.get(key) is None for key in HEADERS):
            raise ValueError('Ligne DOSLEG mal formée.')
        original_kind = row['Type de dossier'].strip()
        if original_kind.startswith('projet de loi'):
            kind = 'projet_de_loi'
        elif original_kind.startswith('proposition de loi'):
            kind = 'proposition_de_loi'
        else:
            continue  # Resolutions and motions are outside the current report contract.
        url = _url(row['URL du dossier'])
        record = Dossier(
            id='senat:' + urlsplit(url).path.rsplit('/', 1)[-1].removesuffix('.html'),
            title=row['Titre'].strip(), kind=kind, original_kind=original_kind,
            initial_date=_date(row['Date initiale']), dossier_url=url,
            original_url=row['URL du dossier'], reported_state=row['État du dossier'].strip() or None,
            promulgation_date=_date(row['Date de promulgation']),
            law_number=row['Numéro de la loi'].strip() or None, themes=row['Thèmes'].strip())
        if not record.title:
            raise ValueError('Titre de dossier vide.')
        if url in records and records[url] != record:
            raise ValueError('Dossier dupliqué avec données différentes ; rapprochement manuel requis.')
        records[url] = record
    return list(records.values())


def fetch_dataset(*, transport=None) -> tuple[bytes, dict]:
    """One bounded public download, no API key, retry or automatic redirect."""
    deadline = monotonic() + 25
    with httpx.Client(transport=transport, timeout=10, follow_redirects=False, trust_env=False,
                      headers={'User-Agent': 'SedLex-Hackathon/0.1'}) as client:
        with client.stream('GET', DATASET_URL) as response:
            if response.status_code != 200:
                raise ValueError(f'Export DOSLEG indisponible (HTTP {response.status_code}).')
            media = response.headers.get('content-type', '').split(';')[0].lower().strip()
            if media not in ('text/csv', 'application/csv', 'text/plain', 'application/octet-stream'):
                raise ValueError('Format HTTP inattendu pour DOSLEG.')
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > MAX_BYTES or monotonic() > deadline:
                    raise ValueError('Limite de téléchargement DOSLEG atteinte.')
            return bytes(body), {'source_url': DATASET_URL,
                                 'retrieved_at': datetime.now(timezone.utc).isoformat(),
                                 'http_last_modified': response.headers.get('last-modified'),
                                 'sha256': hashlib.sha256(body).hexdigest(), 'origin': 'official-download'}


def _terms(value: str) -> set[str]:
    text = ''.join(c for c in unicodedata.normalize('NFKD', value.casefold()) if not unicodedata.combining(c))
    stop = {'les', 'des', 'une', 'pour', 'avec', 'dans', 'sur', 'aux', 'par', 'est', 'de', 'du', 'le', 'la', 'et'}
    return {word for word in re.findall(r'[a-z0-9]+', text) if len(word) > 2 and word not in stop}


def select(records: list[Dossier], topic: str, start: str, end: str, limit: int = 6) -> list[Dossier]:
    """All query terms must occur in title/themes; no semantic/political ranking."""
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first > last or first.isoformat() != start or last.isoformat() != end or not 1 <= limit <= 6:
        raise ValueError('Période ou limite invalide.')
    terms = _terms(topic)
    if not terms:
        raise ValueError('Sujet contenant au moins un mot significatif requis.')
    matches = [r for r in records if terms <= _terms(r.title + ' ' + r.themes)
               and r.initial_date is not None and start <= r.initial_date <= end]
    return sorted(matches, key=lambda r: (r.initial_date or '', r.id), reverse=True)[:limit]


def prepare(topic: str, start: str, end: str, *, fetch_pages=False, transport=None) -> dict:
    """Return inventory and, on request, method-ready inputs; never call Pipelex."""
    # Validate the query before downloading anything.
    select([], topic, start, end)
    payload, provenance = fetch_dataset(transport=transport)
    records = parse_csv(payload)
    selected = select(records, topic, start, end)
    limitations = [
        'Recherche lexicale : tous les mots significatifs doivent être présents dans le titre ou les thèmes.',
        'Filtre sur la date initiale du dossier (dépôt), pas sur la publication ni la dernière activité.',
        'État déclaré dans l’export au moment de la collecte ; promulgation ne signifie pas vigueur actuelle.',
        'Métadonnées de repérage uniquement : elles ne prouvent pas le contenu des dispositions.',
        'Couverture Sénat, au plus six dossiers ; une recherche vide ne démontre aucune absence de texte.']
    result = {'schema_version': '1.0', 'topic': topic, 'start': start, 'end': end,
              'dataset': provenance, 'parsed_law_dossiers': len(records),
              'records': [asdict(r) for r in selected], 'limitations': limitations,
              'pipelex_inputs': None, 'linked_documents': []}
    if fetch_pages:
        from backend.data_sources.senate_documents import collect_dossiers
        corpus, inventory, collection_limits = collect_dossiers([r.dossier_url for r in selected], transport=transport)
        result['linked_documents'] = inventory
        limitations.extend(collection_limits)
        if corpus:
            result['pipelex_inputs'] = {'request': {'topic': topic, 'start': start, 'end': end,
                                                  'corpus_json': json.dumps(corpus, ensure_ascii=False)}}
        else:
            limitations.append('Aucune page exploitable : aucune entrée de rapport préparée.')
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--topic', required=True)
    parser.add_argument('--start', required=True, help='Date initiale minimale des dossiers YYYY-MM-DD')
    parser.add_argument('--end', required=True)
    parser.add_argument('--fetch-pages', action='store_true', help='Lire aussi les pages pour préparer le corpus Pipelex')
    parser.add_argument('--output', type=Path, required=True, help='Nouveau JSON, de préférence dans data/local/')
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error('Le fichier de sortie existe déjà ; choisir un nouveau nom.')
    try:
        result = prepare(args.topic, args.start, args.end, fetch_pages=args.fetch_pages)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
        print(f"{len(result['records'])} dossier(s) sélectionné(s). Sortie : {args.output}. Aucun appel IA.")
        return 0
    except (ValueError, OSError, httpx.HTTPError) as exc:
        print(f'Échec de collecte ({type(exc).__name__}). Aucun résultat de remplacement.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
