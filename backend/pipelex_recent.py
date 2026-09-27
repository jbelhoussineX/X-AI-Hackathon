"""Typed hosted Pipelex call; prepare_inputs is needed for file-bearing methods only."""
from pipelex_sdk.runs import WaitForResultOptions
from backend.clients import pipelex_client
from backend.method_bundle import read_bundle
from backend.generated.recent_brief.models import Request, Brief


async def summarize(request: Request) -> Brief:
    contents = read_bundle('recent_brief')
    async with pipelex_client() as client:
        result = await client.start_and_wait(
            pipe_code='recent_brief.summarize', mthds_contents=contents,
            inputs={'request': request.model_dump()},
            wait_options=WaitForResultOptions(timeout_seconds=180))
    return Brief.model_validate(result.main_stuff)
