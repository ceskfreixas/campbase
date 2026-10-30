# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Confirm a fixed set of cards before queueing one durable archive batch."""
from gi.repository import Adw
from . import localization as ui
from .i18n import _, ngettext


def confirm_archive_column(window, stack):
    board_id, stack_id = window.board_id, stack['id']
    cards = [card['id'] for card in window.cards_in_stack(stack_id) if not card.get('archived')]
    board = next((board for board in window.snapshot.get('boards', []) if board['id'] == board_id), {})
    if not cards or not board.get('permissions', {}).get('PERMISSION_EDIT', True):
        return None
    body = ngettext("S'arxivarà {count} targeta de «{column}», encara que hi hagi filtres actius.",
                    "S'arxivaran {count} targetes de «{column}», encara que hi hagi filtres actius.",
                    len(cards)).format(count=len(cards), column=stack['title'])
    prompt = ui.create(Adw.AlertDialog, heading=_("Arxiva-les totes"), body=body)
    ui.response(prompt, 'cancel', _("Cancel·la"))
    ui.response(prompt, 'archive', _("Arxiva"))
    prompt.set_default_response('cancel')
    prompt.set_close_response('cancel')
    prompt.set_response_appearance('archive', Adw.ResponseAppearance.SUGGESTED)
    prompt.connect('response', lambda _prompt, response:
                   window.engine.archive_cards(board_id, stack_id, cards) if response == 'archive' else None)
    prompt.present(window)
    return prompt
