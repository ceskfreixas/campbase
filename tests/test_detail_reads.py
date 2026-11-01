# SPDX-License-Identifier: GPL-3.0-or-later
"""Foreground reads must be bounded, cancellable and independent of card writes."""
from queue import Queue
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from campbase.detail_reads import DetailCache, DetailReads
from campbase.deck import Deck
from campbase.storage import Store
from campbase.sync import SyncEngine


class DetailReadTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.engine = SyncEngine(Store(self.folder.name))
        self.engine.api = Mock()
        self.release = threading.Event()

    def tearDown(self):
        self.release.set()
        self.engine.close()
        self.engine.executor.shutdown(wait=True)
        self.engine.read_executor.shutdown(wait=True)
        self.engine.updates_executor.shutdown(wait=True)
        self.folder.cleanup()

    def test_two_reads_complete_while_card_worker_is_blocked(self):
        blocked = threading.Event()
        def write_queue():
            blocked.set();self.release.wait(3)
        hold = self.engine.executor.submit(write_queue)
        self.assertTrue(blocked.wait(1))
        entered = [threading.Event(), threading.Event()]
        results = Queue()
        def read(index):
            entered[index].set()
            self.assertTrue(entered[1-index].wait(1))
            return index
        requests = [self.engine.run_read(lambda _, i=i: read(i), lambda result, error: results.put((result,error))) for i in range(2)]
        for request in requests:request.result(timeout=2)
        self.assertEqual({results.get_nowait(),results.get_nowait()}, {(0,None),(1,None)})
        self.assertFalse(hold.done())

    def test_limit_two_and_cancel_queued_closed_scope(self):
        entered = [threading.Event(), threading.Event()]
        def read(index):
            entered[index].set();self.release.wait(3)
        running = [self.engine.run_read(lambda _, i=i: read(i), lambda *_: None) for i in range(2)]
        self.assertTrue(all(event.wait(1) for event in entered))
        action = Mock()
        scope = DetailReads(self.engine)
        queued = scope.run(action, Mock())
        scope.close()
        self.assertTrue(queued.cancelled())
        action.assert_not_called()
        self.release.set()
        for request in running:request.result(timeout=1)

    def test_stale_refresh_closed_view_and_switched_account_drop_deliveries(self):
        callbacks = Queue()
        self.engine.dispatch = lambda fn,*args: callbacks.put((fn,args))
        scope = DetailReads(self.engine)
        done = Mock()
        scope.run(lambda _: 'old',done).result(timeout=1)
        scope.invalidate()
        callback,args = callbacks.get_nowait();callback(*args)
        done.assert_not_called()
        scope.run(lambda _: 'other account',done).result(timeout=1)
        self.engine.api = Mock()
        callback,args = callbacks.get_nowait();callback(*args)
        done.assert_not_called()

    def test_reads_do_not_block_serialized_writes(self):
        entered = threading.Event()
        def read(_):
            entered.set();self.release.wait(3)
        active = self.engine.run_read(read,lambda *_:None)
        self.assertTrue(entered.wait(1))
        calls = []
        writes = [self.engine.run(lambda _, i=i: calls.append(i),None) for i in range(3)]
        for write in writes:write.result(timeout=1)
        self.assertEqual(calls,[0,1,2])
        self.assertFalse(active.done())

    def test_account_transition_does_not_start_reads(self):
        self.engine.account_changing = True
        action = Mock()
        self.assertIsNone(self.engine.run_read(action,Mock()))
        action.assert_not_called()

    def test_cancelled_notification_lookup_stops_requesting_older_pages(self):
        api = Deck.__new__(Deck)
        rows = [{'id': str(index)} for index in range(50)]
        api.comments = Mock(return_value=rows)
        keep_reading = Mock(side_effect=[True,False])
        result = api.comments_for_update(1,{'comment_id':'999'},keep_reading=keep_reading)
        self.assertEqual(result,rows)
        api.comments.assert_called_once_with(1,0)

    def test_scope_can_retry_after_startup_account_becomes_available(self):
        self.engine.api = None
        scope = DetailReads(self.engine)
        self.engine.api = Mock()
        result = []
        scope.run(lambda _: 'ready',lambda value,error:result.append((value,error))).result(timeout=1)
        self.assertEqual(result,[('ready',None)])
        self.assertIs(scope.api,self.engine.api)
        self.engine.api = Mock()
        scope.bind()
        self.assertFalse(scope.current())

    def test_preview_cache_is_bounded_private_expiring_and_not_shared(self):
        cache = DetailCache(capacity=2,lifetime=10)
        api, other = Mock(),Mock()
        with patch('campbase.detail_reads.time.monotonic',return_value=1):
            for index in range(3):cache.put(api,('comments',index),[{'message':str(index)}])
        self.assertEqual(len(cache.items),2)
        self.assertIsNone(cache.get(api,('comments',0)))
        with patch('campbase.detail_reads.time.monotonic',return_value=2):
            value = cache.get(api,('comments',2));value[0]['message']='Changed outside cache'
            self.assertEqual(cache.get(api,('comments',2)),[{'message':'2'}])
        with patch('campbase.detail_reads.time.monotonic',return_value=12):
            self.assertIsNone(cache.get(api,('comments',2)))
        cache.put(api,('comments',1),['Saved'])
        self.assertIsNone(cache.get(other,('comments',1)))
        cache.put(other,('comments',1),['x'*(257*1024)])
        self.assertIsNone(cache.get(other,('comments',1)))
        cache.put(other,('comments',1),['Saved'])
        self.assertIsNone(cache.get(None,('comments',1)))
        cache.put(api,('comments',1),['Saved'])
        cache.discard(api,('comments',1))
        self.assertIsNone(cache.get(api,('comments',1)))
