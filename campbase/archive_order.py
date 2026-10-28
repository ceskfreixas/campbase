# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Plan an archive insertion without rewriting unaffected neighbours."""


def insertion_plan(cards, current, position):
    peers = sorted((card for card in cards if card['id'] != current['id'] and not card.get('deletedAt')),
                   key=lambda card: (card.get('order', 0), card['id']))
    position = max(0, min(position, len(peers)))
    previous = peers[position-1] if position else None
    following = peers[position] if position < len(peers) else None
    low = previous.get('order', 0) if previous else 0
    high = following.get('order', 0) if following else low+1024
    candidates = (current.get('order', 0), (low+high)//2, low, high)
    def fits(order):
        key = (order, current['id'])
        return order >= 0 and (previous is None or (low, previous['id']) < key) and (
            following is None or key < (high, following['id']))
    order = next((value for value in candidates if fits(value)), None)
    if order is None:
        order = low + (current['id'] <= previous['id']) if previous else 0
    plan = [{'id': current['id'], 'base': current.get('order', 0), 'order': order}]
    # Dense integer positions occasionally need room. Shift only the colliding
    # neighbours, stopping as soon as an existing position already fits.
    previous_key = (order, current['id'])
    for card in peers[position:]:
        key = (card.get('order', 0), card['id'])
        if key > previous_key:
            break
        order = previous_key[0] + (card['id'] <= previous_key[1])
        plan.append({'id': card['id'], 'base': card.get('order', 0), 'order': order})
        previous_key = (order, card['id'])
    return plan
