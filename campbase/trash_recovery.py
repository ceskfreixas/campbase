# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Bounded trash reads and conflict guards for explicit recovery actions."""
from concurrent.futures import ThreadPoolExecutor
from .deck import ConflictError
from .i18n import _


def load_deleted_items(api, board_id):
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix='campbase-trash') as pool:
        cards = pool.submit(api.deleted_cards, board_id)
        columns = pool.submit(api.deleted_stacks, board_id)
        return {'cards': cards.result(), 'columns': columns.result()}


def restore_deleted_card(api, store, board_id, card):
    if any(operation['payload'].get('card_id') == card['id'] for operation in store.operations()):
        raise ConflictError(_("Resol els canvis pendents d'aquesta targeta abans de restaurar-la."))
    return api.restore_card(board_id, card['stackId'], card['id'])


def restore_deleted_stack(api, store, board_id, stack):
    for operation in store.operations():
        payload = operation['payload']
        if payload.get('board_id') == board_id and stack['id'] in (
                payload.get('stack_id'), payload.get('source_stack'), payload.get('target_stack')):
            raise ConflictError(_("Resol els canvis pendents d'aquesta columna abans de restaurar-la."))
    return api.restore_stack(board_id, stack['id'])
