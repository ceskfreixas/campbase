# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""An archive destination sharing the ordinary card insertion behavior."""
from gi.repository import Gtk
from .dragging import ColumnDrop


class ArchiveDrop(ColumnDrop):
    def __init__(self, section, column, widgets, container, triage):
        super().__init__(column, widgets, None, triage, container, widget=section, archived=True)
        self.spacer = None

    def coordinates(self, parent, x, y):
        ok, bounds = self.widget.compute_bounds(parent)
        return (x-bounds.origin.x, y-bounds.origin.y) if ok else (x, y)

    def mark_position(self, x, y):
        if self.widgets:
            self.widget.remove_css_class('archive-drop-active')
            super().mark_position(x, y)
        else:
            self.widget.add_css_class('archive-drop-active')

    def prepare(self, previous):
        # Keep the preceding insertion slot so this destination stays under the pointer.
        if previous is self.column.drop and previous.placeholder is not None:
            self.spacer, previous.placeholder = previous.placeholder, None
            self.spacer.set_opacity(0)

    def clear_mark(self):
        super().clear_mark()
        self.widget.remove_css_class('archive-drop-active')
        if self.spacer is not None:
            parent = self.spacer.get_parent()
            if parent is not None:
                self.column.drop.cards_box.remove(parent if isinstance(parent, Gtk.FlowBoxChild) else self.spacer)
            self.spacer = None
