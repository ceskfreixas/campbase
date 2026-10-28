# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Theme-aware mention attributes without interpreting comment text as markup."""
import re
import weakref
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, GLib, Gtk, Pango
from .collaboration import members, mention_token


def board_tokens(window, board_id):
    board = next((b for b in window.snapshot.get('boards', []) if b['id'] == board_id), {})
    tokens = []
    for user in members(board):
        try:
            tokens.append(mention_token(user['uid']))
        except ValueError:
            tokens.append('@'+user['uid'])
    return tokens


def mention_spans(text, tokens):
    alternatives = '|'.join(re.escape(token) for token in sorted(set(tokens), key=len, reverse=True) if token)
    if not alternatives:
        return []
    pattern = r"(?<![\w@])(?:"+alternatives+r")(?![\w@'/-]|\.[\w@])"
    return [(len(text[:match.start()].encode('utf-8')), len(text[:match.end()].encode('utf-8')))
            for match in re.finditer(pattern, text)]


class MentionStyle:
    def __init__(self, widget, tokens):
        self.widget = weakref.ref(widget, self.disconnect)
        self.tokens = tokens
        self.handlers = []
        self.idle = 0
        widget.connect('map', self.mapped)
        widget.connect('unmap', self.disconnect)
        widget.connect('changed' if isinstance(widget, Gtk.Entry) else 'notify::label', self.update)
        self.update()

    def mapped(self, *_unused):
        self.disconnect()
        manager = Adw.StyleManager.get_default()
        for name in ('dark', 'high-contrast', 'accent-color'):
            if manager.find_property(name):
                self.handlers.append((manager, manager.connect('notify::'+name, self.queue_update)))
        self.update()

    def disconnect(self, *_unused):
        for manager, handler in self.handlers:
            manager.disconnect(handler)
        self.handlers.clear()
        if self.idle:
            GLib.source_remove(self.idle)
            self.idle = 0

    def queue_update(self, *_unused):
        if not self.idle:
            self.idle = GLib.idle_add(self.update)

    def update(self, *_unused):
        self.idle = 0
        widget = self.widget()
        if widget is None:
            return GLib.SOURCE_REMOVE
        attributes = Pango.AttrList()
        found, color = widget.get_style_context().lookup_color('accent_color')
        if found:
            for start, end in mention_spans(widget.get_text(), self.tokens):
                channels = [round(max(0, min(1, value))*65535) for value in (color.red, color.green, color.blue)]
                attr = Pango.attr_foreground_new(*channels)
                attr.start_index, attr.end_index = start, end
                attributes.insert(attr)
        widget.set_attributes(attributes)
        return GLib.SOURCE_REMOVE
