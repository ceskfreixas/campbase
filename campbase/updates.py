# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Optional collaboration feeds never block the durable Deck outbox."""
import time
import re
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from .collaboration import activity_creators, assignment_ids, display_comment, mention_token, comment_tokens
from .i18n import _
from .deck import DeckError, ServiceUnavailable
from .update_targets import destination


def collect_updates(api, store, snapshot=None, force=False):
    state = store.get('updates', {})
    account_key = api.server + '|' + api.username
    if state.get('account') != account_key:
        if state.get('account'):
            store.put('updates_read', [])
            store.put('creators', {})
            store.put('local_notices', [])
            store.put('updates_hidden', [])
        state = {'account': account_key}
    errors = {}
    profile = store.get('profile', {})
    if profile.get('account') != api.goa_id or time.time()-profile.get('checked', 0) >= 3600:
        try:
            store.put('profile', api.profile() | {'account': api.goa_id, 'checked': time.time()})
        except DeckError as error:
            errors['profile'] = str(error)
    sources = [('notifications', api.notifications), ('activity', api.activity)] if force or time.time()-state.get('checked', 0) >= 60 else []
    unavailable = state.get('unavailable', {})
    retry = state.get('retry_unavailable', {})
    sources = [(key, read) for key, read in sources if force or time.time() >= retry.get(key, 0)]
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix='campbase-feed') as pool:
        results = [(key, pool.submit(read)) for key, read in sources]
    for key, result in results:
        try:
            rows = result.result()
            if not isinstance(rows, list):
                raise DeckError(_("La resposta de Nextcloud no té el format esperat."))
            id_key = 'notification_id' if key == 'notifications' else 'activity_id'
            state[key] = [row for row in rows if isinstance(row, dict) and row.get('app') == 'deck' and
                          isinstance(row.get(id_key), int)]
            unavailable.pop(key, None)
            retry.pop(key, None)
        except ServiceUnavailable:
            unavailable[key] = True
            retry[key] = time.time()+3600
        except DeckError as error:
            errors[key] = str(error)
    if sources:
        state['checked'] = time.time()
        activity_creators(store, state.get('activity', []))
    if snapshot is not None:
        comments = []
        for board in snapshot.get('boards', []):
            for stack in snapshot.get('stacks', {}).get(str(board['id']), []):
                for card in stack.get('cards') or []:
                    if card.get('commentsUnread', 0) > 0:
                        comments.append({'key': f'comments:{card["id"]}:{card.get("commentsCount", 0)}',
                                         'board_id': board['id'], 'card_id': card['id'], 'title': card['title'],
                                         'count': card['commentsUnread']})
        state['comments'] = comments
    state['unavailable'] = unavailable
    state['retry_unavailable'] = retry
    state['errors'] = errors if sources else state.get('errors', {})
    store.put('updates', state)
    return state



def own_assignment_notice(store, api, operation, card):
    payload = operation['payload']
    desired = payload.get('changes', {}).get('assignedUsers')
    if desired is None:
        return None
    profile = store.get('profile', {})
    uid = profile.get('uid') if profile.get('account') == getattr(api, 'goa_id', '') else api.username
    added = assignment_ids(desired) - assignment_ids(payload.get('base', {}).get('assignedUsers'))
    if uid not in added or uid not in assignment_ids(card.get('assignedUsers')):
        return None
    return {'key': f'local:assignment:{operation["id"]}', 'event': 'self-assigned',
            'board_id': payload['board_id'], 'card_id': card['id'], 'title': card.get('title') or '',
            'datetime': datetime.now(timezone.utc).isoformat()}


def record_own_comment(store, board_id, card, result):
    uid = result.get('actorId') or ''
    mentioned = any(str(item.get('mentionId')) == uid for item in result.get('mentions') or [])
    if uid and not mentioned:
        try:
            token = mention_token(uid)
            mentioned = bool(re.search(r'(?<!\S)'+re.escape(token)+r'(?=$|[\s,;!?.])', result.get('message') or ''))
        except ValueError:
            pass
    store.record_notice({'key': f'local:comment:{card["id"]}:{result["id"]}',
                         'event': 'self-mentioned' if mentioned else 'own-comment',
                         'board_id': board_id, 'card_id': card['id'], 'title': card.get('title') or '',
                         'body': display_comment(result),
                         'mentions': comment_tokens(result), 'comment_id': str(result['id']),
                         'datetime': result.get('creationDateTime') or datetime.now(timezone.utc).isoformat()})


def record_own_reaction(store, board_id, card, parent, result, emoji):
    store.record_notice({'key': f'local:comment:{card["id"]}:{result["id"]}',
                         'event': 'self-reaction' if parent.get('actorId') == result.get('actorId') else 'own-reaction',
                         'board_id': board_id, 'card_id': card['id'], 'title': card.get('title') or '',
                         'body': display_comment(parent), 'emoji': emoji, 'comment_id': str(result['id']),
                         'datetime': result.get('creationDateTime') or datetime.now(timezone.utc).isoformat()})


def entries(store):
    state = store.get('updates', {})
    rows = []
    for item in state.get('notifications', []):
        from .comment_reactions import reaction_preview
        rich = item.get('subjectRichParameters') or {}
        emoji = reaction_preview(item.get('message'))
        title = item.get('subject') or ''
        if emoji and isinstance(rich, dict) and isinstance(rich.get('user'), dict):
            title = _("{name} ha reaccionat {emoji} a un comentari de «{title}».").format(
                name=rich['user'].get('name') or rich['user'].get('id') or _("Usuari de Deck"),
                emoji=emoji, title=(rich.get('deck-card') or {}).get('name') or _("Sense títol"))
        rows.append({**destination(item), 'key': f'n:{item["notification_id"]}', 'notice_id': item['notification_id'],
                     'title': title, 'body': item.get('message') or '',
                     'datetime': item.get('datetime', ''), 'link': item.get('link') or '',
                     'kind': item.get('object_type'), 'object_id': item.get('object_id'), 'icon': 'preferences-system-notifications-symbolic'})
    for item in state.get('activity', []):
        # The user's activity settings decide which server events are available.
        rows.append({**destination(item), 'key': f'a:{item["activity_id"]}', 'title': item.get('subject') or '',
                     'body': item.get('message') or '', 'datetime': item.get('datetime', ''),
                     'link': item.get('link') or '', 'kind': item.get('object_type'),
                     'object_id': item.get('object_id'), 'icon': 'view-list-symbolic', 'user': item.get('user', '')})
    for item in state.get('comments', []):
        rows.append({**item, 'body': _("Comentaris nous: {count}").format(count=item['count']),
                     'icon': 'user-status-pending-symbolic', 'datetime': ''})
    titles = {'self-assigned': _("T'has assignat la targeta «{title}»."),
              'self-mentioned': _("T'has mencionat a la targeta «{title}»."),
              'own-reaction': _("Has reaccionat {emoji} a un comentari de «{title}»."),
              'self-reaction': _("Has reaccionat {emoji} al teu comentari de «{title}»."),
              'own-comment': _("Has comentat la targeta «{title}».")}
    for item in store.get('local_notices', []):
        template = titles.get(item.get('event'))
        if template:
            rows.append({**item, 'title': template.format(title=item['title'], emoji=item.get('emoji', '')),
                         'icon': 'preferences-system-notifications-symbolic'})
    hidden = set(store.get('updates_hidden', []))
    rows = [row for row in rows if row['key'] not in hidden]
    seen = set(store.get('updates_read', []))
    for row in rows:
        row.update(destination(row))
        row['read'] = row['key'] in seen
    return sorted(rows, key=lambda row: (not row['read'], row.get('datetime') or ''), reverse=True)


def mark_read(store, key):
    seen = store.get('updates_read', [])
    store.put('updates_read', [*dict.fromkeys([*seen, key])][-2000:])


def erase_entries(api, store, rows):
    # Never call Nextcloud's global delete-all: that includes other applications.
    for row in rows:
        if row.get('notice_id'):
            api.dismiss_notification(row['notice_id'])
        store.dismiss_notice(row)
