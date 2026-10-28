# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Undo only the latest move/archive action, without discarding other drafts."""
import json
from .deck import ConflictError
from .i18n import _


def undo_action(store, operation_id):
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute("SELECT value FROM state WHERE key='undo_action'").fetchone()
        action = json.loads(row[0]) if row else None
        if not action or action['operation_id'] != operation_id:
            raise ConflictError(_("Aquesta acció ja no es pot desfer."))
        operations = [dict(row) | {'payload': json.loads(row['payload'])}
                      for row in db.execute('SELECT * FROM outbox ORDER BY id').fetchall()]
        row = db.execute("SELECT value FROM state WHERE key='snapshot'").fetchone()
        view = store.project(json.loads(row[0]) if row else {}, operations)
        card = next((card for stack in view.get('stacks', {}).get(str(action['board_id']), [])
                     for card in stack.get('cards', []) if card['id'] == action['card_id']), None)
        payload, before = action['payload'], action['before']
        expected_stack = payload.get('target_stack', payload.get('stack_id'))
        expected_archived = payload.get('archived', payload.get('changes', {}).get('archived', before['archived']))
        if not card or card['stackId'] != expected_stack or bool(card.get('archived')) != expected_archived:
            raise ConflictError(_("La targeta ha canviat. Els altres canvis es conserven."))
        own = next((op for op in operations if op['id'] == operation_id), None)
        later = any(op['id'] > operation_id and op['payload'].get('card_id') == card['id'] for op in operations)
        if own and own['state'] == 'pending' and not action['attempted'] and not later:
            db.execute('DELETE FROM outbox WHERE id=?', (operation_id,))
        else:
            inverse = {'board_id': action['board_id'], 'card_id': card['id']}
            if action['kind'] == 'move':
                inverse.update(source_stack=card['stackId'], target_stack=before['stack_id'], order=before['order'])
                if 'archived' in payload:
                    inverse.update(archived=before['archived'], base_archived=expected_archived)
                kind = 'move'
            else:
                inverse.update(stack_id=card['stackId'], changes={'archived': before['archived']},
                               base={'archived': expected_archived})
                kind = 'archive'
            if own and own['state'] == 'blocked':
                db.execute('DELETE FROM outbox WHERE id=?', (operation_id,))
            db.execute('INSERT INTO outbox(kind,payload) VALUES (?,?)', (kind, json.dumps(inverse)))
        store._put(db, 'undo_action', None)
