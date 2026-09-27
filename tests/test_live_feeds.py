import httpx
import pytest

from backend.data_sources.live_feeds import (
    collect, rss_events, publication_rows, amendment_event, xml_root, official_link,
)

URL = 'https://www.assemblee-nationale.fr/dyn/opendata/AMANR5L17PO123B456P0D1N000001.xml'
RSS = b'''<?xml version="1.0" encoding="ISO-8859-15"?><rss><channel><item>
<title>Logement \xe9tudiant</title><description>Texte ancien</description>
<pubDate>Fri,25 Sep 2026 01:03:34 GMT</pubDate>
<link>http://www.senat.fr/leg/ppl25-123.html</link></item></channel></rss>'''
XML = b'''<amendement xmlns="http://schemas.assemblee-nationale.fr/referentiel">
<uid>AMANR5L17PO123B456P0D1N000001</uid><legislature>17</legislature>
<identification><numeroLong>CD1</numeroLong></identification>
<corps><contenuAuteur><exposeSommaire>&lt;p&gt;Le logement des familles&lt;/p&gt;</exposeSommaire></contenuAuteur></corps>
</amendement>'''


def test_rss_encoding_date_semantics_and_whitelist():
    events = rss_events(RSS, 'logement', '2026-09-21', '2026-09-27', 'https://www.senat.fr/rss/textes.rss')
    assert events[0]['title'] == 'Logement étudiant'
    assert events[0]['event_date'] == '2026-09-25'
    assert 'pas date de dépôt' in events[0]['date_kind']
    assert events[0]['dossier_url'].startswith('https:')
    assert rss_events(RSS, 'santé', '2026-09-21', '2026-09-27', 'feed') == []
    bad = RSS.replace(b'www.senat.fr/leg', b'www.senat.fr.evil.test/leg')
    assert rss_events(bad, 'logement', '2026-09-21', '2026-09-27', 'feed') == []


@pytest.mark.parametrize('payload', [b'<!DOCTYPE a [<!ENTITY x "abc">]><a>&x;</a>', b'\x00<rss/>', b'<broken'])
def test_unsafe_or_invalid_xml_is_refused(payload):
    with pytest.raises(ValueError):
        xml_root(payload)


def test_amendment_publication_is_not_adoption_and_matching_reads_body():
    payload = f'2026-09-26 12:00:00;{URL}\n2026-09-26 12:00:00;{URL[:-3]}pdf\n'.encode()
    rows = publication_rows(payload, '2026-09-26')
    assert len(rows) == 1
    event = amendment_event(XML, 'logement', rows[0][0], URL, 'list', 1)
    assert event['decision'] is None
    assert 'pas adoption' in event['date_kind']
    assert amendment_event(XML, 'santé', rows[0][0], URL, 'list', 1) is None


def test_feeds_are_bounded_deduplicated_and_do_not_follow_redirects():
    calls = []
    def handler(request):
        url = str(request.url)
        calls.append(url)
        if url.endswith('.rss'):
            return httpx.Response(200, content=RSS)
        if 'publication_2026-09-26' in url:
            return httpx.Response(200, text=f'2026-09-26 12:00:00;{URL}\n2026-09-26 13:00:00;{URL}')
        if 'publication_' in url:
            return httpx.Response(302, headers={'location': 'https://evil.test'})
        return httpx.Response(200, content=XML)
    events, sources, limits = collect('logement', '2026-09-21', '2026-09-27', transport=httpx.MockTransport(handler))
    assert calls.count(URL) == 1
    assert not any('evil' in url for url in calls)
    assert any(s['status'] == 'unavailable' for s in sources)
    amended = [e for e in events if e['provider'] == 'assemblee-publications']
    assert len(amended) == 1 and amended[0]['published_at'].endswith('13:00:00')
    assert 'detail_sha256' in amended[0]


def test_bad_host_and_payload_size_rejected():
    with pytest.raises(ValueError):
        official_link('http://www.senat.fr@evil.test/a', 'www.senat.fr')
    with pytest.raises(ValueError):
        xml_root(b'x' * 2_000_001)
