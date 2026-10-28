# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Only the confirmed archived cards in the selected column may be removed."""
import copy
import http.server
import tempfile
import threading
import unittest
from types import SimpleNamespace
from test_sync import Fixture
from campbase.deck import Deck, DeckError, ConflictError
from campbase.storage import Store
from campbase.card_deletion import delete_archived_batch


class ArchivedDeletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.store = Store(self.directory.name)
        self.server.board = {'id': 1, 'title': 'Prova'}
        self.server.cards = {index: {'id': index, 'title': f'Card {index}', 'stackId': 10 if index < 3 else 20,
                                     'archived': index != 4, 'deletedAt': 0} for index in range(1, 5)}
        self.server.writes=[];self.server.reads=[];self.server.delete_errors={};self.server.reject_delete=False
        self.store.put('snapshot', {'boards': [self.server.board], 'stacks': {'1': [
            {'id': 10, 'cards': [copy.deepcopy(self.server.cards[i]) for i in [1, 2]]},
            {'id': 20, 'cards': [copy.deepcopy(self.server.cards[i]) for i in [3, 4]]}]}})
        self.api = Deck(SimpleNamespace(server=f'http://127.0.0.1:{self.server.server_port}',username='test',password='dummy'),allow_local=True)
        self.stopped = threading.Event()

    def remove(self, cards):
        return delete_archived_batch(self.api,self.store,1,10,[self.server.cards[index].copy() for index in cards],self.stopped)

    def cached_ids(self):
        return {card['id'] for stack in self.store.get('snapshot')['stacks']['1'] for card in stack['cards']}

    def test_bulk_scope_keeps_other_columns_and_active_cards(self):
        self.assertEqual(list(self.remove([1, 2])), [1, 2])
        self.assertEqual(self.cached_ids(), {3, 4})
        self.assertFalse(self.server.cards[3]['deletedAt'])
        self.assertFalse(self.server.cards[4]['deletedAt'])

    def test_restored_or_moved_card_is_not_deleted(self):
        for changes in [{'archived': False}, {'stackId': 20}]:
            self.server.cards[1].update(archived=True, stackId=10)
            self.server.cards[1].update(changes)
            with self.assertRaises(ConflictError):list(self.remove([1]))
            self.assertFalse(self.server.writes)
            self.assertIn(1,self.cached_ids())

    def test_partial_failure_preserves_unconfirmed_cards(self):
        self.server.delete_errors[2] = 503
        with self.assertRaises(DeckError):list(self.remove([1, 2]))
        self.assertEqual(self.cached_ids(), {2, 3, 4})
        self.assertFalse(self.server.cards[2]['deletedAt'])

    def test_pending_edits_block_the_batch_before_any_delete(self):
        self.store.enqueue('update', {'board_id':1,'card_id':2,'stack_id':10,'changes':{'title':'Draft'}})
        with self.assertRaises(ConflictError):list(self.remove([1, 2]))
        self.assertFalse(self.server.writes)
        self.assertEqual(self.store.operations()[0]['payload']['changes']['title'],'Draft')

    def test_stop_only_leaves_confirmed_deletions(self):
        job=self.remove([1, 2])
        self.assertEqual(next(job),1)
        self.stopped.set()
        self.assertEqual(list(job),[])
        self.assertEqual(self.cached_ids(),{2,3,4})

    def test_unconfirmed_delete_never_removes_cached_card(self):
        self.server.reject_delete=True
        with self.assertRaises(DeckError):list(self.remove([1]))
        self.assertIn(1,self.cached_ids())
