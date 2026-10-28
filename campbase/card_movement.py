# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Durable restore/reorder/archive steps for Deck's active-only reorder API."""
from .deck import ConflictError
from .i18n import _


def perform_move(api, store, operation):
    payload = operation['payload']

    def checkpoint(**fields):
        updated = store.checkpoint_move(operation['id'], fields)
        if updated is None:
            raise ConflictError(_("Aquesta acció ja no es pot desfer."))
        payload.update(updated)

    board, card_id = payload['board_id'], payload['card_id']
    source, target = payload['source_stack'], payload['target_stack']
    current = api.card_for_move(board, card_id, source, target)
    force = payload.get('force', False)
    if current['stackId'] not in (source, target) and not force:
        raise ConflictError(_("La targeta s'ha mogut a una altra columna des d'un altre dispositiu."))
    if 'archived' not in payload:
        checkpoint(archived=bool(current.get('archived')), base_archived=bool(current.get('archived')))
    desired, actual = bool(payload['archived']), bool(current.get('archived'))
    base = bool(payload.get('base_archived', actual))
    if actual not in (base, desired) and not force and not (payload.get('restore_started') and not actual):
        raise ConflictError(_("El contingut d'aquesta targeta ha canviat a Deck. El teu esborrany s'ha conservat."))
    # The ordinary update endpoint can place an archived card directly. Keep
    # the old restore/reorder checkpoints resumable for operations already sent.
    if desired and (payload.get('archive_direct') or not (payload.get('restore_started') or payload.get('move_done'))):
        return move_to_archive(api, board, target, current, payload, checkpoint)
    expected_orders = {payload['order']}
    for entry in payload.get('archive_order') or []:
        if entry['id'] == card_id:
            expected_orders.update((entry['base'],entry['order']))
    moved = payload.get('move_done') and current['stackId'] == target and current.get('order') in expected_orders
    if payload.get('move_done') and not moved:
        if not force:
            raise ConflictError(_("El contingut d'aquesta targeta ha canviat a Deck. El teu esborrany s'ha conservat."))
        checkpoint(move_done=False, archive_order=None, archive_order_done=False)
    if not moved:
        if actual:
            # Save intent before the first write, including a lost response.
            checkpoint(restore_started=True)
            current = api.set_archived(board, current['stackId'], card_id, False, current=current)
        current = api.move_card(board, card_id, source, target, payload['order'], force, current=current)
        checkpoint(move_done=True)
    current = api.set_archived(board, target, card_id, desired, current=current)
    if desired and not payload.get('archive_order_done'):
        reorder_archived(api, board, target, card_id, payload, checkpoint)
        current = api.get_card(board, target, card_id)
    return current


def move_to_archive(api, board, target, current, payload, checkpoint):
    from .archive_order import insertion_plan
    if not payload.get('archive_direct') or payload.get('force'):
        plan = insertion_plan(api.archived_cards(board, target), current, payload['order'])
        checkpoint(archive_direct=True, archive_order=plan,
                   archive_base={key: current.get(key) for key in ('stackId', 'order', 'archived')})
    plan = payload['archive_order']
    mover = next(entry for entry in plan if entry['id'] == current['id'])
    result = api.update_card(board, current['stackId'], current['id'],
                             {'stackId': target, 'order': mover['order'], 'archived': True},
                             payload['archive_base'], payload.get('force', False))
    # Confirm each changed neighbour against its original or already-applied
    # position. No restore/rearchive cycle and no reads for unaffected cards.
    for entry in plan:
        if entry['id'] != current['id']:
            api.update_card(board, target, entry['id'], {'order': entry['order']},
                            {'order': entry['base'], 'stackId': target, 'archived': True})
    checkpoint(archive_order_done=True)
    return result


def reorder_archived(api, board, stack, card_id, payload, checkpoint):
    """Archived order is independent of Deck's active-only reorder list."""
    plan = payload.get('archive_order')
    if plan is None or payload.get('force'):
        cards = sorted(api.archived_cards(board, stack), key=lambda card:(card.get('order',0),card['id']))
        card = next((card for card in cards if card['id'] == card_id), None)
        if card is None:
            raise ConflictError(_("Deck no ha confirmat tots els canvis. L'esborrany es conserva."))
        cards = [item for item in cards if item['id'] != card_id]
        cards.insert(min(payload['order'],len(cards)),card)
        plan = [{'id':card['id'],'base':card.get('order',0),'order':index} for index,card in enumerate(cards)]
        checkpoint(archive_order=plan)
    for entry in plan:
        if entry['base'] == entry['order']:
            continue
        api.update_card(board, stack, entry['id'], {'order':entry['order']},
                        {'order':entry['base'],'stackId':stack,'archived':True})
    checkpoint(archive_order_done=True)
