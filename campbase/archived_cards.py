# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""A separate, subdued archive area with per-card and scoped bulk actions."""
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk
from . import localization as ui
from .i18n import _
from .widgets import label, icon_button
from .card_tiles import CardTile
from .dragging import CardDrag
from .card_sections import CardSection


class ArchivedCard(CardTile):
    def __init__(self, window, stack, card, *, flexible=False):
        super().__init__(card, window, min_width=0 if flexible else 252)
        self.add_css_class('archived-tile')
        self.delete_button = None
        self.restore_button = None
        self.drag = None
        board = next((board for board in window.snapshot.get('boards', []) if board['id'] == window.board_id), {})
        if window.demo or board.get('permissions', {}).get('PERMISSION_EDIT', True):
            self.restore_button = icon_button('edit-undo-symbolic', _("Restaura la targeta"),
                lambda *_unused: window.update_card(card, {'archived': False}, kind='archive'))
            self.restore_button.add_css_class('flat')
            self.delete_button = icon_button('user-trash-symbolic', _("Esborra la targeta"),
                lambda *_unused: window.delete_archived_cards(stack, [card]))
            self.delete_button.add_css_class('flat')
            self.delete_button.add_css_class('destructive-action')
            self.add_actions(self.restore_button, self.delete_button)
            self.drag = CardDrag(self, card, window, handle=self.card_widget)


class ArchivedCards(CardSection):
    def __init__(self, window, stack, cards, *, triage=False, flexible=False, column=None):
        super().__init__(window,stack,cards,kind='archived',title=_("Arxivades"),icon='folder-symbolic',
            empty=_("Arrossega-hi una targeta per arxivar-la."),triage=triage,
            hide=lambda:window.show_archived(stack['id'],False),hide_title=_("Amaga les arxivades"),column=column)
        title = _("Esborra les arxivades visibles") if window.query else _("Esborra totes les arxivades")
        self.delete_all=icon_button('user-trash-symbolic',title,lambda *_:window.delete_archived_cards(stack,cards))
        self.delete_all.add_css_class('flat');self.delete_all.add_css_class('destructive-action')
        board=next((board for board in window.snapshot.get('boards',[]) if board['id']==window.board_id),{})
        self.delete_all.set_sensitive(bool(cards) and (window.demo or board.get('permissions',{}).get('PERMISSION_EDIT',True)))
        self.add_action(self.delete_all)
        for card in cards:
            self.add_card(ArchivedCard(window,stack,card,flexible=flexible))
        if column is not None:
            from .archive_drop import ArchiveDrop
            self.drop=ArchiveDrop(self,column,self.cards,self.cards_box,triage)
