# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Optional collaboration feeds never block the durable Deck outbox."""
import time
from concurrent.futures import ThreadPoolExecutor
from .collaboration import activity_creators
from .i18n import _
from .deck import DeckError, ServiceUnavailable
from .update_targets import destination
from .notification_text import notification_title, notification_actor


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
    profile = store.get('profile', {})
    state['recipient_uid'] = profile.get('uid') if profile.get('account') == api.goa_id else api.username
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
            apps = {'deck', 'spreed'} if key == 'notifications' else {'deck'}
            state[key] = [row for row in rows if isinstance(row, dict) and row.get('app') in apps
                          and isinstance(row.get(id_key), int)
                          and (row.get('app') != 'spreed' or destination(row).get('talk_token'))]
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
    state['unavailable'] = unavailable
    state['retry_unavailable'] = retry
    state['errors'] = errors if sources else state.get('errors', {})
    store.put('updates', state)
    return state


def entries(store):
    state = store.get('updates', {})
    rows = []
    profile = store.get('profile', {})
    uid = state.get('recipient_uid') or profile.get('uid') or state.get('account', '').rsplit('|', 1)[-1]
    for item in state.get('notifications', []):
        if uid and notification_actor(item) == uid:
            continue
        title = notification_title(item)
        rows.append({**destination(item), 'key': f'n:{item["notification_id"]}', 'notice_id': item['notification_id'],
                     'title': title, 'body': item.get('message') or '',
                     'datetime': item.get('datetime', ''), 'link': item.get('link') or '',
                     'app': item.get('app'), 'kind': item.get('object_type'), 'object_id': item.get('object_id'),
                     'icon': 'cat.ceskfreixas.Campbase-conversations-symbolic' if item.get('app') == 'spreed' else 'preferences-system-notifications-symbolic'})
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
