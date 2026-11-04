# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""An archive destination sharing the ordinary card insertion behavior."""
from gi.repository import Gtk
from .dragging import ColumnDrop


class SectionDrop(ColumnDrop):
    def __init__(self, section, column, widgets, container, triage, *, archived=False, held=None):
        super().__init__(column, widgets, None, triage, container, widget=section, archived=archived,
                         held=held, register_target=False)
        self.highlight = 'archive-drop-active' if archived else 'hold-drop-active'
        self.spacer = None

    def accepts(self):
        field='archived_section' if self.archived else 'hold_section'
        return getattr(self.column,field,None) is self.widget and super().accepts()

    def coordinates(self, parent, x, y):
        ok, bounds = self.widget.compute_bounds(parent)
        return (x-bounds.origin.x, y-bounds.origin.y) if ok else (x, y)

    def mark_position(self, x, y):
        if any(widget.get_mapped() for widget in self.widgets):
            self.widget.remove_css_class(self.highlight)
            super().mark_position(x, y)
        else:
            self.widget.add_css_class(self.highlight)

    def prepare(self, previous):
        # Keep the preceding insertion slot so this destination stays under the pointer.
        if previous is self.column.drop and previous.placeholder is not None:
            self.spacer, previous.placeholder = previous.placeholder, None
            self.spacer.set_opacity(0)

    def clear_mark(self):
        super().clear_mark()
        self.widget.remove_css_class(self.highlight)
        if self.spacer is not None:
            parent = self.spacer.get_parent()
            if parent is not None:
                self.column.drop.cards_box.remove(parent if isinstance(parent, Gtk.FlowBoxChild) else self.spacer)
            self.spacer = None


class ArchiveDrop(SectionDrop):
    def __init__(self, section, column, widgets, container, triage):
        super().__init__(section, column, widgets, container, triage, archived=True)


class HoldDrop(SectionDrop):
    def __init__(self, section, column, widgets, container, triage):
        super().__init__(section, column, widgets, container, triage, held=True)
