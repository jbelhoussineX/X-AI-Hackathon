"""Load the local closure whose generated types match its source hashes."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_bundle(name: str) -> list[str]:
    if name not in ('political_search', 'political_report'):
        raise ValueError('Méthode inconnue.')
    files = sorted((ROOT / 'methods' / name).rglob('*.mthds'))
    hashes = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    sidecar = json.loads((ROOT / 'backend/generated' / name / 'sources.json').read_text(encoding='utf-8'))
    if not files or hashes != sidecar['sources']:
        raise RuntimeError('Méthode modifiée : régénérer les types avant tout appel.')
    return [p.read_text(encoding='utf-8') for p in files]
