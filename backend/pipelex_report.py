"""Typed hosted method. File-bearing callers should use SDK prepare_inputs first."""
from dataclasses import dataclass
from pipelex_sdk.runs import RunResults, WaitForResultOptions
from backend.clients import pipelex_client
from backend.method_bundle import read_bundle
from backend.generated.political_report.models import ReportRequest, Report


@dataclass(frozen=True)
class MethodRun:
    output: Report
    results: RunResults


async def build_report(request: ReportRequest) -> MethodRun:
    contents = read_bundle('political_report')
    async with pipelex_client() as client:
        results = await client.start_and_wait(
            pipe_code='political_report.build_report', mthds_contents=contents,
            inputs={'request': request.model_dump()},
            wait_options=WaitForResultOptions(timeout_seconds=180))
    return MethodRun(Report.model_validate(results.main_stuff), results)
