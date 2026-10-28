# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""A stable shared slot for assignee avatars and contextual card controls."""
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk
from .widgets import Card


class CardTileLayout(Gtk.OverlayLayout):
    def do_allocate(self, tile, width, height, baseline):
        Gtk.OverlayLayout.do_allocate(self, tile, width, height, baseline)
        heading = tile.card_widget.get_child().get_first_child()
        ok, bounds = heading.compute_bounds(tile)
        if not ok:
            return
        changed = False
        for child in (tile.assignee_avatars, tile.controls):
            if child is None:
                continue
            top = max(0, round(bounds.origin.y+bounds.size.height/2-child.get_height()/2))
            if child.get_margin_top() != top:
                child.set_margin_top(top)
                changed = True
        if changed:
            Gtk.OverlayLayout.do_allocate(self, tile, width, height, baseline)


class CardTile(Gtk.Overlay):
    def __init__(self, card, window, min_width=252):
        super().__init__(hexpand=True, valign=Gtk.Align.FILL)
        self.card = card
        self.card_widget = Card(card, window, min_width=min_width, draggable=False, inline_assignees=False)
        self.set_child(self.card_widget)
        self.controls = None
        self.assignee_avatars = self.card_widget.assignee_avatars
        self.set_layout_manager(CardTileLayout())
        if self.assignee_avatars:
            self.assignee_avatars.add_css_class('card-assignees')
            self.assignee_avatars.set_margin_end(14)
            self.assignee_avatars.set_valign(Gtk.Align.START)
            self.add_overlay(self.assignee_avatars)
            count = min(3, len(card.get('assignedUsers') or []))
            self.card_widget.get_child().set_margin_end(count*28+4)

    def add_actions(self, *buttons):
        self.add_css_class('has-card-controls')
        self.card_widget.get_child().set_margin_end(max(80, self.card_widget.get_child().get_margin_end()))
        actions = Gtk.Box(spacing=4, halign=Gtk.Align.END, valign=Gtk.Align.START, margin_end=8)
        self.controls = actions
        actions.add_css_class('hover-action')
        actions.add_css_class('card-controls')
        for button in buttons:
            actions.append(button)
        # Mouse/programmatic focus after a refresh is not a request to hide
        # the assignee. Keep the controls available for actual keyboard focus.
        for button in (self.card_widget, *buttons):
            button.connect('state-flags-changed', self.focus_changed)
        self.add_overlay(actions)

    def focus_changed(self, *_unused):
        buttons = [self.card_widget]
        child = self.controls.get_first_child()
        while child:
            buttons.append(child)
            child = child.get_next_sibling()
        if any(button.has_visible_focus() for button in buttons):
            self.add_css_class('keyboard-actions')
        else:
            self.remove_css_class('keyboard-actions')
