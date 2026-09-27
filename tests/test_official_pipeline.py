"""Both execution engines share the exact retrieved corpus; no external calls."""
import asyncio
import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.pipelex_research import research
from src.openai_research import Run, ResearchFailure
from test_pipelex_research import report, URL, TEXT


def prepared(empty=False):
    return {'limitations': ['Corpus fictif, hors ligne.'], 'corpus': [] if empty else [
        {'url': URL, 'final_url': URL, 'text': TEXT, 'pdf_pages': None, 'truncated': False}]}


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    monkeypatch.setenv('POLITICAL_DATA_SOURCE', 'official')
    monkeypatch.setenv('ENABLE_PIPELEX_CALLS', 'true')
    monkeypatch.setenv('PYTHON_DOTENV_DISABLED', '1')
    monkeypatch.setenv('DO_NOT_TRACK', '1')
    monkeypatch.setenv('OPENAI_API_KEY', 'offline-test-placeholder')
    def reject(*args, **kwargs):
        raise AssertionError('No real HTTP in integration tests')
    import httpx
    import httpx2
    for module in (httpx, httpx2):
        monkeypatch.setattr(module.Client, 'send', reject)
        monkeypatch.setattr(module.AsyncClient, 'send', reject)


@pytest.mark.parametrize('empty', [False, True])
def test_hosted_skips_search_and_empty_corpus_skips_generation(empty):
    result = SimpleNamespace(results=SimpleNamespace(main_stuff=report()))
    with patch('backend.data_sources.official.prepare', return_value=prepared(empty)), \
         patch('backend.pipelex_research.find_sources', side_effect=AssertionError('No web inference')), \
         patch('backend.pipelex_research.build_report', AsyncMock(return_value=result)) as build:
        output = research('Transports', start='2026-01-01', end='2026-12-31')
    assert build.call_count == (0 if empty else 1)
    assert len(output.runs) == (0 if empty else 1)
    if not empty:
        assert output.checks[0]['status'] == 'matched'
        assert TEXT in build.call_args.args[0].corpus_json


@pytest.mark.parametrize('empty', [False, True])
def test_local_real_graph_reviews_then_writes_without_web(empty):
    from src.pipelex_worker import execute
    captured = []
    async def fake(self, **kwargs):
        captured.append(kwargs)
        self.calls += 1
        payload = {'needs_more': False, 'followup_query': None, 'limitations': []} if len(captured) == 1 else report()
        return SimpleNamespace(output_text=json.dumps(payload))
    with patch('backend.data_sources.official.prepare', return_value=prepared(empty)), \
         patch.object(Run, 'call', fake):
        output = asyncio.run(execute({'topic': 'Transports', 'start': '2026-01-01', 'end': '2026-12-31'}))
    assert len(captured) == (0 if empty else 2)
    if empty:
        assert output['documents'] == []
    else:
        assert TEXT in captured[0]['prompt']
        assert all(not call.get('search', False) for call in captured)
        assert TEXT in captured[1]['prompt']


def test_local_refuses_invented_excerpt_in_known_url():
    invalid = report()
    invalid['documents'][0]['evidence'][0]['excerpt'] = 'Une citation inventÃ©e.'
    run = Run('Transports', '2026-01-01', '2026-12-31', source_urls={URL}, prepared=prepared())
    with patch.object(Run, 'call', AsyncMock(return_value=SimpleNamespace(output_text=json.dumps(invalid)))), \
         pytest.raises(ResearchFailure, match='sources'):
        asyncio.run(run.finish())


def test_unknown_source_mode_never_falls_back_to_paid_search(monkeypatch):
    monkeypatch.setenv('POLITICAL_DATA_SOURCE', 'typo')
    with patch('backend.pipelex_research.find_sources') as web, pytest.raises(ValueError):
        research('Transports', start='2026-01-01', end='2026-12-31')
    web.assert_not_called()
