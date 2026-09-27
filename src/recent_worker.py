"""Isolate the local Pipelex runtime; never expose raw provider errors."""
import asyncio
import contextlib
import json
import os
import subprocess
import sys

from backend.clients import require_enabled
from backend.generated.recent_brief.models import Request, Brief
from backend.method_bundle import ROOT, read_bundle


async def execute(request: Request) -> Brief:
    require_enabled('PIPELEX')
    if os.environ.get('PIPELEX_FORCE_DRY_RUN_MODE', '').lower() in ('1', 'true', 'yes'):
        raise ValueError('Génération fictive interdite.')
    from pipelex.pipelex import Pipelex
    from pipelex.pipeline.runner import PipelexMTHDSProtocol
    contents = read_bundle('recent_brief')
    Pipelex.make(config_dir=ROOT / '.pipelex', library_dirs=[], config_overrides={
        'inference': {'transport_max_retries': 0, 'model_deck': {'is_model_fallback_enabled': False},
                      'llm': {'schema_reask_max_attempts': 1}},
        'runtime': {'tracing': {'is_enabled': False}},
        'interpreter': {'methods': {'fetch_on_miss': False},
                        'pipeline_execution': {'is_generate_graph': False, 'is_generate_usage': False}},
    })
    try:
        runner = PipelexMTHDSProtocol(library_dirs=[])
        result = await runner.execute(pipe_code='recent_brief.summarize', mthds_contents=contents,
                                      inputs={'request': {'concept': 'recent_brief.Request',
                                                          'content': request.model_dump()}})
        return Brief.model_validate(result.pipe_output.main_stuff.content.model_dump())
    finally:
        Pipelex.teardown_if_needed()


def run_local(request: Request) -> Brief:
    require_enabled('PIPELEX')
    env = dict(os.environ, PYTHON_DOTENV_DISABLED='1', DO_NOT_TRACK='1', PYTHONIOENCODING='utf-8')
    try:
        result = subprocess.run([sys.executable, '-m', 'src.recent_worker'], cwd=ROOT,
                                input=request.model_dump_json(), text=True, encoding='utf-8',
                                capture_output=True, timeout=180, env=env,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        if result.returncode or len(result.stdout) > 100000:
            raise ValueError('Échec du moteur local.')
        return Brief.model_validate_json(result.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        raise RuntimeError('Synthèse indisponible. Vérifie l’activité du fournisseur avant de relancer ; '
                           'le délai local ne garantit pas l’arrêt distant.') from None


def main():
    with open(os.devnull, 'w') as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        try:
            request = Request.model_validate_json(sys.stdin.read(200000))
            result = asyncio.run(execute(request))
        except Exception:
            return 1
    print(result.model_dump_json())
    return 0


if __name__ == '__main__':
    sys.exit(main())
