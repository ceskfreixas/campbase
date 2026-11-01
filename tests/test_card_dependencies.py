# SPDX-License-Identifier: GPL-3.0-or-later
"""Dependency writes use Deck relationships without overwriting card content."""
import copy
import tempfile
import unittest
from unittest.mock import Mock
from campbase.deck import Deck, DeckError, OfflineError, ConflictError
from campbase.storage import Store
from campbase.card_dependencies import dependency_ids


class DependencyTests(unittest.TestCase):
    def setUp(self):
        self.api = Deck.__new__(Deck)
        self.card = {'id': 3, 'stackId': 2, 'title': 'Source', 'description': 'Server draft', 'dependentCards': []}
        self.board = {'id': 1, 'permissions': {'PERMISSION_EDIT': True}}
        self.writes = []
        self.api.check_board = Mock(side_effect=lambda _: copy.deepcopy(self.board))
        self.api.get_card = Mock(side_effect=lambda *_: copy.deepcopy(self.card))
        self.api.request = Mock(side_effect=self.request)
        self.uncertain = self.reject = False

    def request(self, method, path, *args, **kwargs):
        if method == 'GET':
            self.assertEqual(path, '/cards/4')
            self.assertTrue(kwargs['internal'])
            return {'id': 4}
        self.writes.append((method, path))
        if not self.reject:
            self.card['dependentCards'] = [4] if method == 'POST' else []
        if self.uncertain:
            raise OfflineError('Lost response')

    def change(self, present=True):
        return self.api.set_card_dependency(1, 2, 3, 4, present)

    def test_confirm_add_remove_and_idempotent_retry(self):
        self.assertEqual(dependency_ids(self.change()), [4])
        self.change()
        self.assertEqual(len(self.writes), 1)
        self.assertEqual(dependency_ids(self.change(False)), [])
        self.assertEqual(self.writes, [('POST', '/boards/1/stacks/2/cards/3/dependentCards/4'),
                                      ('DELETE', '/boards/1/stacks/2/cards/3/dependentCards/4')])
        self.assertEqual(self.card['description'], 'Server draft')

    def test_lost_response_is_verified_without_second_write(self):
        self.uncertain = True
        self.assertEqual(dependency_ids(self.change()), [4])
        self.assertEqual(len(self.writes), 1)

    def test_unconfirmed_write_reports_failure(self):
        self.reject = True
        with self.assertRaises(DeckError):self.change()
        self.uncertain = True
        with self.assertRaises(OfflineError):self.change()

    def test_permissions_archival_movement_self_links_and_old_server(self):
        for field in ('archived', 'deletedAt'):
            with self.subTest(field=field):
                self.card[field] = True
                with self.assertRaises(ConflictError):self.change()
                self.card.pop(field)
        self.board['permissions']['PERMISSION_EDIT'] = False
        with self.assertRaises(ConflictError):self.change()
        self.board['permissions']['PERMISSION_EDIT'] = True
        self.card['stackId'] = 9
        with self.assertRaises(ConflictError):self.change()
        self.card['stackId'] = 2
        with self.assertRaises(DeckError):self.api.set_card_dependency(1,2,3,3,True)
        self.card.pop('dependentCards')
        with self.assertRaises(DeckError):self.change()
        self.assertFalse(self.writes)

    def test_target_access_and_invalid_server_data_do_not_write(self):
        self.api.request.side_effect = DeckError('No target access')
        with self.assertRaises(DeckError):self.change()
        self.assertFalse(self.writes)
        for value in (None, [True], [-1], ['4']):
            with self.subTest(value=value), self.assertRaises(DeckError):
                dependency_ids({'dependentCards': value})

    def test_cache_merge_preserves_pending_description_and_other_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            store.put('snapshot', {'boards': [self.board], 'stacks': {'1': [{'id': 2, 'cards': [self.card]}]}})
            store.enqueue('update', {'board_id': 1, 'stack_id': 2, 'card_id': 3,
                                    'changes': {'description': 'Local draft'}, 'base': {'description': 'Server draft'}})
            before = store.operations()
            store.cache_card_dependencies(1, dict(self.card, dependentCards=[4], description='Unexpected change'))
            current = store.view()['stacks']['1'][0]['cards'][0]
            self.assertEqual(current['description'], 'Local draft')
            self.assertEqual(current['dependentCards'], [4])
            self.assertEqual(store.operations(), before)
