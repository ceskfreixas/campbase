# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Board trash uses fresh reads and restores only the selected deleted card."""
import copy
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from campbase.deck import Deck, ConflictError, DeckError, OfflineError
from campbase.storage import Store


class BoardTrashTests(unittest.TestCase):
    def setUp(self):
        self.api = Deck(SimpleNamespace(server='https://cloud.example.invalid', username='alice', password='dummy'))
        self.card = {'id': 99, 'stackId': 10, 'deletedAt': 100, 'archived': True, 'title': 'Deleted',
                     'description': 'Keep', 'owner': {'uid': 'alice'}, 'type': 'plain', 'order': 3,
                     'duedate': None, 'done': '2026-10-01T12:00:00Z',
                     'assignedUsers': [{'participant': {'uid': 'alice'}}], 'labels': [{'id': 4}]}
        self.remote = copy.deepcopy(self.card)
        self.writes = []
        self.api.check_board = Mock(return_value={'id': 1, 'permissions': {'PERMISSION_EDIT': True}})
        self.api.request = Mock(side_effect=self.request)

    def request(self, method, path, body=None, **kwargs):
        if path == '/1/cards/deleted':
            self.assertTrue(kwargs['internal'])
            return [copy.deepcopy(self.remote)] if self.remote['deletedAt'] else []
        if path == '/boards/1/stacks':return [{'id': 10}]
        if path == '/boards/1/stacks/10/cards/99':
            if method == 'PUT':
                self.writes.append(body)
                self.remote.update(body, deletedAt=0)
            return copy.deepcopy(self.remote)
        self.fail((method, path))

    def test_list_is_filtered_and_sorted_without_writes(self):
        self.api.request.side_effect = None
        self.api.request.return_value = [self.card, self.card | {'id': 100, 'deletedAt': 200},
                                        self.card | {'id': 101, 'deletedAt': 0}, {}]
        self.assertEqual([card['id'] for card in self.api.deleted_cards(1)], [100, 99])
        self.api.request.assert_called_once_with('GET', '/1/cards/deleted', internal=True)

    def test_restore_preserves_content_archived_state_assignment_and_labels(self):
        result = self.api.restore_card(1, 10, 99)
        self.assertEqual(result['deletedAt'], 0)
        for field in ['title', 'description', 'archived', 'assignedUsers', 'labels', 'done', 'order']:
            self.assertEqual(result[field], self.card[field])
        self.assertEqual(len(self.writes), 1)
        self.assertEqual(self.writes[0]['owner'], 'alice')
        self.assertNotIn('archived', self.writes[0])
        self.assertNotIn('assignedUsers', self.writes[0])
        self.assertEqual(self.api.request.call_count, 4)

    def test_already_restored_card_is_idempotent(self):
        self.remote['deletedAt'] = 0
        self.assertEqual(self.api.restore_card(1, 10, 99)['id'], 99)
        self.assertFalse(self.writes)

    def test_read_only_or_archived_board_cannot_restore(self):
        for board in [{'permissions': {'PERMISSION_EDIT': False}},
                      {'permissions': {'PERMISSION_EDIT': True}, 'archived': True},
                      {'permissions': {'PERMISSION_EDIT': True}, 'deletedAt': 1}]:
            self.api.check_board.return_value = board
            with self.assertRaises(ConflictError):self.api.restore_card(1, 10, 99)
        self.assertFalse(self.writes)

    def test_missing_original_column_or_changed_card_blocks_write(self):
        self.remote['stackId'] = 20
        with self.assertRaises(ConflictError):self.api.restore_card(1, 10, 99)
        self.remote['stackId'] = 10
        original = self.request
        self.api.request.side_effect = lambda method, path, *args, **kw: [] if path == '/boards/1/stacks' else original(method, path, *args, **kw)
        with self.assertRaises(ConflictError):self.api.restore_card(1, 10, 99)
        self.assertFalse(self.writes)

    def test_failed_verification_is_not_reported_as_restored(self):
        original = self.request
        def request(method, path, *args, **kw):
            if method == 'PUT':return None
            return original(method, path, *args, **kw)
        self.api.request.side_effect = request
        with self.assertRaises(DeckError):self.api.restore_card(1, 10, 99)

    def test_offline_read_never_writes(self):
        self.api.request.side_effect = OfflineError('offline')
        with self.assertRaises(OfflineError):self.api.restore_card(1, 10, 99)
        self.assertFalse(self.writes)

    def test_incremental_cache_keeps_other_cards_and_pending_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            store.put('snapshot', {'boards': [{'id': 1}], 'stacks': {'1': [
                {'id': 10, 'cards': [{'id': 1, 'stackId': 10, 'title': 'Original'}]}]}})
            store.enqueue('update', {'board_id': 1, 'stack_id': 10, 'card_id': 1,
                                    'changes': {'title': 'Draft'}})
            self.assertTrue(store.cache_restored_card(1, self.card | {'deletedAt': 0}))
            self.assertTrue(store.cache_restored_card(1, self.card | {'deletedAt': 0}))
            cards = store.view()['stacks']['1'][0]['cards']
            self.assertEqual(len(cards), 2)
            self.assertEqual(cards[0]['title'], 'Draft')
            self.assertEqual(len(store.operations()), 1)
            self.assertFalse(store.cache_restored_card(2, self.card))

    def test_restore_column_preserves_active_and_archived_cards_without_restoring_deleted_cards(self):
        stack = {'id': 10, 'boardId': 1, 'title': 'Column', 'order': 2, 'deletedAt': 100}
        self.api.check_board.return_value = {'permissions': {'PERMISSION_MANAGE': True}}
        writes = []
        def request(method, path, body=None, **kwargs):
            if path == '/1/stacks/deleted':return [dict(stack)] if stack['deletedAt'] else []
            if method == 'PUT':
                self.assertEqual(path, '/boards/1/stacks/10')
                writes.append(body);stack.update(deletedAt=0)
                return dict(stack)
            if path == '/boards/1/stacks':return [stack | {'cards': [self.card | {'id': 1, 'deletedAt': 0, 'archived': False}]}]
            if path == '/boards/1/stacks/archived':return [stack | {'cards': [self.card | {'id': 2, 'deletedAt': 0}, self.card]}]
            self.fail(path)
        self.api.request.side_effect = request
        result = self.api.restore_stack(1, 10)
        self.assertEqual([card['id'] for card in result['cards']], [1, 2])
        self.assertFalse(result['cards'][0]['archived']);self.assertTrue(result['cards'][1]['archived'])
        self.assertEqual(result['cards'][1]['assignedUsers'], self.card['assignedUsers'])
        self.assertEqual(writes, [{'title': 'Column', 'order': 2}])
        self.api.restore_stack(1, 10)
        self.assertEqual(len(writes), 1)

    def test_column_restore_requires_manage_permission(self):
        with self.assertRaises(ConflictError):self.api.restore_stack(1, 10)
        self.assertFalse(self.writes)
        self.api.request.assert_not_called()

    def test_column_cache_preserves_other_columns_and_pending_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            store.put('snapshot', {'boards': [{'id': 1}], 'stacks': {'1': [
                {'id': 20, 'order': 1, 'cards': [{'id': 1, 'stackId': 20, 'title': 'Original'}]}]}})
            store.enqueue('update', {'board_id': 1, 'stack_id': 20, 'card_id': 1, 'changes': {'title': 'Draft'}})
            self.assertTrue(store.cache_restored_stack(1, {'id': 10, 'order': 0, 'cards': [self.card]}))
            stacks = store.view()['stacks']['1']
            self.assertEqual([stack['id'] for stack in stacks], [10, 20])
            self.assertEqual(stacks[1]['cards'][0]['title'], 'Draft')
            self.assertEqual(len(store.operations()), 1)

    def test_pending_column_work_blocks_restoration(self):
        from campbase.trash_recovery import restore_deleted_stack
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            store.enqueue('move', {'board_id': 1, 'card_id': 99, 'source_stack': 10, 'target_stack': 20})
            self.api.restore_stack = Mock()
            with self.assertRaises(ConflictError):restore_deleted_stack(self.api, store, 1, {'id': 10})
            self.api.restore_stack.assert_not_called()
