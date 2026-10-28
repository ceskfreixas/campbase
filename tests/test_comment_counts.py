# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Confirmed comment counts preserve queued card edits and assignment data."""
import tempfile
import unittest
from campbase.storage import Store


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
