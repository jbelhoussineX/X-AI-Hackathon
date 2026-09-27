"""Multiple explicit topics are combined with OR using shared official inventories."""

from datetime import date
import io
import json
from unittest.mock import Mock
import zipfile

import pytest

from backend.data_sources import recent
from test_assembly_data import archive_bytes
from test_senate_data import csv_bytes


TODAY = date(2026, 9, 27)


def assembly_archive():
    out = io.BytesIO(archive_bytes())
    with zipfile.ZipFile(out, 'a') as archive:
        for number, title, day in (
                (10, 'Projet fictif logement', '2026-09-25'),
                (11, 'Projet fictif travail', '2026-09-26'),
                (12, 'Projet fictif logement travail', '2026-09-24'),
                (13, 'Projet fictif énergie', '2026-09-24'),
                (14, 'Projet fictif logement ancien', '2026-08-31'),
                (15, 'Projet fictif travail futur', '2026-09-28')):
            uid = f'DLR5L17N{number}'
            dossier = {
                'uid': uid, '@xsi:type': 'DossierLegislatif_Type', 'legislature': '17',
                'procedureParlementaire': {'libelle': 'Projet de loi ordinaire'},
                'titreDossier': {'titre': title},
                'actesLegislatifs': {'acteLegislatif': {
                    'uid': f'act-{number}', 'dateActe': day,
                    'libelleActe': {'nomCanonique': 'Examen en commission'},
                }},
            }
            archive.writestr(f'json/dossierParlementaire/{uid}.json',
                             json.dumps({'dossierParlementaire': dossier}))
    return out.getvalue()


def senate_csv():
    result = csv_bytes(**{'Titre': 'Texte fictif logement', 'Thèmes': 'Logement',
                          'Date initiale': '25/09/2026'})
    for name, title, themes in (
            ('travail', 'Texte fictif travail', 'Travail'),
            ('both', 'Texte fictif logement travail', 'Logement, Travail'),
            ('other', 'Texte fictif énergie', 'Énergie')):
        payload = csv_bytes(**{
            'Titre': title, 'Thèmes': themes, 'Date initiale': '26/09/2026',
            'URL du dossier': f'http://www.senat.fr/dossier-legislatif/{name}.html'})
        result += payload.splitlines(keepends=True)[1]
    return result


def event(event_id='feed:shared', *, day='2026-09-25', text='Une étape', **overrides):
    return {
        'id': event_id, 'title': 'Titre fictif', 'event_date': day, 'event': text,
        'decision': None, 'provider': 'senat-rss', 'date_kind': 'publication',
        'source_url': 'https://www.senat.fr/rss/textes.rss',
        'source_location': 'item test', 'dossier_url': 'https://www.senat.fr/test.html',
        'retrieved_at': '2026-09-27T12:00:00Z', 'dataset_sha256': 'original-content',
        **overrides,
    }


@pytest.fixture
def offline(monkeypatch):
    an_meta = {'retrieved_at': '2026-09-27T12:00:00Z', 'sha256': 'archive-hash',
               'source_url': recent.assembly.DATASET_URL}
    senate_meta = {'retrieved_at': '2026-09-27T12:01:00Z', 'sha256': 'csv-hash',
                   'source_url': recent.senate.DATASET_URL}
    calls = {
        'assembly': Mock(return_value=(assembly_archive(), an_meta)),
        'senate': Mock(return_value=(senate_csv(), senate_meta)),
        'feeds': Mock(return_value=([], [], [])),
        'debates': Mock(return_value=([], [], [])),
    }
    monkeypatch.setattr(recent.assembly, 'fetch_dataset', calls['assembly'])
    monkeypatch.setattr(recent.senate, 'fetch_dataset', calls['senate'])
    monkeypatch.setattr('backend.data_sources.live_feeds.collect', calls['feeds'])
    monkeypatch.setattr('backend.data_sources.debates.collect', calls['debates'])
    return calls


@pytest.mark.parametrize('topics', [
    [], ['logement'] * 9, 'logement', None, (),
    ['logement', 1], ['logement', None], ['logement', ''],
    ['lo'], ['a' * 101], ['???'], ['les et'], ['logement\ntravail'],
])
def test_invalid_topics_fail_before_any_download(offline, topics):
    with pytest.raises(ValueError):
        recent.search_topics(topics, today=TODAY)
    for call in offline.values():
        call.assert_not_called()


@pytest.mark.parametrize('period', [
    {'days': 0}, {'days': 91}, {'days': True}, {'days': '3'},
    {'months': 0}, {'months': 13}, {'months': True}, {'months': 1.5},
])
def test_invalid_period_fails_before_any_download(offline, period):
    with pytest.raises(ValueError):
        recent.search_topics(['logement', 'travail'], today=TODAY, **period)
    for call in offline.values():
        call.assert_not_called()


def test_distinct_topics_are_or_not_concatenated_and_inventories_parsed_once(offline, monkeypatch):
    parse_an = Mock(wraps=recent.assembly.parse_archive)
    parse_senate = Mock(wraps=recent.senate.parse_csv)
    monkeypatch.setattr(recent.assembly, 'parse_archive', parse_an)
    monkeypatch.setattr(recent.senate, 'parse_csv', parse_senate)
    result = recent.search_topics(['logement', 'travail'], 7, today=TODAY)
    titles = {item['title'] for item in result['events']}
    assert titles == {
        'Projet fictif logement', 'Projet fictif travail', 'Projet fictif logement travail',
        'Texte fictif logement', 'Texte fictif travail', 'Texte fictif logement travail',
    }
    assert result['total_events'] == 6
    assert result['topic'] == 'logement · travail'
    assert result['topics'] == ['logement', 'travail']
    assert result['start'] == '2026-09-21' and result['end'] == '2026-09-27'
    for provider in ('assembly', 'senate'):
        offline[provider].assert_called_once_with(transport=None)
    parse_an.assert_called_once()
    parse_senate.assert_called_once()
    for provider in ('feeds', 'debates'):
        assert [call.args for call in offline[provider].call_args_list] == [
            ('logement', '2026-09-21', '2026-09-27'),
            ('travail', '2026-09-21', '2026-09-27')]
    for item in result['events']:
        assert item['source_location']
        assert item['dataset_sha256'] in ('archive-hash', 'csv-hash')
        assert item['retrieved_at'].startswith('2026-09-27T12:0')
    assert result['events'] == sorted(
        result['events'], key=lambda item: (item['event_date'], item['id']), reverse=True)
    assert any('plusieurs fois' in limitation for limitation in result['limitations'])


def test_each_multiword_topic_keeps_its_own_lexical_requirements(offline):
    result = recent.search_topics(['logement travail', 'énergie'], 7, today=TODAY)
    assert {item['title'] for item in result['events']} == {
        'Projet fictif logement travail', 'Texte fictif logement travail',
        'Projet fictif énergie', 'Texte fictif énergie'}


def test_repeated_topic_is_normalized_without_duplicate_source_calls(offline):
    result = recent.search_topics([' Logement ', 'logement', 'Travail'], 7, today=TODAY)
    assert result['topics'] == ['Logement', 'Travail']
    assert result['topic'] == 'Logement · Travail'
    assert offline['feeds'].call_count == offline['debates'].call_count == 2
    assert result['total_events'] == 6


@pytest.mark.parametrize(('today', 'months', 'start'), [
    (date(2026, 9, 27), 2, '2026-07-27'),
    (date(2026, 3, 31), 1, '2026-02-28'),
    (date(2024, 3, 31), 1, '2024-02-29'),
])
def test_all_topics_share_same_calendar_window_and_transport(offline, today, months, start):
    transport = object()
    result = recent.search_topics(['logement', 'travail'], months=months, today=today, transport=transport)
    assert result['start'] == start
    assert result['end'] == today.isoformat()
    for key in ('assembly', 'senate'):
        offline[key].assert_called_once_with(transport=transport)
    for key in ('feeds', 'debates'):
        for call in offline[key].call_args_list:
            assert call.args[1:] == (start, today.isoformat())
            assert call.kwargs == {'transport': transport}


def test_exact_duplicates_removed_but_different_versions_and_steps_preserved(offline):
    first = event()
    repeated = dict(first, retrieved_at='2026-09-27T12:05:00Z')
    new_version = dict(first, dataset_sha256='updated-content')
    different_passage = dict(first, content_passages=['Autre passage exact de la même séance.'])
    second_step = event(text='Nouvelle étape de procédure')
    second_date = event(day='2026-09-26')
    metadata = {'provider': 'senat-rss', 'source_url': first['source_url'],
                'sha256': 'feed-hash', 'status': 'ok', 'retrieved_at': first['retrieved_at']}
    offline['feeds'].side_effect = [
        ([first, second_step], [metadata], ['Limite de flux.']),
        ([repeated, new_version, different_passage, second_date],
         [dict(metadata, retrieved_at=repeated['retrieved_at'])], ['Limite de flux.']),
    ]
    result = recent.search_topics(['logement', 'travail'], 7, today=TODAY)
    added = [item for item in result['events'] if item['id'] == first['id']]
    assert len(added) == 5
    assert sum(item['dataset_sha256'] == 'updated-content' for item in added) == 1
    assert sum(item['event'] == 'Nouvelle étape de procédure' for item in added) == 1
    assert len([source for source in result['datasets'] if source['provider'] == 'senat-rss']) == 1
    assert result['limitations'].count('Limite de flux.') == 1


def test_inventory_and_one_topic_feed_failures_keep_other_results_without_retry(offline):
    offline['assembly'].side_effect = ValueError('DO NOT EXPOSE INTERNAL ERROR')
    extra = event('feed:only-travail')
    offline['feeds'].side_effect = [RuntimeError('DO NOT EXPOSE INTERNAL ERROR'), ([extra], [], [])]
    result = recent.search_topics(['logement', 'travail'], 7, today=TODAY)
    assert result['total_events'] == 4
    assert any(item['id'] == extra['id'] for item in result['events'])
    assert all(item['provider'] != 'assemblee' for item in result['events'])
    assert [source['status'] for source in result['datasets'][:2]] == ['unavailable', 'ok']
    assert any(source.get('topic') == 'logement' for source in result['datasets'])
    assert 'DO NOT EXPOSE INTERNAL ERROR' not in json.dumps(result)
    offline['assembly'].assert_called_once()
    assert offline['feeds'].call_count == offline['debates'].call_count == 2


def test_limit_applies_after_union_and_deduplication(offline):
    added = [event(f'feed:{index:02d}', day='2026-09-27') for index in range(30)]
    offline['feeds'].side_effect = [([*added[:20]], [], []), ([*added[10:]], [], [])]
    result = recent.search_topics(['logement', 'travail'], 7, today=TODAY)
    assert len(result['events']) == 20
    assert result['total_events'] == 36
    assert all(item['event_date'] == '2026-09-27' for item in result['events'])
    assert any('20 événements les plus récents sur 36' in text for text in result['limitations'])


def test_one_topic_keeps_legacy_search_shape_and_result(offline):
    multi = recent.search_topics(['logement'], 7, today=TODAY)
    legacy = recent.search_recent('logement', 7, today=TODAY)
    assert 'topics' not in legacy
    assert multi['topics'] == ['logement']
    for key in ('topic', 'start', 'end', 'events', 'total_events', 'datasets', 'limitations'):
        assert multi[key] == legacy[key]
    assert offline['assembly'].call_count == offline['senate'].call_count == 2


def test_single_subject_legacy_still_accepts_longer_queries(offline):
    topic = 'logement ' + 'abc ' * 28
    assert 100 < len(topic) < 300
    result = recent.search_recent(topic, today=TODAY)
    assert result['topic'] == topic.strip()
    assert result['events'] == []
