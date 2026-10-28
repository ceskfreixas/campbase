# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Sibling hover controls keep card opening, archiving and dragging separate."""
from .i18n import _
from .widgets import icon_button
from .card_tiles import CardTile
from .dragging import CardDrag


class ActiveCard(CardTile):
    def __init__(self, card, window, min_width=252):
        super().__init__(card, window, min_width=min_width)
        self.add_css_class('active-tile')
        self.drag_handle = self.archive_button = self.drag = self.handle_drag = None
        board = next((b for b in window.snapshot.get('boards', []) if b['id'] == window.board_id), {})
        if window.demo or board.get('permissions', {}).get('PERMISSION_EDIT', True):
            self.drag_handle = icon_button('list-drag-handle-symbolic', _("Arrossega la targeta"))
            self.drag_handle.add_css_class('flat')
            self.drag_handle.set_cursor_from_name('grab')
            self.archive_button = icon_button('folder-symbolic', _("Arxiva la targeta"),
                lambda *_unused: window.update_card(card, {'archived': True}, kind='archive'))
            self.archive_button.add_css_class('flat')
            self.add_actions(self.archive_button, self.drag_handle)
            self.drag = CardDrag(self, card, window, handle=self.card_widget)
            self.handle_drag = CardDrag(self, card, window, handle=self.drag_handle)
