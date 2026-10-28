# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Emoji replies remain portable, identifiable and navigable across clients."""
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from campbase.comment_reactions import reaction_message, reaction, group_comments, reaction_preview
from campbase.deck import Deck, DeckError
from campbase.storage import Store
from campbase.updates import entries, record_own_reaction
from campbase.update_targets import destination, matches_comment
from campbase.i18n import configure


class ReactionTests(unittest.TestCase):
    def setUp(self):
        configure('ca', user_choice=True)
        self.parent = {'id': 1, 'actorId': 'bob', 'actorType': 'users', 'message': 'Proposta',
                       'creationDateTime': '2026-10-28T10:00:00Z'}
        self.reply = {'id': 2, 'actorId': 'alice', 'message': '👍 @bob', 'replyTo': self.parent,
                      'creationDateTime': '2026-10-28T10:01:00Z'}

    def test_only_exact_emoji_replies_are_grouped(self):
        normal = dict(self.reply, id=3, message='👍 @bob bona proposta')
        comments, reactions = group_comments([self.reply, normal])
        self.assertEqual([item['id'] for item in comments], [1, 3])
        self.assertEqual(reactions['1'], [self.reply])
        self.assertEqual(reaction(self.reply), '👍')
        self.assertIsNone(reaction(dict(self.reply, replyTo={})))
        self.assertIsNone(reaction(dict(self.reply, message='👍 @carol')))
        self.assertIsNone(reaction_preview(normal['message']))

    def test_author_mention_is_explicit_and_handles_spaces(self):
        self.assertEqual(reaction_message(self.parent, '❤️'), '❤️ @bob')
        parent = dict(self.parent, actorId='Bob Smith')
        message = reaction_message(parent, '👍')
        self.assertEqual(message, '👍 @"user/Bob Smith"')
        self.assertEqual(reaction_preview(message), '👍')
        with self.assertRaises(ValueError):
            reaction_message(parent, 'arbitrary content')

    def test_api_sends_parent_id_and_requires_parent_confirmation(self):
        api = Deck(SimpleNamespace(server='https://cloud.example.invalid', username='alice', password='dummy'))
        api.request = Mock(return_value=self.reply)
        self.assertEqual(api.add_comment(99, '👍 @bob', parent_id=1), self.reply)
        api.request.assert_called_once_with('POST', '/cards/99/comments', {'message': '👍 @bob', 'parentId': 1}, ocs=True)
        api.request.return_value = dict(self.reply, replyTo={})
        with self.assertRaises(DeckError):
            api.add_comment(99, '👍 @bob', parent_id=1)

    def test_received_notice_describes_reaction_and_targets_the_reply(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            notice = {'notification_id': 7, 'object_type': 'card', 'object_id': '99',
                      'subject': 'Mention', 'message': '👍 @bob', 'datetime': self.reply['creationDateTime'],
                      'subjectRichParameters': {'user': {'id': 'alice', 'name': 'Alícia'},
                                                'deck-card': {'id': '99', 'name': 'Prova'}}}
            store.put('updates', {'notifications': [notice]})
            row = entries(store)[0]
            self.assertIn('ha reaccionat 👍', str(row['title']))
            self.assertTrue(matches_comment(self.reply, destination(row)))
            record_own_reaction(store, 1, {'id': 99, 'title': 'Prova'}, self.parent, self.reply, '👍')
            own = next(row for row in entries(store) if row['key'].startswith('local:'))
            self.assertEqual(destination(own)['comment_id'], '2')
