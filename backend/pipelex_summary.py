"""Typed synthesis method. File-bearing callers should use SDK prepareInputs first."""
import asyncio
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from pipelex_sdk.runs import RunResults, WaitForResultOptions
from backend.clients import pipelex_client
from backend.generated.political_summary.models import InterestSummary, SummaryRequest

ROOT = Path(__file__).resolve().parents[1]
BUNDLE_DIR = ROOT / 'methods/political_summary'
PIPE_CODE = 'political_summary.summarize_interest'


@dataclass(frozen=True)
class SummaryRun:
    output: InterestSummary
    results: RunResults


async def summarize_interest(request: SummaryRequest) -> SummaryRun:
    files = sorted(BUNDLE_DIR.rglob('*.mthds'))
    hashes = {f.relative_to(ROOT).as_posix(): hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
    sidecar = json.loads((ROOT / 'backend/generated/political_summary/sources.json').read_text(encoding='utf-8'))
    if not files or hashes != sidecar['sources']:
        raise RuntimeError('Méthode modifiée : régénérer les types avant tout appel.')
    async with pipelex_client() as client:
        results = await client.start_and_wait(
            pipe_code=PIPE_CODE, mthds_contents=[f.read_text(encoding='utf-8') for f in files],
            inputs={'request': request.model_dump()},
            wait_options=WaitForResultOptions(timeout_seconds=180))
    return SummaryRun(InterestSummary.model_validate(results.main_stuff), results)


def analyze_summary(envelope: dict) -> dict:
    """Sync adapter for Streamlit. Preserve raw output for strict boundary checks."""
    run = asyncio.run(summarize_interest(SummaryRequest.model_validate(envelope['request'])))
    return run.results.main_stuff
