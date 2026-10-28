# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Concurrent reads must preserve complete snapshots and serialized writes."""
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from concurrent.futures import ThreadPoolExecutor

from campbase.deck import Deck, OfflineError
from campbase.storage import Store
from campbase.sync import SyncEngine


class ReadPerformanceTests(unittest.TestCase):
    def api(self):
        return Deck(SimpleNamespace(server='https://cloud.example.invalid', username='alice',
                                    password='dummy', goa_id='test'))

    def test_parallel_fetch_merges_active_and_archived_cards(self):
        api = self.api()
        lock = threading.Lock()
        active = peak = 0

        def request(method, path):
            nonlocal active, peak
            self.assertEqual(method, 'GET')
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(.02)
            with lock:
                active -= 1
            if path.startswith('/boards?'):
                return [] if 'archived=1' in path else [{'id': 1, 'title': 'Prova'}]
            archived = path.endswith('/archived')
            return [{'id': 10, 'cards': [{'id': 102 if archived else 101, 'order': 1 if archived else 0,
                                         'archived': archived}, {'id': 103, 'deletedAt': 1}]}]

        api.request = request
        snapshot = api.fetch(refresh_auth=False)
        self.assertGreaterEqual(peak, 2)
        self.assertLessEqual(peak, 4)
        self.assertEqual([card['id'] for card in snapshot['stacks']['1'][0]['cards']], [101, 102])

    def test_transport_is_local_to_each_thread(self):
        api = self.api()
        main = api.opener
        result = []
        worker = threading.Thread(target=lambda: result.append((api.opener, api.opener)))
        worker.start();worker.join()
        self.assertIs(result[0][0], result[0][1])
        self.assertIsNot(main, result[0][0])

    def test_parallel_activity_and_local_creations_do_not_lose_authors(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(lambda index: store.record_creator(f'card:{index}', {'uid': f'user{index}'}), range(20)))
            self.assertEqual(len(store.get('creators')), 20)

    def test_account_change_pauses_both_queues_until_old_inbox_is_drained(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = SyncEngine(Store(directory))
            engine.api = self.api()
            try:
                engine.account_changing = True
                self.assertIsNone(engine.sync())
                self.assertIsNone(engine.refresh_updates())
                engine.account_changing = False
                action = Mock()
                engine.run_updates(action).result(timeout=1)
                action.assert_called_once_with(engine.api)
            finally:
                engine.close()
                engine.executor.shutdown(wait=True)
                engine.updates_executor.shutdown(wait=True)

    def test_unavailable_feeds_cannot_hold_card_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            store.put('profile', {'account': 'test', 'checked': time.time()})
            entered, release = threading.Event(), threading.Event()
            api = self.api()
            api.refresh_auth = Mock()
            api.fetch = Mock(return_value={'boards': [], 'stacks': {}})
            api.activity = Mock(return_value=[])

            def notifications():
                entered.set()
                release.wait(5)
                return []

            api.notifications = notifications
            engine = SyncEngine(store)
            engine.api = api
            try:
                engine.sync().result(timeout=2)
                self.assertTrue(entered.wait(2))
                self.assertFalse(engine.busy)
                self.assertIsNotNone(store.get('last_sync'))
                self.assertEqual(engine.run(lambda _: 'ready', lambda *_: None).result(timeout=1), None)
                self.assertFalse(release.is_set())
            finally:
                release.set()
                engine.close()
                engine.executor.shutdown(wait=True)
                engine.updates_executor.shutdown(wait=True)

    def test_failed_parallel_read_does_not_replace_cached_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            cached = {'boards': [{'id': 1, 'title': 'Desat'}], 'stacks': {}}
            store.put('snapshot', cached)
            api = self.api()
            api.refresh_auth = Mock()

            def request(_method, path):
                if '/stacks' in path:
                    raise OfflineError('Synthetic interrupted read')
                return [{'id': 1, 'title': 'Remot'}]

            api.request = request
            engine = SyncEngine(store)
            engine.api = api
            try:
                engine.sync().result(timeout=2)
                self.assertEqual(store.get('snapshot'), cached)
                self.assertTrue(engine.error)
            finally:
                engine.close()
                engine.executor.shutdown(wait=True)
                engine.updates_executor.shutdown(wait=True)


if __name__ == '__main__':
    unittest.main()
