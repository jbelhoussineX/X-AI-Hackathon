"""Quotes are selected, not rewritten; verification and the public contract remain strict."""
import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace

from jsonschema import Draft202012Validator
import pytest

from backend.data_sources.official import fetched_corpus
from backend.source_verification import normalize, verify_sources
from src.contracts import SCHEMA, validate_report
from src.openai_research import Run, ResearchFailure, report_response_schema
from src.source_passages import passages_from_corpus, resolve_passages, selection_schema
from test_official_integration import fixture_data, URL


def draft_report():
    report, prepared = fixture_data()
    for item in report['documents'] + report['contacts']:
        item['evidence'] = [{'purpose': proof['purpose'], 'passage_id': 'p0001'} for proof in item['evidence']]
    return report, prepared


def test_passages_preserve_all_collected_characters_and_pdf_page_boundaries():
    _, prepared = fixture_data()
    source = prepared['corpus'][0]
    text = 'L’article 1er\u00a0: un montant de 123 € — adopté.\n' * 40
    source.update(text='', pdf_pages=[text, 'Autre page.\tFin.', '', 'X' * 1201])
    passages = passages_from_corpus([source])
    assert all(0 < len(p['excerpt']) <= 600 for p in passages.values())
    for number, original in enumerate(source['pdf_pages'], 1):
        chunks = [p['excerpt'] for p in passages.values() if p['location'] == f'Page {number} (couche texte PDF)']
        separator = '' if number == 4 else ' '
        assert separator.join(chunks) == normalize(original)
    report, _ = draft_report()
    report['contacts'] = []
    report['documents'][0]['evidence'] = [{'purpose': 'contenu', 'passage_id': key} for key in passages]
    hydrated = resolve_passages(report, passages)
    assert verify_sources(hydrated, fetched_sources=fetched_corpus([source])).all_matched


def test_schema_and_resolver_keep_public_contract_and_trusted_url():
    report, prepared = draft_report()
    original = deepcopy(report)
    original_schema = deepcopy(SCHEMA)
    passages = passages_from_corpus(prepared['corpus'])
    schema = selection_schema(report_response_schema(), passages)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(report)
    hydrated = resolve_passages(report, passages)
    validate_report(hydrated)
    assert report == original
    assert SCHEMA == original_schema
    proof = hydrated['documents'][0]['evidence'][0]
    assert proof['excerpt'] == prepared['corpus'][0]['text']
    assert proof['url'] == URL
    assert proof['location'] is None
    assert 'passage_id' not in proof
    assert verify_sources(hydrated, fetched_sources=fetched_corpus(prepared['corpus'])).all_matched


@pytest.mark.parametrize('invalid', ['unknown_id', 'rewritten_quote', 'different_url'])
def test_draft_cannot_inject_quotes_or_sources_and_failure_is_safe(monkeypatch, invalid):
    report, prepared = draft_report()
    proof = report['documents'][0]['evidence'][0]
    if invalid == 'unknown_id':
        proof['passage_id'] = 'SECRET_UNKNOWN'
    elif invalid == 'rewritten_quote':
        proof['excerpt'] = 'SECRET_REWRITTEN'
    else:
        proof['url'] = 'https://www.senat.fr/SECRET_OTHER'
    run = Run('test', '2024-01-01', '2026-09-27', data_source='official', source_urls={URL}, prepared=prepared)
    calls = []
    async def fake(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(output_text=json.dumps(report))
    monkeypatch.setattr(run, 'call', fake)
    with pytest.raises(ResearchFailure) as caught:
        asyncio.run(run.finish())
    assert caught.value.reason == 'invalid_evidence_selection'
    from src.pipelex_worker import error_diagnostic
    from src.pipelex_client import failure_message
    diagnostic = error_diagnostic(caught.value)
    assert diagnostic['reason'] == 'invalid_evidence_selection'
    assert 'SECRET' not in failure_message(caught.value.code, diagnostic)
    assert len(calls) == 1


def test_verifier_still_rejects_rephrasing_wrong_page_and_wrong_source():
    report, prepared = fixture_data()
    original_excerpt = report['documents'][0]['evidence'][0]['excerpt']
    report['documents'][0]['evidence'][0]['excerpt'] = 'Reformulation absente du texte officiel.'
    assert not verify_sources(report, fetched_sources=fetched_corpus(prepared['corpus'])).all_matched
    report['documents'][0]['evidence'][0]['excerpt'] = original_excerpt
    report['documents'][0]['evidence'][0]['url'] = 'https://www.senat.fr/une-autre-page'
    assert not verify_sources(report, fetched_sources=fetched_corpus(prepared['corpus'])).all_matched
    report['documents'][0]['evidence'][0].update(url=URL, excerpt='fin début')
    prepared['corpus'][0].update(text='', pdf_pages=['fin', 'début'])
    assert not verify_sources(report, fetched_sources=fetched_corpus(prepared['corpus'])).all_matched


def test_uncollected_titles_and_omitted_text_never_become_passages():
    _, prepared = fixture_data()
    prepared['records'] = [{'title': 'ONLY_IN_METADATA'}]
    prepared['corpus'][0].update(text='Texte collecté.', truncated=True, title='ONLY_IN_METADATA')
    passages = passages_from_corpus(prepared['corpus'])
    assert list(passages.values()) == [{'url': URL, 'excerpt': 'Texte collecté.', 'location': None}]
    assert passages_from_corpus([]) == {}
    with pytest.raises(ValueError):
        selection_schema(report_response_schema(), {})
