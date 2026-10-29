# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Deck participants, ACLs and assignments. No independent identity database."""
import re
from datetime import datetime
from urllib.parse import urlencode
from .i18n import _


def person(value):
    if isinstance(value, dict):
        uid = str(value.get('uid') or value.get('primaryKey') or value.get('id') or '')
        return {'uid': uid, 'displayname': value.get('displayname') or value.get('displayName') or value.get('name') or uid}
    uid = str(value or '')
    return {'uid': uid, 'displayname': uid}


def members(board):
    result = {}
    for value in [board.get('owner'), *(board.get('users') or [])]:
        user = person(value)
        if user['uid']:
            result[user['uid']] = user
    for acl in board.get('acl') or []:
        if acl.get('type', 0) == 0:
            user = person(acl.get('participant'))
            if user['uid']:
                result.setdefault(user['uid'], user)
    return sorted(result.values(), key=lambda user: user['displayname'].casefold())


def assignment_users(values):
    return [person(item.get('participant', item)) for item in values or [] if item.get('type', 0) == 0]


def assignment_ids(values):
    return {user['uid'] for user in assignment_users(values) if user['uid']}


def mention_token(uid):
    # Use readable usernames; Nextcloud requires quoting for spaces/namespaces.
    if not re.fullmatch(r"[\w@.\-' :/]+", uid, flags=re.ASCII):
        raise ValueError('Unsupported Nextcloud mention identifier')
    return '@'+uid if re.fullmatch(r"[\w@.\-']+", uid, flags=re.ASCII) else '@"user/' + uid + '"'


def display_comment(item):
    text = item.get('message') or ''
    for mention in item.get('mentions') or []:
        uid = str(mention.get('mentionId') or '')
        name = mention.get('mentionDisplayName') or uid
        if uid:
            text = text.replace('@"user/'+uid+'"', '@'+name).replace('@"'+uid+'"', '@'+name)
    return text


def comment_tokens(item):
    tokens = []
    for mention in item.get('mentions') or []:
        uid = str(mention.get('mentionId') or '')
        if uid:
            tokens.append('@'+uid)
            if any(token in (item.get('message') or '') for token in ('@"user/'+uid+'"', '@"'+uid+'"')):
                tokens.append('@'+(mention.get('mentionDisplayName') or uid))
    return tokens


def remember_creator(store, kind, object_id, user, when=None):
    store.record_creator(f'{kind}:{object_id}', {**person(user), 'datetime': when or datetime.now().astimezone().isoformat()})


def activity_creators(store, activities):
    """Only the explicit creation icon and exact object parameters are evidence.

    Deck's translated subject is presentation text, so never parse its wording.
    Historical activity may be disabled or expired; missing provenance stays unknown.
    """
    from urllib.parse import urlsplit
    for event in activities:
        if not isinstance(event, dict):
            continue
        rich = event.get('subject_rich') or []
        if not urlsplit(event.get('icon') or '').path.endswith('/add-color.svg') or len(rich) != 2 or not isinstance(rich[1], dict):
            continue
        params = rich[1]
        keys = set(params) - {'user'}
        if keys == {'board'}:
            kind, obj = 'board', params['board']
        elif keys == {'board', 'stack'}:
            kind, obj = 'stack', params['stack']
        elif keys == {'board', 'stack', 'card'}:
            kind, obj = 'card', params['card']
        else:
            continue
        user = person(params.get('user') or event.get('user'))
        if user['uid'] and isinstance(obj, dict) and obj.get('id'):
            remember_creator(store, kind, obj['id'], user, event.get('datetime'))


class CollaborationAPI:
    def profile(self):
        result = self.request('GET', '/user?format=json', service='cloud')
        return person({'uid': result['id'], 'displayname': result.get('displayname') or result.get('display-name')})

    def search_users(self, query):
        params = urlencode({'search': query.strip(), 'itemType': '0', 'shareType': '0', 'lookup': 'false', 'perPage': 30, 'format': 'json'})
        result = self.request('GET', '/sharees?'+params, service='sharing')
        users = {}
        for item in [*(result.get('exact', {}).get('users') or []), *(result.get('users') or [])]:
            value = item.get('value') or {}
            if value.get('shareType') == 0 and value.get('shareWith'):
                uid = str(value['shareWith'])
                users[uid] = {'uid': uid, 'displayname': item.get('label') or uid}
        return list(users.values())

    def share_board(self, board_id, uid, permissions, share_type=0, before_send=None):
        from .deck import DeckError
        if share_type not in (0, 6):
            raise ValueError('Unsupported board share type')
        board = self.check_board(board_id)
        if not board.get('permissions', {}).get('PERMISSION_SHARE', False):
            raise DeckError(_("No tens permís per compartir aquest tauler."))
        # A retry after a lost response must never create a duplicate ACL.
        if any(acl.get('type') == share_type and person(acl.get('participant'))['uid'] == uid for acl in board.get('acl') or []):
            return board
        if before_send:
            before_send()
        self.request('POST', f'/boards/{int(board_id)}/acl', {'type': share_type, 'participant': uid, **permissions})
        board = self.check_board(board_id)
        if not any(acl.get('type') == share_type and person(acl.get('participant'))['uid'] == uid for acl in board.get('acl') or []):
            raise DeckError(_("Deck no ha confirmat la compartició. Revisa els membres abans de tornar-ho a provar."))
        return board

    def change_access(self, board_id, acl_id, permissions=None):
        from .deck import DeckError
        board = self.check_board(board_id)
        if not board.get('permissions', {}).get('PERMISSION_SHARE', False):
            raise DeckError(_("No tens permís per compartir aquest tauler."))
        path = f'/boards/{int(board_id)}/acl/{int(acl_id)}'
        self.request('DELETE' if permissions is None else 'PUT', path, permissions)
        board = self.check_board(board_id)
        acl = next((item for item in board.get('acl') or [] if item.get('id') == acl_id), None)
        if (permissions is None and acl) or (permissions is not None and (not acl or any(bool(acl.get(k)) != v for k, v in permissions.items()))):
            raise DeckError(_("Deck no ha confirmat els permisos. Torna a carregar els membres."))
        return board

    def update_assignments(self, board_id, stack_id, card_id, desired, base, current=None):
        from .deck import DeckError
        before, after = assignment_ids(base), assignment_ids(desired)
        changed = before ^ after
        current = current if current is not None else self.get_card(board_id, stack_id, card_id)
        if not changed:
            return current
        actual = assignment_ids(current.get('assignedUsers'))
        path = self.card_path(board_id, current['stackId'], card_id)
        for uid in sorted(changed):
            selected = uid in after
            if selected != (uid in actual):
                self.request('PUT', path + ('/assignUser' if selected else '/unassignUser'), {'userId': uid})
        result = self.get_card(board_id, current['stackId'], card_id)
        actual = assignment_ids(result.get('assignedUsers'))
        if any((uid in actual) != (uid in after) for uid in changed):
            raise DeckError(_("Deck no ha confirmat les assignacions. El canvi es conserva."))
        return result

    def notifications(self):
        return self.request('GET', '/notifications?format=json', service='notifications') or []

    def activity(self):
        return self.request('GET', '/activity/deck?limit=100&format=json', service='activity') or []

    def dismiss_notification(self, notification_id):
        from .deck import ServiceUnavailable
        try:
            return self.request('DELETE', f'/notifications/{int(notification_id)}?format=json', service='notifications')
        except ServiceUnavailable:
            # Another client may have already dismissed this notification.
            return None
