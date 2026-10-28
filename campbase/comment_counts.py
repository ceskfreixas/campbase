# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Cache real comment totals separately from Deck's reply-inclusive totals."""
import json
import time


def decorate(snapshot, records):
    for stacks in snapshot.get('stacks', {}).values():
        for stack in stacks:
            for card in stack.get('cards') or []:
                total = card.get('commentsCount')
                summary = records.get(str(card['id']), {})
                if total == 0:
                    card['_textCommentsCount'] = 0
                elif isinstance(total, int) and summary.get('total') == total:
                    card['_textCommentsCount'] = summary['text']
    return snapshot


def _snapshot_card(db, board_id, card_id):
    row = db.execute("SELECT value FROM state WHERE key='snapshot'").fetchone()
    snapshot = json.loads(row[0]) if row else {}
    card = next((card for stack in snapshot.get('stacks', {}).get(str(board_id), [])
                 for card in stack.get('cards') or [] if card['id'] == card_id), None)
    return snapshot, card


def _records(db):
    row = db.execute("SELECT value FROM state WHERE key='comment_counts'").fetchone()
    return json.loads(row[0]) if row else {}


def _summary(total, text, revision):
    return {'total': total, 'text': max(0, min(text, total)), 'revision': revision, 'checked': time.time()}


def change_count(store, board_id, card_id, *, count=None, delta=0, text_count=None, reaction_delta=0):
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        snapshot, card = _snapshot_card(db, board_id, card_id)
        if card is None:
            return
        previous = card.get('commentsCount')
        if count is None and not isinstance(previous, int):
            return
        total = max(0, count if count is not None else previous+delta)
        records = _records(db)
        old = records.get(str(card_id), {})
        if text_count is None and count is None and old.get('total') == previous:
            text_count = old['text']+delta-reaction_delta
        if total != previous:
            card['commentsCount'] = total
            store._put(db, 'snapshot', snapshot)
        if text_count is not None:
            records[str(card_id)] = _summary(total, text_count, card.get('lastModified'))
            store._put(db, 'comment_counts', records)


def confirm_summary(store, board_id, card_id, total, text, revision):
    """Never apply a background result to a newer snapshot or another card."""
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        _snapshot, card = _snapshot_card(db, board_id, card_id)
        if card is None or card.get('commentsCount') != total:
            return False
        records = _records(db)
        records[str(card_id)] = _summary(total, text, revision)
        store._put(db, 'comment_counts', records)
        return True
