# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Confirmed comment counts preserve queued card edits and assignment data."""
import tempfile
import unittest
import queue
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch
from campbase.storage import Store
from campbase.deck import Deck
from campbase.comment_count_loader import CommentCountLoader
from campbase.sync import SyncEngine


class CommentCountTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = Store(directory.name)
        self.card = {'id': 99, 'stackId': 10, 'title': 'Original', 'commentsCount': 3,
                     'assignedUsers': [{'participant': {'uid': 'alice'}}]}
        self.store.put('snapshot', {'boards': [{'id': 1}],
                                   'stacks': {'1': [{'id': 10, 'cards': [self.card]}]}})

    def test_count_updates_preserve_inflight_changes_and_assignees(self):
        operation = self.store.enqueue('update', {'board_id': 1, 'card_id': 99, 'stack_id': 10,
                                                 'changes': {'title': 'Local draft'}})
        for delta, expected in ((1, 4), (-1, 3), (-10, 0)):
            self.store.comment_count(1, 99, delta=delta)
            card = self.store.view()['stacks']['1'][0]['cards'][0]
            self.assertEqual(card['commentsCount'], expected)
            self.assertEqual(card['title'], 'Local draft')
            self.assertEqual(card['assignedUsers'], self.card['assignedUsers'])
            self.assertEqual(self.store.operations()[0]['id'], operation)

    def test_unknown_count_is_not_invented_from_a_delta(self):
        self.card.pop('commentsCount')
        self.store.put('snapshot', {'stacks': {'1': [{'id': 10, 'cards': [self.card]}]}})
        self.store.comment_count(1, 99, delta=1)
        self.assertNotIn('commentsCount', self.store.view()['stacks']['1'][0]['cards'][0])
        self.store.comment_count(1, 99, count=7)
        self.assertEqual(self.store.view()['stacks']['1'][0]['cards'][0]['commentsCount'], 7)

    def test_reactions_do_not_change_the_visible_comment_count(self):
        self.store.comment_count(1, 99, count=3, text_count=2)
        for delta in (1, -1):
            self.store.comment_count(1, 99, delta=delta, reaction_delta=delta)
            self.assertEqual(self.store.view()['stacks']['1'][0]['cards'][0]['_textCommentsCount'], 2)
        self.store.comment_count(1, 99, delta=1)
        self.assertEqual(self.store.view()['stacks']['1'][0]['cards'][0]['_textCommentsCount'], 3)
        with patch.object(self.store, 'connect', wraps=self.store.connect) as connect:
            self.store.view()
            self.assertEqual(connect.call_count, 1)

    def test_stale_background_total_cannot_replace_a_newer_count(self):
        self.store.comment_count(1, 99, count=4, text_count=3)
        self.assertFalse(self.store.comment_summary(1, 99, 3, 1, None))
        self.assertEqual(self.store.view()['stacks']['1'][0]['cards'][0]['_textCommentsCount'], 3)

    def test_count_pagination_uses_large_pages_and_rejects_inconsistent_reads(self):
        api = Deck(SimpleNamespace(server='https://cloud.example.invalid', username='alice', password='dummy'))
        rows = [{'id': key, 'message': 'Comment'} for key in range(300)]
        rows[-1].update(message='👍 @bob', actorId='alice', replyTo={'id': 999, 'actorId': 'bob'})
        api.comments = Mock(side_effect=lambda _id, offset, limit: rows[offset:offset+limit])
        self.assertEqual(api.comment_summary(99, 300), 299)
        self.assertEqual(api.comments.call_count, 2)
        self.assertTrue(all(call.kwargs['limit'] == 200 for call in api.comments.call_args_list))
        self.assertIsNone(api.comment_summary(99, 301))
        api.comments.reset_mock()
        self.assertIsNone(api.comment_summary(99, 300, keep_reading=lambda: False))
        api.comments.assert_not_called()


class BackgroundCountTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        self.store = Store(directory.name)
        self.cards = [{'id': key, 'stackId': 10, 'commentsCount': 3, 'lastModified': 1} for key in range(1, 9)]
        self.snapshot = {'boards': [{'id': 1}], 'stacks': {'1': [{'id': 10, 'cards': self.cards}]}}
        self.store.put('snapshot', self.snapshot)
        self.release = threading.Event();self.started = threading.Event();self.calls = []
        self.callbacks = queue.Queue()
        def summary(card_id, total, keep_reading):
            self.calls.append(card_id);self.started.set();self.release.wait(5)
            return 2 if keep_reading() else None
        self.api = SimpleNamespace(server='https://cloud.example.invalid', username='alice',
                                   comment_summary=summary, refresh_auth=Mock())
        self.engine = SyncEngine(self.store, dispatch=lambda fn,*args:self.callbacks.put((fn,args)))
        self.engine.api = self.api
        self.window = SimpleNamespace(engine=self.engine,store=self.store,demo=False,board_id=1,
                                      query='',only_mine=False,matching_cards=lambda stack:stack['cards'])
        self.loader = CommentCountLoader(self.window)
        def cleanup():
            self.release.set();self.loader.close();self.loader.executor.shutdown(wait=True)
            self.engine.close();self.engine.executor.shutdown(wait=True)
        self.addCleanup(cleanup)

    def flush(self):
        while not self.callbacks.empty():
            fn,args=self.callbacks.get();fn(*args)

    def test_bounded_reads_coalesce_and_moves_do_not_recount(self):
        for _ in range(20):self.loader.refresh(self.snapshot,1)
        self.assertTrue(self.started.wait(1));self.assertLessEqual(len(self.calls),2)
        self.assertEqual(len(self.loader.pending),2)
        action_done=threading.Event()
        self.engine.run(lambda _api:action_done.set(),lambda *_:None).result(timeout=1)
        self.assertTrue(action_done.is_set())
        self.release.set();deadline=time.monotonic()+3
        while len(self.store.get('comment_counts',{}))<8 and time.monotonic()<deadline:
            self.flush();self.loader.refresh(self.snapshot,1);time.sleep(.01)
        self.assertEqual(len(self.calls),8)
        for card in self.cards:card['lastModified']=50
        for _ in range(20):self.loader.refresh(self.snapshot,1)
        self.assertEqual(len(self.calls),8)
        self.assertTrue(all(card['_textCommentsCount']==2 for card in self.store.view()['stacks']['1'][0]['cards']))

    def test_account_switch_drops_old_results(self):
        self.loader.refresh(self.snapshot,1);self.assertTrue(self.started.wait(1))
        self.engine.api=SimpleNamespace(server=self.api.server,username='bob')
        self.release.set();self.loader.executor.shutdown(wait=True);self.flush()
        self.assertEqual(self.store.get('comment_counts',{}),{})

    def test_showing_archived_cards_starts_counts_without_waiting_for_the_next_minute(self):
        self.window.matching_cards=lambda stack:[]
        self.loader.refresh(self.snapshot,1)
        self.assertFalse(self.calls)
        self.window.matching_cards=lambda stack:stack['cards']
        self.loader.refresh(self.snapshot,1)
        self.assertTrue(self.started.wait(1))

    def test_visibility_cancellation_does_not_apply_network_error_backoff(self):
        self.loader.refresh(self.snapshot,1);self.assertTrue(self.started.wait(1))
        self.window.matching_cards=lambda stack:[];self.loader.refresh(self.snapshot,1)
        self.release.set();deadline=time.monotonic()+2
        while self.loader.pending and time.monotonic()<deadline:
            self.flush();time.sleep(.005)
        self.assertFalse(self.loader.failed)
        self.window.matching_cards=lambda stack:stack['cards'];self.loader.refresh(self.snapshot,1)
        deadline=time.monotonic()+2
        while len(self.calls)<4 and time.monotonic()<deadline:time.sleep(.005)
        self.assertGreaterEqual(len(self.calls),4)
