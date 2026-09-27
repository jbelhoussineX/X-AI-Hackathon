from datetime import date
import io
import json
from unittest.mock import Mock
import zipfile

import pytest
from streamlit.testing.v1 import AppTest

from backend.data_sources.recent import assembly_events, senate_events, search_recent
from test_assembly_data import archive_bytes
from test_senate_data import csv_bytes


def archive():
    buf = io.BytesIO(archive_bytes())  # January deposit, September event.
    acts = [{'uid': str(i), 'dateActe': day, 'libelleActe': {'nomCanonique': 'Décision'},
             'statutConclusion': {'libelle': 'adopté'}} for i, day in enumerate(
                 ['2026-09-25T23:00:00+02:00', None, '2026-09-28', '2025-01-01'])]
    dossier = {'uid': 'DLR5L17N12345', '@xsi:type': 'DossierLegislatif_Type', 'legislature': '17',
               'procedureParlementaire': {'libelle': 'Proposition de loi ordinaire'},
               'titreDossier': {'titre': 'Logement fictif'},
               'actesLegislatifs': {'acteLegislatif': {'dateActe': None,
                   'actesLegislatifs': {'acteLegislatif': acts}}}}
    with zipfile.ZipFile(buf, 'a') as z:
        z.writestr('json/dossierParlementaire/DLR5L17N12345.json', json.dumps({'dossierParlementaire': dossier}))
    return buf.getvalue()


def test_old_deposit_recent_act_unknown_and_future_excluded():
    events = assembly_events(archive(), 'logement', '2026-09-21', '2026-09-27')
    assert len(events) == 1
    assert events[0]['event_date'] == '2026-09-25'
    assert events[0]['decision'] == 'adopté'
    assert 'acteLegislatif[0]' in events[0]['source_location']
    assert assembly_events(archive(), 'transports', '2026-09-21', '2026-09-27') == []


def test_senate_old_deposit_recent_promulgation():
    payload = csv_bytes(**{'Date initiale': '01/01/2020', 'Date de promulgation': '25/09/2026'})
    events = senate_events(payload, 'logement', '2026-09-21', '2026-09-27')
    assert len(events) == 1 and events[0]['event'] == 'Promulgation'
    assert events[0]['date_kind'] == 'Date de promulgation'


def test_fresh_fetch_on_every_click_partial_outage_and_inclusive_window(monkeypatch):
    monkeypatch.setattr('backend.data_sources.live_feeds.collect', lambda *a, **kw: ([], [], []))
    fetch = Mock(return_value=(archive(), {'retrieved_at': '2026-09-27T12:00:00Z', 'sha256': 'test'}))
    monkeypatch.setattr('backend.data_sources.recent.assembly.fetch_dataset', fetch)
    monkeypatch.setattr('backend.data_sources.recent.senate.fetch_dataset', Mock(side_effect=ValueError('SECRET')))
    for _ in range(2):
        result = search_recent('logement', 7, today=date(2026, 9, 27))
        assert result['start'] == '2026-09-21'
        assert result['events'][0]['retrieved_at'] == '2026-09-27T12:00:00Z'
        assert result['datasets'][1]['status'] == 'unavailable'
        assert 'SECRET' not in json.dumps(result)
    assert fetch.call_count == 2


def test_invalid_period_fails_before_network(monkeypatch):
    fetch = Mock(side_effect=AssertionError('Network forbidden'))
    monkeypatch.setattr('backend.data_sources.recent.assembly.fetch_dataset', fetch)
    with pytest.raises(ValueError):
        search_recent('logement', 365)
    fetch.assert_not_called()


def test_ui_only_collects_on_explicit_click(monkeypatch):
    result = {'topic': 'logement', 'start': '2026-09-21', 'end': '2026-09-27',
              'collected_at': '2026-09-27T12:00:00Z', 'datasets': [],
              'events': [], 'limitations': ['Test fictif.']}
    fetch = Mock(return_value=result)
    monkeypatch.setattr('frontend.recent_activity.search_recent', fetch)
    app = AppTest.from_string('from frontend.recent_activity import render\nrender()').run()
    fetch.assert_not_called()
    app.text_input(key='recent_topic').set_value('logement')
    app.radio[0].set_value(7)
    app.button[0].click().run()
    assert not app.exception
    fetch.assert_called_once_with('logement', 7)
    assert 'Aucun événement' in app.info[0].value
    app.run()
    fetch.assert_called_once()
