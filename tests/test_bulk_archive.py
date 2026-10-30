# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Column archive batches preserve drafts, permissions and offline durability."""
import copy
import tempfile
import unittest
from unittest.mock import Mock
from campbase.deck import OfflineError, ConflictError
from campbase.storage import Store
from campbase.sync import SyncEngine


class BulkArchiveTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = Store(directory.name)
        self.snapshot = {'boards': [{'id': 1, 'permissions': {'PERMISSION_EDIT': True}}],
            'stacks': {'1': [{'id': 10, 'cards': [
                {'id': index, 'stackId': 10, 'archived': index == 4, 'order': index,
                 'title': str(index), 'assignedUsers': [{'participant': {'uid': 'alice'}}]}
                for index in range(1, 5)]}, {'id': 20, 'cards': []}]}}
        self.store.put('snapshot', self.snapshot)
        self.engine = SyncEngine(self.store)
        self.addCleanup(self.engine.close)

    def test_batch_is_scoped_idempotent_and_keeps_assignment_and_drafts(self):
        self.store.enqueue('update', {'board_id': 1, 'stack_id': 10, 'card_id': 1,
            'changes': {'title': 'Draft'}, 'base': {'title': '1'}})
        self.assertEqual(self.store.archive_cards(1, 10, [1, 2, 4, 999]), 2)
        self.assertEqual(self.store.archive_cards(1, 10, [1, 2]), 0)
        cards = self.store.view()['stacks']['1'][0]['cards']
        self.assertEqual(cards[0]['title'], 'Draft')
        self.assertEqual(cards[0]['assignedUsers'], self.snapshot['stacks']['1'][0]['cards'][0]['assignedUsers'])
        self.assertTrue(cards[0]['archived']);self.assertTrue(cards[1]['archived'])
        self.assertFalse(cards[2]['archived'])
        self.assertEqual(len(self.store.operations()), 3)

    def test_permission_and_changed_location_are_rechecked(self):
        self.snapshot['boards'][0]['permissions']['PERMISSION_EDIT'] = False
        self.store.put('snapshot', self.snapshot)
        self.assertEqual(self.store.archive_cards(1, 10, [1, 2]), 0)
        self.snapshot['boards'][0]['permissions']['PERMISSION_EDIT'] = True
        self.store.put('snapshot', self.snapshot)
        self.store.enqueue('move', {'board_id': 1, 'card_id': 1, 'source_stack': 10,
            'target_stack': 20, 'order': 0, 'archived': False})
        self.assertEqual(self.store.archive_cards(1, 10, [1, 2]), 1)
        self.assertEqual(self.store.operations()[-1]['payload']['card_id'], 2)

    def test_engine_starts_one_sync_for_whole_batch(self):
        self.engine.notify = Mock();self.engine.sync = Mock()
        self.assertEqual(self.engine.archive_cards(1, 10, [1, 2, 3]), 3)
        self.engine.notify.assert_called_once_with()
        self.engine.sync.assert_called_once_with(automatic=True)

    def test_sync_refreshes_workspace_once_without_per_card_redraws(self):
        self.store.archive_cards(1, 10, [1, 2, 3])
        remote = copy.deepcopy(self.snapshot)
        def update(_board, _stack, card_id, changes, *_args):
            card = next(card for card in remote['stacks']['1'][0]['cards'] if card['id'] == card_id)
            card.update(changes)
            return copy.deepcopy(card)
        self.engine.api = Mock()
        self.engine.api.update_card.side_effect = update
        self.engine.api.fetch.return_value = remote
        self.engine.refresh_updates = Mock();self.engine.notify = Mock()
        self.engine._sync()
        self.assertEqual(self.engine.api.update_card.call_count, 3)
        self.engine.api.fetch.assert_called_once_with(refresh_auth=False)
        self.assertEqual(self.engine.notify.call_count, 2)
        self.assertFalse(self.store.operations())

    def test_connection_failure_preserves_unsent_cards(self):
        self.store.archive_cards(1, 10, [1, 2, 3])
        self.engine.api = Mock()
        def update(_board, _stack, card_id, changes, *_args):
            if card_id == 2:
                raise OfflineError('offline')
            return self.snapshot['stacks']['1'][0]['cards'][0] | changes
        self.engine.api.update_card.side_effect = update
        with self.assertRaises(OfflineError):self.engine._send_pending()
        self.assertEqual([operation['payload']['card_id'] for operation in self.store.operations()], [2, 3])
        self.assertTrue(all(card['archived'] for card in self.store.view()['stacks']['1'][0]['cards']))

    def test_conflicting_card_does_not_stop_other_cards(self):
        self.store.archive_cards(1, 10, [1, 2, 3])
        self.engine.api = Mock()
        def update(_board, _stack, card_id, changes, *_args):
            if card_id == 2:raise ConflictError('conflict')
            return next(card for card in self.snapshot['stacks']['1'][0]['cards'] if card['id'] == card_id) | changes
        self.engine.api.update_card.side_effect = update
        self.engine._send_pending()
        operations = self.store.operations()
        self.assertEqual(len(operations), 1)
        self.assertEqual(operations[0]['payload']['card_id'], 2)
        self.assertEqual(operations[0]['state'], 'blocked')
