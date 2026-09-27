import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.refresh import refresh_demo
from backend.storage import Store


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'watch.sqlite3'
        self.store = Store(self.path)
        self.watch = self.store.add_watch('Transports')

    def refresh(self, scenario='Version du 10 octobre'):
        return refresh_demo(self.store, self.watch, scenario)

    def test_persistence_and_version_deduplication(self):
        self.refresh()
        self.refresh()
        restored = Store(self.path)
        self.assertEqual(restored.documents(self.watch)[0]['report']['change_type'], 'unchanged')
        self.assertEqual(len(restored.runs(self.watch)), 2)
        with restored.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM versions').fetchone()[0], 1)

    def test_modification_then_failure_preserves_previous_version(self):
        self.refresh()
        self.refresh('Version du 20 octobre')
        document = self.store.documents(self.watch)[0]
        self.assertEqual(document['report']['change_type'], 'modified')
        self.refresh('Source indisponible')
        after = self.store.documents(self.watch)[0]
        self.assertEqual(after['snapshot'], document['snapshot'])
        self.assertEqual(after['report']['change_type'], 'unconfirmed')
        self.assertEqual(self.store.runs(self.watch)[0]['status'], 'partial')

    def test_provider_failure_records_failure_without_replacing_data(self):
        self.refresh()
        before = self.store.documents(self.watch)
        with patch('backend.demo.analyze', side_effect=RuntimeError('secret must not be stored')):
            with self.assertRaises(RuntimeError):
                self.refresh('Version du 20 octobre')
        self.assertEqual(self.store.documents(self.watch), before)
        run = self.store.runs(self.watch)[0]
        self.assertEqual(run['status'], 'failed')
        self.assertNotIn('secret', run['detail'])

    def test_concurrent_refresh_refused(self):
        self.store.begin(self.watch)
        with self.assertRaises(ValueError):
            Store(self.path).begin(self.watch)

    def test_failed_finish_rolls_back_documents_and_results(self):
        self.refresh()
        before = self.store.documents(self.watch)
        run = self.store.begin(self.watch)
        item = dict(before[0])
        item['title'] = 'Should be rolled back'
        with self.assertRaises(Exception):
            self.store.finish(run, [item, item], {})  # Duplicate result breaks the transaction.
        self.assertEqual(self.store.documents(self.watch), before)
        self.store.fail(run, 'transaction refused')

    def test_demo_cannot_mutate_live_watch(self):
        live = self.store.add_watch('Transports', 'live')
        with self.assertRaises(ValueError):
            refresh_demo(self.store, live, 'Version du 10 octobre')
        self.assertEqual(self.store.documents(live), [])

    def test_empty_topic_and_duplicate_watch(self):
        with self.assertRaises(ValueError):
            self.store.add_watch('   ')
        self.assertEqual(self.store.add_watch('Transports'), self.watch)

    def test_first_failed_retrieval_has_no_snapshot(self):
        self.refresh('Source indisponible')
        self.assertIsNone(self.store.documents(self.watch)[0]['snapshot'])
        self.refresh()
        self.assertEqual(self.store.documents(self.watch)[0]['report']['change_type'], 'new_document')
