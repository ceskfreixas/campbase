# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Native Talk conversations. A board link never grants conversation access."""
import re
from urllib.parse import urlencode
from .collaboration import members, person
from .deck import DeckError
from .i18n import _
from .links import board_url


def token(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9]{1,64}', value):
        raise ValueError('Invalid Talk conversation token')
    return value


def message_text(message):
    text = str(message.get('message') or '')
    for key, value in (message.get('messageParameters') or {}).items():
        if isinstance(value, dict):
            text = text.replace('{' + key + '}', str(value.get('name') or value.get('id') or ''))
    return text


def local_members(board):
    def remote(value):
        return isinstance(value, dict) and (value.get('type') == 6 or bool(value.get('remote')))
    return members({**board, 'owner': None if remote(board.get('owner')) else board.get('owner'),
                    'users': [u for u in board.get('users') or [] if not remote(u)],
                    'acl': [a for a in board.get('acl') or [] if a.get('type', 0) == 0]})


class Talk:
    def __init__(self, api):
        self.api = api

    def capabilities(self):
        caps = self.api.request('GET', '/capabilities?format=json', service='cloud')
        result = caps.get('capabilities', {}).get('spreed', {})
        if 'conversation-v4' not in result.get('features', []):
            raise DeckError(_("Aquest servidor no té Nextcloud Talk habilitat."))
        return result

    def conversations(self):
        return self.api.request('GET', '/room?noStatusUpdate=1', service='talk')

    def conversation(self, room):
        return self.api.request('GET', '/room/' + token(room) + '?noStatusUpdate=1', service='talk')

    def participants(self, room):
        return self.api.request('GET', '/room/' + token(room) + '/participants', service='talk')

    def direct(self, uid):
        # Talk returns the existing direct conversation rather than duplicating it.
        return self.api.request('POST', '/room', {'roomType': 1, 'invite': uid}, service='talk')

    def board_conversations(self, board):
        marker = board_url(self.api.server, board['id'])
        return [room for room in self.conversations() if room.get('type') == 2
                and room.get('description', '').strip() == marker]

    def create_board_conversation(self, board_id, created, *, expected_users=None, creating=lambda: None):
        """Only called after explicit invitation confirmation; no automatic sync.

        Persist the room immediately, before adding people. An interrupted group
        setup can then be reviewed in Talk without blindly creating another room.
        """
        caps = self.capabilities()
        if 'room-description' not in caps.get('features', []):
            raise DeckError(_("Gestiona aquesta conversa des de Nextcloud Talk."))
        board = self.api.check_board(board_id)
        owner = person(board.get('owner'))['uid']
        profile = self.api.profile()
        if owner != profile['uid']:
            raise DeckError(_("Només el responsable pot crear el xat del tauler."))
        if expected_users is not None and {u['uid'] for u in local_members(board)} != set(expected_users):
            raise DeckError(_("Els membres han canviat. Revisa'ls abans de crear el xat."))
        existing = self.board_conversations(board)
        if existing:
            return existing[0]
        creating()
        room = self.api.request('POST', '/room', {'roomType': 2, 'roomName': board['title'][:255]}, service='talk')
        room_token = token(room['token'])
        created(room_token)
        self.api.request('PUT', '/room/' + room_token + '/description',
                         {'description': board_url(self.api.server, board_id)}, service='talk')
        for user in local_members(board):
            if user['uid'] != profile['uid']:
                self.api.request('POST', '/room/' + room_token + '/participants',
                                 {'newParticipant': user['uid'], 'source': 'users'}, service='talk')
        actual = {p.get('actorId') for p in self.participants(room_token) if p.get('actorType') == 'users'}
        if actual != {u['uid'] for u in local_members(board)}:
            raise DeckError(_("Talk no ha confirmat tots els participants. Revisa el xat a Talk."))
        return self.api.request('GET', '/room/' + room_token, service='talk')

    def messages(self, room, *, after=0, before=0):
        params = {'lookIntoFuture': int(bool(after)), 'limit': 100, 'timeout': 1,
                  'noStatusUpdate': 1, 'setReadMarker': 0, 'markNotificationsAsRead': 0}
        if after or before:
            params['lastKnownMessageId'] = after or before
        return self.api.request('GET', '/chat/' + token(room) + '?' + urlencode(params), service='chat') or []

    def send(self, room, text, reference):
        return self.api.request('POST', '/chat/' + token(room),
                                {'message': text, 'referenceId': reference}, service='chat')

    def mark_read(self, room, message_id):
        return self.api.request('POST', '/chat/' + token(room) + '/read',
                                {'lastReadMessage': int(message_id)}, service='chat')
