"""Official Assembly JSON archive: document notices, never reconstructed legal text."""
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
import hashlib
import io
import json
import re
from time import monotonic
import zipfile

import httpx

from backend.data_sources.senate import _terms

DATASET_URL = 'https://data.assemblee-nationale.fr/static/openData/repository/17/loi/dossiers_legislatifs/Dossiers_Legislatifs.json.zip'
MAX_BYTES = 25_000_000
MAX_UNPACKED = 150_000_000
MAX_MEMBER = 5_000_000


@dataclass(frozen=True)
class AssemblyDocument:
    id: str
    title: str
    kind: str
    initial_date: str | None
    publication_date: str | None
    web_publication_date: str | None
    document_url: str
    dossier_url: str | None
    dossier_id: str | None


def _iso(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError('Date AN invalide.')
    parsed = datetime.fromisoformat(value)
    return parsed.date().isoformat()


def parse_archive(payload: bytes) -> list[AssemblyDocument]:
    if len(payload) > MAX_BYTES:
        raise ValueError('Archive AN trop volumineuse.')
    records: dict[str, AssemblyDocument] = {}
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        members = archive.infolist()
        if len(members) > 30_000 or sum(m.file_size for m in members) > MAX_UNPACKED:
            raise ValueError('Archive AN au-delà des limites de décompression.')
        names = set()
        for member in members:
            if member.filename in names:
                raise ValueError('Entrée ZIP dupliquée.')
            names.add(member.filename)
            if not re.fullmatch(r'json/document/[A-Za-z0-9_-]+\.json', member.filename):
                continue
            if member.file_size > MAX_MEMBER or member.flag_bits & 1:
                raise ValueError('Notice trop volumineuse ou chiffrée.')
            # Nothing is extracted to disk: ZIP paths cannot escape a directory.
            document = json.loads(archive.read(member)).get('document')
            if not isinstance(document, dict):
                raise ValueError('Structure de notice AN inconnue.')
            label = document.get('denominationStructurelle', '').casefold()
            kind = ('proposition_de_loi' if label.startswith('proposition de loi') else
                    'projet_de_loi' if label.startswith('projet de loi') else None)
            if kind is None or str(document.get('legislature')) != '17':
                continue
            uid = document.get('uid', '')
            if not re.fullmatch(r'(?:PION|PRJL)ANR[0-9]+L17B[0-9]+', uid):
                continue
            title = document.get('titres', {}).get('titrePrincipal')
            if not isinstance(title, str) or not title.strip():
                raise ValueError('Titre AN manquant.')
            chrono = (document.get('cycleDeVie') or {}).get('chrono') or {}
            dossier = document.get('dossierRef')
            if dossier is not None and not re.fullmatch(r'DLR[0-9]+L[0-9]+N[0-9]+', dossier):
                raise ValueError('Identifiant de dossier AN invalide.')
            # Official dyn/opendata pattern documented in the Assembly FAQ.
            # This is a candidate URL; only a successful fetch supplies evidence.
            record = AssemblyDocument('assemblee:' + uid, title.strip(), kind,
                                      _iso(chrono.get('dateDepot')), _iso(chrono.get('datePublication')),
                                      _iso(chrono.get('datePublicationWeb')),
                                      f'https://www.assemblee-nationale.fr/dyn/opendata/{uid}.html',
                                      f'https://www.assemblee-nationale.fr/dyn/17/dossiers/{dossier}' if dossier else None,
                                      dossier)
            if uid in records and records[uid] != record:
                raise ValueError('Notices AN contradictoires pour un même identifiant.')
            records[uid] = record
    if not records:
        raise ValueError('Aucune notice législative reconnue ; vérifier le format AN.')
    return list(records.values())


def fetch_dataset(*, transport=None) -> tuple[bytes, dict]:
    deadline = monotonic() + 30
    with httpx.Client(transport=transport, timeout=10, trust_env=False, follow_redirects=False) as client:
        with client.stream('GET', DATASET_URL) as response:
            if response.status_code != 200:
                raise ValueError(f'Archive AN indisponible (HTTP {response.status_code}).')
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > MAX_BYTES or monotonic() > deadline:
                    raise ValueError('Limite de téléchargement AN atteinte.')
            return bytes(body), {'source_url': DATASET_URL, 'origin': 'official-download',
                                 'retrieved_at': datetime.now(timezone.utc).isoformat(),
                                 'http_last_modified': response.headers.get('last-modified'),
                                 'sha256': hashlib.sha256(body).hexdigest()}


def select(records, topic, start, end, limit=3):
    if date.fromisoformat(start) > date.fromisoformat(end) or not 1 <= limit <= 6:
        raise ValueError('Période ou limite AN invalide.')
    terms = _terms(topic)
    if not terms:
        raise ValueError('Sujet trop vague.')
    matches = [r for r in records if terms <= _terms(r.title) and r.initial_date
               and start <= r.initial_date <= end]
    return sorted(matches, key=lambda r: (r.initial_date, r.id), reverse=True)[:limit]


def inventory(topic, start, end, *, transport=None):
    payload, provenance = fetch_dataset(transport=transport)
    records = parse_archive(payload)
    return {'dataset': provenance, 'parsed_law_documents': len(records),
            'records': [asdict(r) for r in select(records, topic, start, end)]}
