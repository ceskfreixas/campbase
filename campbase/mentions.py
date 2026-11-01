# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""A non-modal member completion list that keeps typing in the comment field."""
import re
from gi.repository import Gdk, GLib, Gtk, Pango
from .collaboration import members, mention_token
from .people import avatar
from .widgets import clear, label


def mention_fragment(text, position):
    position = len(text) if position < 0 else position
    return re.search(r"(?<![\w@])@([\w.@'\-]*)$", text[:position])


class MentionCompletion:
    def __init__(self, entry, window, board_id, insert):
        self.entry, self.window, self.board_id, self.insert = entry, window, board_id, insert
        self.popover = None
        self.matches = []
        self.scroll_retry = 0
        self.scroll_attempts = 0
        entry.connect('changed', self.changed)
        entry.connect('notify::cursor-position', self.changed)
        entry.connect('unrealize', self.dispose)
        self.keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        self.keys.connect('key-pressed', self.key_pressed)
        entry.add_controller(self.keys)
        focus = Gtk.EventControllerFocus()
        focus.connect('leave', lambda *_unused: self.hide())
        entry.add_controller(focus)

    def create_popup(self):
        self.popover = Gtk.Popover(autohide=False, has_arrow=False, position=Gtk.PositionType.RIGHT,
                                   valign=Gtk.Align.CENTER)
        self.popover.add_css_class('menu')
        self.popover.set_parent(self.entry)
        self.rows = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE, activate_on_single_click=True)
        self.rows.add_css_class('navigation-sidebar')
        self.rows.connect('row-activated', lambda _box, row: self.choose(row.get_index()))
        self.popover.set_child(Gtk.ScrolledWindow(child=self.rows,
            min_content_width=280, max_content_width=420, propagate_natural_width=True,
            max_content_height=260, propagate_natural_height=True,
            hscrollbar_policy=Gtk.PolicyType.NEVER))

    def changed(self, *_unused):
        if not self.entry.get_mapped():
            return
        fragment = mention_fragment(self.entry.get_text(), self.entry.get_position())
        if not fragment:
            self.hide()
            return
        if self.scroll_into_view():
            return
        query = fragment[1].casefold()
        board = next((b for b in self.window.snapshot.get('boards', []) if b['id'] == self.board_id), {})
        self.matches = []
        for user in members(board):
            if query not in (user['displayname']+' '+user['uid']).casefold():
                continue
            try:
                mention_token(user['uid'])
            except ValueError:
                continue
            self.matches.append(user)
        if not self.matches:
            self.hide()
            return
        if self.popover is None:
            self.create_popup()
        clear(self.rows)
        for user in self.matches:
            line = Gtk.Box(spacing=8, margin_top=6, margin_bottom=6, margin_start=8, margin_end=8)
            line.append(avatar(self.window, user, 24))
            names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            names.append(label(user['displayname'], xalign=0, wrap=True,
                               wrap_mode=Pango.WrapMode.WORD_CHAR, max_width_chars=32))
            names.append(label(user['uid'], 'caption', xalign=0, ellipsize=Pango.EllipsizeMode.END, max_width_chars=32))
            line.append(names)
            self.rows.append(line)
        self.rows.select_row(self.rows.get_row_at_index(0))
        self.position_popup(self.entry.get_position())
        self.popover.popup()
        self.entry.grab_focus_without_selecting()

    def scroll_into_view(self):
        scroller = self.entry.get_ancestor(Gtk.ScrolledWindow)
        if scroller is None:
            return False
        ok, bounds = self.entry.compute_bounds(scroller)
        if not ok:
            return False
        top, bottom = bounds.origin.y, bounds.origin.y+bounds.size.height
        if top >= 0 and bottom <= scroller.get_height():
            self.scroll_attempts = 0
            return False
        if self.scroll_attempts >= 3:
            return True
        adjustment = scroller.get_vadjustment()
        delta = top-12 if top < 0 else bottom-scroller.get_height()+12
        adjustment.set_value(max(adjustment.get_lower(), min(adjustment.get_value()+delta,
            adjustment.get_upper()-adjustment.get_page_size())))
        if not self.scroll_retry:
            self.scroll_attempts += 1
            def retry():
                self.scroll_retry = 0
                self.changed()
                return GLib.SOURCE_REMOVE
            self.scroll_retry = GLib.timeout_add(20, retry)
        return True

    def position_popup(self, position):
        """Anchor the list to the typed @, including horizontally scrolled text."""
        text = self.entry.get_delegate()
        strong, _weak = text.compute_cursor_extents(position)
        point = strong.get_top_left()
        ok, point = text.compute_point(self.entry, point)
        if ok:
            rectangle = Gdk.Rectangle()
            rectangle.x = max(0, min(self.entry.get_width(), round(point.x)))
            rectangle.y = round(point.y)
            rectangle.width = 1
            rectangle.height = max(1, round(strong.get_height()))
            self.popover.set_pointing_to(rectangle)

    def hide(self):
        self.scroll_attempts = 0
        if self.scroll_retry:
            GLib.source_remove(self.scroll_retry)
            self.scroll_retry = 0
        if self.popover:
            self.popover.popdown()

    def choose(self, index):
        if 0 <= index < len(self.matches):
            self.hide()
            self.insert(self.matches[index]['uid'])

    def key_pressed(self, _controller, key, _code, modifiers):
        if not self.popover or not self.popover.get_visible():
            return False
        if key == Gdk.KEY_Escape:
            self.hide()
            return True
        row = self.rows.get_selected_row()
        index = row.get_index() if row else 0
        if key in {Gdk.KEY_Down, Gdk.KEY_Up}:
            index = (index+(1 if key == Gdk.KEY_Down else -1)) % len(self.matches)
            self.rows.select_row(self.rows.get_row_at_index(index))
            return True
        if key in {Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_Tab} and not modifiers & Gdk.ModifierType.CONTROL_MASK:
            self.choose(index)
            return True
        return False

    def dispose(self, *_unused):
        self.hide()
        if self.popover:
            self.popover.popdown()
            self.popover.unparent()
            self.popover = None
