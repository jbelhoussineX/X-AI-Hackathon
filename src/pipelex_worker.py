"""Processus isolé : stdin = demande JSON, stdout = résultat public uniquement."""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
from pathlib import Path
import sys


async def execute(request: dict) -> dict:
    from backend.clients import require_enabled
    require_enabled("PIPELEX")
    from pipelex.pipelex import Pipelex
    from pipelex.pipeline.runner import PipelexMTHDSProtocol
    from src.openai_research import Run, ResearchFailure
    from src.pipelex_steps import bind_run

    # This worker must never return a dry-run fixture as a real search.
    if os.environ.get('PIPELEX_FORCE_DRY_RUN_MODE', '').lower() in ('1', 'true', 'yes'):
        raise ResearchFailure('configuration')
    root = Path(__file__).resolve().parents[1]
    os.environ['DO_NOT_TRACK'] = '1'
    Pipelex.make(
        config_dir=root / ".pipelex",
        library_dirs=[],
        config_overrides={
            'inference': {'transport_max_retries': 0, 'model_deck': {'is_model_fallback_enabled': False},
                          'llm': {'schema_reask_max_attempts': 1}},
            'runtime': {'tracing': {'is_enabled': False}},
            'interpreter': {'methods': {'fetch_on_miss': False},
                            'pipeline_execution': {'is_generate_graph': False, 'is_generate_usage': False}},
        },
    )
    try:
        run = Run(**request)
        bind_run(run)
        runner = PipelexMTHDSProtocol(library_dirs=[])
        result = await runner.execute(
            mthds_contents=[(root / 'methods/recherche_citoyenne/main.mthds').read_text(encoding='utf-8')],
        )
        report = json.loads(result.pipe_output.main_stuff.content.text)
        if run.calls not in ((0, 1) if run.data_source == 'official' else (3, 4)):
            raise ResearchFailure('configuration')
        return report
    finally:
        Pipelex.teardown_if_needed()


def exception_chain(exc: BaseException):
    visited: set[int] = set()
    while exc is not None and id(exc) not in visited:
        visited.add(id(exc))
        yield exc
        exc = exc.__cause__ or exc.__context__


def error_code(exc: BaseException) -> str:
    from src.openai_research import ResearchFailure
    from src.contracts import ReportError
    fallback = 'provider'
    for exc in exception_chain(exc):
        if isinstance(exc, ResearchFailure):
            return exc.code
        if isinstance(exc, ReportError):
            return 'format'
        name = type(exc).__name__
        if name in ('AuthenticationError', 'PermissionDeniedError', 'InferenceBackendCredentialsError'):
            return 'credentials'
        if name == 'RateLimitError':
            return 'quota'
        if name in ('APITimeoutError', 'TimeoutError'):
            return 'timeout'
        if name == 'APIConnectionError':
            return 'network'
        if name in ('BadRequestError', 'UnprocessableEntityError'):
            return 'request'
        if name == 'NotFoundError':
            return 'model'
        if name == 'InternalServerError':
            return 'server'
        if name in ('PipelexSetupError', 'ConfigValidationError', 'ValidateBundleError'):
            # A setup wrapper may contain the more precise missing-key error below.
            fallback = 'configuration'
            continue
        if name in ('TypeError', 'KeyError', 'AttributeError', 'ValueError'):
            return 'internal'
    return fallback


def error_diagnostic(exc: BaseException) -> dict:
    from src.pipelex_client import safe_diagnostic
    details = {}
    for cause in exception_chain(exc):
        candidate = {
            'stage': getattr(cause, 'pipe_code', None),
            'http_status': getattr(cause, 'status_code', None),
            'type': type(cause).__name__,
            'code': getattr(cause, 'code', None),
            'param': getattr(cause, 'param', None),
            'reason': getattr(cause, 'reason', None),
            'field': getattr(cause, 'field', None),
        }
        for key, value in safe_diagnostic(candidate).items():
            details.setdefault(key, value)
    return details


def main() -> int:
    os.environ['DO_NOT_TRACK'] = '1'
    # Do not return raw SDK errors or framework traces to the parent/UI.
    with open(os.devnull, 'w') as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        try:
            request = json.loads(sys.stdin.read(5000))
            report = asyncio.run(execute(request))
            payload = {'ok': True, 'report': report}
        except Exception as exc:
            payload = {'ok': False, 'error': error_code(exc), 'diagnostic': error_diagnostic(exc)}
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
