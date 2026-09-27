"""Isolated Pipelex stage with a bounded, redacted worker protocol."""
import asyncio
import contextlib
import json
import os
import subprocess
import sys

from pydantic import ValidationError

from backend.agent_models import OUTPUTS
from backend.generated.recent_brief.models import Request
from backend.method_bundle import ROOT
from src.pipelex_client import PipelexError, failure_message
from src.recent_worker import execute_method


def method_contents():
    return [(ROOT / 'methods/recent_agent/main.mthds').read_text(encoding='utf-8')]


async def execute_stage(stage, request):
    if stage not in OUTPUTS:
        raise ValueError('Unknown stage')
    return await execute_method(request, method_contents(), 'recent_agent.' + stage, OUTPUTS[stage])


def run_stage(stage, request):
    if stage not in OUTPUTS:
        raise PipelexError('Étape IA inconnue. Aucun appel lancé.')
    payload = request.model_dump_json()
    if len(payload) > 200000:
        raise PipelexError('Corpus trop volumineux. Aucun appel IA lancé pour cette étape.')
    try:
        completed = subprocess.run(
            [sys.executable, '-m', 'src.recent_agent_worker', stage], cwd=ROOT,
            input=payload, text=True, encoding='utf-8', capture_output=True, timeout=180,
            env=dict(os.environ, PYTHON_DOTENV_DISABLED='1', DO_NOT_TRACK='1', PYTHONIOENCODING='utf-8'),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    except subprocess.TimeoutExpired:
        raise PipelexError(failure_message('timeout')) from None
    except OSError:
        raise PipelexError(failure_message('configuration')) from None
    try:
        if len(completed.stdout) > 100000:
            raise ValueError
        data = json.loads(completed.stdout)
        if not isinstance(data, dict):
            raise ValueError
    except (ValueError, TypeError):
        raise PipelexError(failure_message('internal')) from None
    if completed.returncode or data.get('ok') is not True:
        raise PipelexError(failure_message(data.get('error'), data.get('diagnostic'))) from None
    try:
        return OUTPUTS[stage].model_validate(data['output'])
    except ValidationError as exc:
        from src.pipelex_worker import error_diagnostic
        raise PipelexError(failure_message('format', error_diagnostic(exc))) from None
    except (ValueError, KeyError):
        raise PipelexError('Réponse IA invalide. Aucune relance automatique.') from None


def main():
    with open(os.devnull, 'w') as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        try:
            stage = sys.argv[1]
            raw = sys.stdin.read(200001)
            if len(raw) > 200000:
                raise ValueError('Oversized input')
            output = asyncio.run(execute_stage(stage, Request.model_validate_json(raw)))
            payload = {'ok': True, 'output': output.model_dump()}
        except Exception as exc:
            from src.pipelex_worker import error_code, error_diagnostic
            payload = {'ok': False, 'error': error_code(exc), 'diagnostic': error_diagnostic(exc)}
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
