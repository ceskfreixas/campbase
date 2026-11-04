# SPDX-License-Identifier: GPL-3.0-or-later
"""Paused cards stay in their Deck column and share its native drop routing."""
from gi.repository import Gtk
from . import localization as ui
from .i18n import _
from .card_sections import CardSection
from .card_tiles import CardTile
from .dragging import CardDrag
from .widgets import icon_button


class HeldCard(CardTile):
    def __init__(self, column, card):
        window=column.window
        super().__init__(card,window,min_width=0 if column.flexible else 252)
        self.add_css_class('held-tile');self.add_css_class('active-tile')
        self.drag=None;self.restore_button=None;self.archive_button=None
        board=next((item for item in window.snapshot['boards'] if item['id']==window.board_id),{})
        if window.demo or board.get('permissions',{}).get('PERMISSION_EDIT',False):
            self.restore_button=icon_button('edit-undo-symbolic',_("Reprèn la targeta"),
                lambda *_:window.move_card(card,column.stack['id'],held=False))
            self.archive_button=icon_button('folder-symbolic',_("Arxiva la targeta"),
                lambda *_:window.update_card(card,{'archived':True},kind='archive'))
            for button in (self.restore_button,self.archive_button):button.add_css_class('flat')
            self.add_actions(self.restore_button,self.archive_button)
            self.drag=CardDrag(self,card,window,handle=self.card_widget)


class HoldSection(CardSection):
    def __init__(self, column, cards):
        from .workflow_dialog import toggle_hold_column
        super().__init__(column.window,column.stack,cards,kind='hold',title=_("En espera"),
            icon='media-playback-pause-symbolic',empty=_("Arrossega-hi una targeta per posar-la en espera."),
            triage=column.triage,hide=lambda:toggle_hold_column(column.window,column.stack),hide_title=_("Amaga «En espera»"),column=column)
        for card in cards:self.add_card(HeldCard(column,card))
        from .archive_drop import HoldDrop
        self.drop=HoldDrop(self,column,self.cards,self.cards_box,column.triage)


def fold_column(column, expanded):
    from .workflow_state import save_options
    keyboard_focus=column.fold_button.has_visible_focus() or column.expand_button.has_visible_focus()
    column.expanded=expanded
    save_options(column.window.store,column.window.board_id,not_now_expanded=expanded)
    parent=column.get_parent()
    if parent and hasattr(parent,'transition') and parent.get_mapped():
        parent.transition.start(expanded,keyboard_focus=keyboard_focus)
    else:
        apply_fold(column)
        if keyboard_focus:
            (column.fold_button if expanded else column.expand_button).grab_focus()


def apply_fold(column):
    child=column.get_first_child()
    while child:
        child.set_visible(not column.expanded if child is column.rail else column.expanded)
        child=child.get_next_sibling()
    column.set_hexpand(False)
    column.set_size_request(-1 if column.expanded else 52,-1)
    if column.expanded:
        column.add_css_class('not-now-expanded');column.remove_css_class('not-now-folded')
    else:
        column.remove_css_class('not-now-expanded');column.add_css_class('not-now-folded')
    column.set_valign(Gtk.Align.FILL)
    column.fold_button.set_icon_name('pan-end-symbolic')
    ui.text(column.fold_button,'tooltip_text',_("Plega «Ara no»"))
    column.queue_resize()
