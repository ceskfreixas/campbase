# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Retain a visible card across rebuilds without overriding user navigation."""
from gi.repository import Gdk, Gtk


class ScrollPosition:
    def __init__(self, scroller, content):
        self.scroller, self.content = scroller, content
        self.context = None
        self.pending = None
        self.tick = 0
        self.frames = 0
        wheel = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.BOTH_AXES,
                                         propagation_phase=Gtk.PropagationPhase.CAPTURE)
        wheel.connect('scroll', self.user_scroll)
        scroller.add_controller(wheel)
        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed', self.user_key)
        scroller.add_controller(keys)
        click = Gtk.GestureClick(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        click.connect('pressed', lambda *_unused: self.cancel())
        scroller.get_vscrollbar().add_controller(click)

    def anchors(self, widget=None):
        widget = widget or self.content
        if widget.has_css_class('active-tile') or widget.has_css_class('archived-tile'):
            yield ('card', widget.card['id']), widget
            return
        if widget.has_css_class('board-column'):
            yield ('column', widget.stack['id']), widget
        child = widget.get_first_child()
        while child:
            yield from self.anchors(child)
            child = child.get_next_sibling()

    def capture(self):
        adjustment = self.scroller.get_vadjustment()
        position, page = adjustment.get_value(), adjustment.get_page_size()
        candidates = []
        for key, widget in self.anchors():
            ok, bounds = widget.compute_bounds(self.content)
            if ok and bounds.origin.y+bounds.size.height > position and bounds.origin.y < position+page:
                offset = bounds.origin.y-position
                candidates.append((key[0] != 'card', abs(offset), key, offset))
        anchor = min(candidates)[2:] if candidates else None
        return position, anchor

    def prepare(self, context):
        if context != self.context:
            self.cancel()
            self.pending = (0, None)
        elif self.pending is None:
            self.pending = self.capture()
        self.context = context

    def restore(self):
        self.frames = 0
        if not self.tick:
            self.tick = self.content.add_tick_callback(self.after_layout)

    def after_layout(self, _widget, _clock):
        # Tick callbacks precede allocation. Wait through one layout frame.
        self.frames += 1
        if self.frames < 2 or not self.content.get_mapped():
            return True
        position, anchor = self.pending
        if anchor:
            key, offset = anchor
            for current, widget in self.anchors():
                if current == key:
                    ok, bounds = widget.compute_bounds(self.content)
                    if ok:
                        position = bounds.origin.y-offset
                    break
        adjustment = self.scroller.get_vadjustment()
        limit = max(adjustment.get_lower(), adjustment.get_upper()-adjustment.get_page_size())
        adjustment.set_value(max(adjustment.get_lower(), min(position, limit)))
        self.tick = 0
        self.pending = None
        return False

    def cancel(self):
        if self.tick:
            self.content.remove_tick_callback(self.tick)
            self.tick = 0
        self.pending = None

    def user_scroll(self, *_unused):
        self.cancel()
        return False

    def user_key(self, _controller, key, _code, _modifiers):
        if key in (Gdk.KEY_Up, Gdk.KEY_Down, Gdk.KEY_Page_Up, Gdk.KEY_Page_Down,
                   Gdk.KEY_Home, Gdk.KEY_End, Gdk.KEY_space):
            self.cancel()
        return False
