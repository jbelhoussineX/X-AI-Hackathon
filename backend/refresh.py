"""Manual refresh orchestration, with injected providers and atomic persistence."""
from backend.comparison_service import compare_for_refresh
from backend.storage import source_id
from backend import demo


def refresh_demo(store, watch_id, scenario):
    watch = store.watch(watch_id)
    if watch['mode'] != 'demo':
        raise ValueError('La simulation nécessite une veille de démonstration.')
    if scenario not in ('Version du 10 octobre', 'Version du 20 octobre', 'Source indisponible'):
        raise ValueError('Scénario inconnu.')
    run_id = store.begin(watch_id)
    try:
        previous = next((d['snapshot'] for d in store.documents(watch_id) if d['url'] == demo.URL), None)
        current = demo.snapshot('20' if scenario == 'Version du 20 octobre' else '10',
                                scenario == 'Source indisponible')
        request = {'document_id': source_id(demo.URL), 'watch_topic': watch['topic'],
                   'previous': previous, 'current': current}
        result = compare_for_refresh(request, demo.analyze)
        store.finish(run_id, [{'id': request['document_id'], 'url': demo.URL,
                              'title': 'Consultation fictive sur les transports',
                              'snapshot': result.snapshot_to_store, 'report': result.report,
                              'context': {'mode': 'demo'}}], {'mode': 'demo'})
        return run_id
    except Exception:
        store.fail(run_id, 'Échec de la simulation ; versions précédentes conservées.')
        raise
