"""Typed comparison call. File inputs must first go through SDK prepareInputs.

Does not run on import. External execution is disabled by default in the factory.
"""
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from pipelex_sdk.runs import RunResults, WaitForResultOptions
from backend.clients import pipelex_client
from backend.generated.political_watch.models import ChangeReport, ComparisonRequest
from backend.comparison_validation import validate_report, validate_request

ROOT = Path(__file__).resolve().parents[1]
BUNDLE_DIR = ROOT / 'methods/political_watch'
PIPE_CODE = 'political_watch.compare_document'


@dataclass(frozen=True)
class ComparisonRun:
    output: ChangeReport
    results: RunResults


def method_contents() -> list[str]:
    files = sorted(BUNDLE_DIR.rglob('*.mthds'))
    hashes = {f.relative_to(ROOT).as_posix(): hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
    sidecar = json.loads((ROOT / 'backend/generated/political_watch/sources.json').read_text(encoding='utf-8'))
    if not files or hashes != sidecar['sources']:
        raise RuntimeError('Méthode modifiée : régénérer les types avant tout appel.')
    return [f.read_text(encoding='utf-8') for f in files]


async def compare_document(request: ComparisonRequest) -> ComparisonRun:
    payload = request.model_dump()
    validate_request(payload)
    contents = method_contents()
    async with pipelex_client() as client:
        results = await client.start_and_wait(
            pipe_code=PIPE_CODE, mthds_contents=contents, inputs={'request': payload},
            wait_options=WaitForResultOptions(timeout_seconds=180))
    # Validate the raw response before Pydantic can discard unknown fields.
    validate_report(payload, results.main_stuff)
    return ComparisonRun(ChangeReport.model_validate(results.main_stuff), results)
