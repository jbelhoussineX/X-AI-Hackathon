"""Useful label variations must not hide valid IDs; invalid evidence stays rejected."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from backend.agent_models import Selection
from backend.generated.recent_brief.models import Request
from src.pipelex_client import PipelexError, failure_message, safe_diagnostic
from src.pipelex_worker import error_diagnostic
from src.recent_agent_worker import run_stage


@pytest.mark.parametrize('payload,field,constraint', [
    ({'queries': [], 'event_ids': ['c0'] * 7}, 'event_ids', 'too_long'),
    ({'queries': [], 'event_ids': None}, 'event_ids', 'list_type'),
    ({'queries': [], 'event_ids': [{'SECRET_FIELD': 'SECRET_VALUE'}]}, 'event_ids', 'string_type'),
    ({'queries': []}, 'event_ids', 'missing'),
    ({'queries': 'SECRET_VALUE', 'event_ids': []}, 'queries', 'list_type'),
    ({'queries': ['x' * 101], 'event_ids': []}, 'queries', 'string_too_long'),
])
def test_rejected_selection_reports_only_safe_field_and_constraint(payload, field, constraint):
    with pytest.raises(ValidationError) as caught:
        Selection.model_validate(payload)
    details = error_diagnostic(caught.value)
    assert details['field'] == field
    assert details['constraint'] == constraint
    message = failure_message('format', details)
    assert f'champ={field}' in message
    assert f'contrainte={constraint}' in message
    assert 'SECRET' not in message
    assert 'x' * 101 not in message


def test_unknown_field_names_and_constraint_values_are_never_forwarded():
    with pytest.raises(ValidationError) as caught:
        Selection.model_validate({'queries': [], 'event_ids': [], 'SECRET_FIELD': 'SECRET_VALUE'})
    assert 'SECRET' not in json.dumps(error_diagnostic(caught.value))
    assert safe_diagnostic({'field': 'SECRET_FIELD', 'constraint': 'SECRET_VALUE'}) == {}


def test_label_deduplication_never_changes_document_ids():
    selected = Selection(queries=['logement', 'logement', 'IA'], event_ids=['c0', 'c1'])
    assert selected.queries == ['logement', 'IA']
    assert selected.event_ids == ['c0', 'c1']


def test_worker_output_validation_keeps_field_diagnostic_without_retry(monkeypatch):
    process = Mock(return_value=SimpleNamespace(returncode=0, stdout=json.dumps({
        'ok': True, 'output': {'queries': [], 'event_ids': None},
    }), stderr='SECRET_LOG'))
    monkeypatch.setattr('src.recent_agent_worker.subprocess.run', process)
    with pytest.raises(PipelexError) as caught:
        run_stage('select', Request(topic='logement', corpus_json='{}'))
    assert 'champ=event_ids' in str(caught.value)
    assert 'contrainte=list_type' in str(caught.value)
    assert 'SECRET' not in str(caught.value)
    process.assert_called_once()
