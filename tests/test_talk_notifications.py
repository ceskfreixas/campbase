# SPDX-License-Identifier: GPL-3.0-or-later
"""Native Talk alerts reuse the existing feed without Deck destinations or writes."""
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from campbase.storage import Store
from campbase.updates import collect_updates, entries, mark_read, erase_entries
from campbase.update_targets import destination
from campbase.talk import Talk


class TalkNotificationTests(unittest.TestCase):
    def test_native_feed_is_cached_and_preserves_talk_destination(self):
        api = SimpleNamespace(server='https://cloud.example.invalid', username='alice', goa_id='test',
            profile=Mock(return_value={}), activity=Mock(return_value=[]),
            notifications=Mock(return_value=[
                {'notification_id': 1, 'app': 'spreed', 'object_type': 'chat', 'object_id': 'room123/45',
                 'subject': 'Robert in Project', 'message': 'Hello', 'link': 'https://cloud.example.invalid/call/room123#message_45'},
                {'notification_id': 2, 'app': 'mail', 'subject': 'Unrelated'}]),
            dismiss_notification=Mock())
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            collect_updates(api, store)
            collect_updates(api, store)
            api.notifications.assert_called_once_with()
            api.activity.assert_called_once_with()
            row, = entries(store)
            self.assertEqual(row['talk_token'], 'room123')
            self.assertNotIn('card_id', row)
            self.assertFalse(row['read'])
            mark_read(store, row['key'])
            self.assertTrue(entries(store)[0]['read'])
            erase_entries(api, store, entries(store))
            api.dismiss_notification.assert_called_once_with(1)
            self.assertFalse(entries(store))

    def test_tokens_are_validated_and_never_resolve_as_deck_ids(self):
        for object_id in ['12345/67', 'room123']:
            self.assertEqual(destination({'app': 'spreed', 'object_type': 'chat', 'object_id': object_id,
                 'link': '/board/99/card/88'}), {'talk_token': object_id.split('/')[0]})
        for value in ['../secret', 'room?token=evil', '', 'a'*65]:
            self.assertEqual(destination({'app': 'spreed', 'object_type': 'chat', 'object_id': value}), {})
        self.assertEqual(destination({'app': 'spreed', 'object_type': 'certificate_expiration', 'object_id': '123'}), {})
        self.assertEqual(destination({'talk_token': 'room123'}), {'talk_token': 'room123'})

    def test_opening_room_uses_current_server_and_does_not_update_status(self):
        api = SimpleNamespace(request=Mock(return_value={'token': 'room123'}))
        self.assertEqual(Talk(api).conversation('room123'), {'token': 'room123'})
        api.request.assert_called_once_with('GET', '/room/room123?noStatusUpdate=1', service='talk')
        with self.assertRaises(ValueError): Talk(api).conversation('../secret')
