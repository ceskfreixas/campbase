# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Notification destinations from IDs, rich parameters and Deck routes."""
import re
from datetime import datetime
from urllib.parse import urlsplit
from .collaboration import display_comment


def identifier(value):
    try:
        return int(value) if int(value) > 0 else None
    except (ValueError, TypeError):
        return None


def destination(item):
    target = {key: item[key] for key in ('board_id', 'card_id', 'stack_id', 'comment_id', 'section',
                                       'comment_text', 'comment_time', 'comment_actor') if item.get(key)}
    rich = item.get('subject_rich')
    params = item.get('subjectRichParameters') or (rich[1] if isinstance(rich, list) and len(rich) == 2 else {})
    params = params if isinstance(params, dict) else {}
    for key, field in [('board', 'board_id'), ('deck-board', 'board_id'), ('card', 'card_id'),
                       ('deck-card', 'card_id'), ('stack', 'stack_id'), ('comment', 'comment_id')]:
        value = params.get(key)
        if isinstance(value, dict) and identifier(value.get('id')):
            target.setdefault(field, identifier(value['id']))
    kind = item.get('object_type') or item.get('kind')
    if identifier(item.get('object_id')):
        if kind in {'card', 'deck_card', 'deck-card'}:
            target.setdefault('card_id', identifier(item['object_id']))
        elif kind in {'board', 'deck_board', 'deck-board'}:
            target.setdefault('board_id', identifier(item['object_id']))
    link = item.get('link') or ''
    match = re.search(r'/boards?/(\d+)(?:/cards?/(\d+))?(?:/(comments|attachments|details)(?:/(\d+))?)?', link)
    if match:
        target.setdefault('board_id', int(match[1]))
        if match[2]:
            target.setdefault('card_id', int(match[2]))
        if match[3]:
            target.setdefault('section', match[3])
        if match[3] == 'comments' and match[4]:
            target.setdefault('comment_id', match[4])
    event, key = item.get('event'), str(item.get('key') or '')
    if event in {'self-mentioned', 'own-comment', 'own-reaction', 'self-reaction'} or key.startswith('comments:'):
        target['section'] = 'comments'
        if key.startswith('local:comment:'):
            target.setdefault('comment_id', key.rsplit(':', 1)[-1])
    elif event == 'self-assigned':
        target['section'] = 'assignees'
    elif 'comment' in params or urlsplit(item.get('icon') or '').path.endswith('/comment.svg'):
        target['section'] = 'comments'
    elif 'assigneduser' in params:
        target['section'] = 'assignees'
    elif 'label' in params:
        target['section'] = 'labels'
    elif 'acl' in params:
        target['section'] = 'members'
    elif 'stackBefore' in params:
        target['section'] = 'column'
    elif isinstance(params.get('after'), dict) and str(params['after'].get('id', '')).startswith('dt:'):
        target['section'] = 'due'
    elif 'attachment' in params:
        target['section'] = 'attachments'
    if item.get('notification_id') or item.get('notice_id'):
        if target.get('card_id') and item.get('message'):
            target.setdefault('section', 'comments')
        elif target.get('card_id') and 'user' in params:
            target.setdefault('section', 'assignees')
        elif target.get('card_id') and 'deck-board' in params:
            target.setdefault('section', 'due')
        elif target.get('board_id') and not target.get('card_id'):
            target.setdefault('section', 'members')
    if target.get('comment_id'):
        target['section'] = 'comments'
    if target.get('section') == 'comments':
        target.setdefault('comment_text', item.get('body') or item.get('message') or '')
        target.setdefault('comment_time', item.get('datetime') or '')
        user = params.get('user') or {}
        target.setdefault('comment_actor', user.get('id') if isinstance(user, dict) else '')
    return target


def matches_comment(item, target):
    if target.get('comment_id'):
        return str(item.get('id')) == str(target['comment_id'])
    if not target.get('comment_text') or not target.get('comment_time'):
        return False
    if target['comment_text'] not in {item.get('message'), display_comment(item)}:
        return False
    if target.get('comment_actor') and item.get('actorId') != target['comment_actor']:
        return False
    try:
        actual = datetime.fromisoformat(item['creationDateTime'].replace('Z', '+00:00'))
        expected = datetime.fromisoformat(target['comment_time'].replace('Z', '+00:00'))
        return abs((actual-expected).total_seconds()) <= 2
    except (KeyError, ValueError, TypeError):
        return False
