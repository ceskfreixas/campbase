# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Synthetic conversation contracts; never send to a real Nextcloud account."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from campbase.deck import DeckError
from campbase.federation import cloud_id, federation_available, share_remote
from campbase.talk import Talk, token, message_text, local_members
from campbase.collaboration import CollaborationAPI


class FederationTests(unittest.TestCase):
    def test_cloud_ids_preserve_email_username_and_server_path(self):
        self.assertEqual(cloud_id(' alice@example.net@CLOUD.example/nextcloud/ '),
                         'alice@example.net@cloud.example/nextcloud')
        self.assertEqual(cloud_id('alice@https://cloud.example'), 'alice@cloud.example')

    def test_invalid_destinations_never_reach_the_server(self):
        api = Mock()
        for value in ('alice', '@cloud.example', 'alice@http://cloud.example',
                      'alice@cloud.example?secret', 'alice@cloud.example/../x', 'alice\n@cloud.example'):
            with self.subTest(value=value), self.assertRaises(DeckError):
                share_remote(api, 1, value, {})
        api.request.assert_not_called()
        api.share_board.assert_not_called()

    def test_old_and_disabled_servers_never_send_invitations(self):
        api = Mock()
        api.request.return_value = {'capabilities': {'deck': {'version': '1.17.5'}}}
        self.assertFalse(federation_available(api))
        api.request.side_effect = [{'capabilities': {'deck': {'version': '1.18.6'}}}, {'federationEnabled': False}]
        with self.assertRaises(DeckError):
            share_remote(api, 1, 'alice@cloud.example', {})
        api.share_board.assert_not_called()

    def test_remote_share_uses_native_acl_type_and_confirms_it(self):
        api = Mock()
        api.request.side_effect = [{'capabilities': {'deck': {'version': '1.18.6'}}}, {'federationEnabled': True}]
        share_remote(api, 1, 'alice@CLOUD.example', {'permissionEdit': True})
        api.share_board.assert_called_once_with(1, 'alice@cloud.example', {'permissionEdit': True}, share_type=6)
        board = {'permissions': {'PERMISSION_SHARE': True}, 'acl': []}
        confirmed = {'permissions': board['permissions'], 'acl': [{'type': 6, 'participant': {'uid': 'alice@cloud.example', 'remote': 'cloud.example'}}]}
        api.check_board.side_effect = [board, confirmed, confirmed]
        api.request.reset_mock(side_effect=True)
        CollaborationAPI.share_board(api, 1, 'alice@cloud.example', {'permissionEdit': True}, share_type=6)
        CollaborationAPI.share_board(api, 1, 'alice@cloud.example', {'permissionEdit': True}, share_type=6)
        api.request.assert_called_once_with('POST', '/boards/1/acl', {'type': 6, 'participant': 'alice@cloud.example', 'permissionEdit': True})


class TalkTests(unittest.TestCase):
    def setUp(self):
        self.api = Mock(server='https://cloud.example')
        self.talk = Talk(self.api)

    def test_missing_talk_is_optional(self):
        self.api.request.return_value = {'capabilities': {}}
        with self.assertRaises(DeckError):
            self.talk.capabilities()

    def test_tokens_cannot_escape_talk_endpoint(self):
        for value in ('../room', '//evil.example', 'token?x=1', ''):
            with self.assertRaises(ValueError):
                self.talk.messages(value)
        self.api.request.assert_not_called()

    def test_incremental_reads_do_not_mark_hidden_messages_as_read(self):
        self.api.request.return_value = []
        self.talk.messages('abc123', after=42)
        method, path = self.api.request.call_args.args
        self.assertEqual(method, 'GET')
        self.assertIn('lastKnownMessageId=42', path)
        self.assertIn('lookIntoFuture=1', path)
        self.assertIn('setReadMarker=0', path)
        self.assertIn('markNotificationsAsRead=0', path)

    def test_direct_conversations_use_native_idempotent_creation(self):
        self.talk.direct('alice')
        self.api.request.assert_called_once_with('POST', '/room', {'roomType': 1, 'invite': 'alice'}, service='talk')

    def test_group_rechecks_owner_and_confirmed_member_set(self):
        self.api.request.return_value = {'capabilities': {'spreed': {'features': ['conversation-v4', 'room-description']}}}
        self.api.check_board.return_value = {'id': 1, 'owner': 'alice', 'users': ['bob']}
        self.api.profile.return_value = {'uid': 'alice'}
        with self.assertRaises(DeckError):
            self.talk.create_board_conversation(1, Mock(), expected_users={'alice'})
        self.assertTrue(all(call.args[0] == 'GET' for call in self.api.request.call_args_list))

    def test_messages_render_rich_parameters_as_plain_text(self):
        self.assertEqual(message_text({'message': 'Hello {user}', 'messageParameters': {'user': {'name': '<Alícia>'}}}), 'Hello <Alícia>')

    def test_federated_people_are_not_sent_to_the_local_user_invitation_endpoint(self):
        board = {'owner': 'alice', 'users': [{'uid': 'bob', 'displayname': 'Bob'},
                 {'uid': 'carol@remote.example', 'type': 6, 'remote': 'remote.example'}]}
        self.assertEqual({u['uid'] for u in local_members(board)}, {'alice', 'bob'})

    def test_group_checkpoint_precedes_invitations_and_only_invites_confirmed_members(self):
        board = {'id': 1, 'title': 'Team', 'owner': 'alice', 'users': ['bob']}
        self.api.check_board.return_value = board
        self.api.profile.return_value = {'uid': 'alice'}
        events = []
        def request(method, path, body=None, **kwargs):
            events.append((method, path, body))
            if path.startswith('/capabilities'):
                return {'capabilities': {'spreed': {'features': ['conversation-v4', 'room-description']}}}
            if method == 'GET' and path.startswith('/room?'):
                return []
            if path == '/room':
                return {'token': 'abc123'}
            if path.endswith('/participants') and method == 'GET':
                return [{'actorType': 'users', 'actorId': name} for name in ('alice', 'bob')]
            return {'token': 'abc123'}
        self.api.request.side_effect = request
        self.talk.create_board_conversation(1, lambda t: events.append(('checkpoint', t)),
            expected_users={'alice', 'bob'}, creating=lambda: events.append(('starting',)))
        checkpoint = events.index(('checkpoint', 'abc123'))
        invitation = next(i for i, e in enumerate(events) if len(e) == 3 and e[1].endswith('/participants'))
        self.assertLess(checkpoint, invitation)
        self.assertEqual(events[invitation][2], {'newParticipant': 'bob', 'source': 'users'})

    def test_existing_board_chat_never_reinvites_or_creates_a_room(self):
        self.api.check_board.return_value = {'id': 1, 'title': 'Team', 'owner': 'alice'}
        self.api.profile.return_value = {'uid': 'alice'}
        self.api.request.side_effect = [
            {'capabilities': {'spreed': {'features': ['conversation-v4', 'room-description']}}},
            [{'type': 2, 'token': 'abc123', 'description': 'https://cloud.example/index.php/apps/deck/board/1'}]]
        self.assertEqual(self.talk.create_board_conversation(1, Mock())['token'], 'abc123')
        self.assertTrue(all(call.args[0] == 'GET' for call in self.api.request.call_args_list))


if __name__ == '__main__':
    unittest.main()
