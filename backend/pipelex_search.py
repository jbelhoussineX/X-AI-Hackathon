"""Typed hosted method. File-bearing callers should use SDK prepare_inputs first."""
from dataclasses import dataclass
from pipelex_sdk.runs import RunResults, WaitForResultOptions
from backend.clients import pipelex_client
from backend.method_bundle import read_bundle
from backend.generated.political_search.models import SearchRequest, SearchResult


@dataclass(frozen=True)
class MethodRun:
    output: SearchResult
    results: RunResults


async def find_sources(request: SearchRequest) -> MethodRun:
    contents = read_bundle('political_search')
    async with pipelex_client() as client:
        results = await client.start_and_wait(
            pipe_code='political_search.find_sources', mthds_contents=contents,
            inputs={'request': request.model_dump()},
            wait_options=WaitForResultOptions(timeout_seconds=180))
    return MethodRun(SearchResult.model_validate(results.main_stuff), results)
