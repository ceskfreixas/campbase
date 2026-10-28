# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Archive insertion keeps every requested position and existing peer order."""
import itertools
import unittest
from campbase.archive_order import insertion_plan


class ArchiveOrderTests(unittest.TestCase):
    def test_dense_sparse_and_tied_positions(self):
        for ids in itertools.permutations((10, 20, 30, 40)):
            for orders in ((0, 0, 0), (0, 1, 2), (0, 100, 200)):
                peers = sorted(({'id': key, 'order': order} for key, order in zip(ids[:3], orders)),
                               key=lambda card: (card['order'], card['id']))
                current = {'id': ids[3], 'order': 1}
                for position in range(4):
                    with self.subTest(ids=ids, orders=orders, position=position):
                        cards = {card['id']: dict(card) for card in [*peers, current]}
                        plan = insertion_plan(peers, current, position)
                        for entry in plan:
                            cards[entry['id']]['order'] = entry['order']
                            self.assertGreaterEqual(entry['order'], 0)
                        expected = [card['id'] for card in peers]
                        expected.insert(position, current['id'])
                        result = sorted(cards.values(), key=lambda card: (card['order'], card['id']))
                        self.assertEqual([card['id'] for card in result], expected)

    def test_sparse_insertion_changes_only_the_moving_card(self):
        peers = [{'id': index, 'order': index*100} for index in range(1, 101)]
        plan = insertion_plan(peers, {'id': 1000, 'order': 0}, 50)
        self.assertEqual(len(plan), 1)
