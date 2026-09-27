"""Unsupported contacts are omitted transparently; document validation stays strict."""
import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from src.contracts import ReportError, validate_report
from src.openai_research import Run, ResearchFailure, prepare_report
from test_official_integration import fixture_data, URL
from test_source_passages import draft_report


@pytest.mark.parametrize('references', [[], ['absent'], ['p0001'], ['DEMO-1', 'absent']])
def test_omits_entire_orphan_without_guessing_and_keeps_other_entities(references):
    report, _ = fixture_data()
    valid_contact = deepcopy(report['contacts'][0])
    report['contacts'][0]['document_ids'] = references
    report['contacts'].append(valid_contact)
    original = deepcopy(report)
    # The public contract still rejects these references.
    with pytest.raises(ReportError) as caught:
        validate_report(report)
    assert caught.value.reason == 'contact_document_reference'
    result = prepare_report(report)
    assert report == original
    assert result['documents'] == original['documents']
    assert result['contacts'] == [valid_contact]
    assert any('Interlocuteur n°1 non affiché' in text for text in result['limitations'])
    validate_report(result)


def test_no_documents_cannot_leave_a_contact_or_invent_a_document():
    report, _ = fixture_data()
    report.update(documents=[], limitations=[])
    result = prepare_report(report)
    assert result['documents'] == result['contacts'] == []
    assert result['limitations']
    validate_report(result)


@pytest.mark.parametrize('problem,reason', [('too_many', 'item_limit'), ('duplicate', 'duplicate_document_id'),
                                         ('missing_content', 'missing_content_evidence'), ('date', 'invalid_date')])
def test_orphan_omission_does_not_hide_other_contract_failures(problem, reason):
    report, _ = fixture_data()
    report['contacts'][0]['document_ids'] = ['absent']
    if problem == 'too_many':
        report['contacts'] *= 4
    elif problem == 'duplicate':
        report['documents'] *= 2
    elif problem == 'missing_content':
        report['documents'][0]['evidence'] = []
    else:
        report['documents'][0]['publication_date'] = 'invalid'
    with pytest.raises(ReportError) as caught:
        prepare_report(report)
    assert caught.value.reason == reason


@pytest.mark.parametrize('bad_document_date', [False, True])
def test_official_finish_preserves_verified_document_without_another_model_call(monkeypatch, bad_document_date):
    draft, prepared = draft_report()
    draft['contacts'][0]['document_ids'] = ['p0001']  # Passage ID, not a document ID.
    if bad_document_date:
        draft['documents'][0]['publication_date'] = '2020-01-01'
    run = Run('test', '2024-01-01', '2026-09-27', data_source='official', source_urls={URL}, prepared=prepared)
    calls = []
    async def fake(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(output_text=json.dumps(draft))
    monkeypatch.setattr(run, 'call', fake)
    if bad_document_date:
        with pytest.raises(ResearchFailure) as caught:
            asyncio.run(run.finish())
        assert caught.value.reason == 'publication_outside_period'
    else:
        result = asyncio.run(run.finish())
        assert [d['id'] for d in result['documents']] == ['DEMO-1']
        assert result['contacts'] == []
        assert any('Interlocuteur n°1 non affiché' in text for text in result['limitations'])
        assert any('1/1 extraits retrouvés' in text for text in result['limitations'])
        validate_report(result)
    assert len(calls) == 1
