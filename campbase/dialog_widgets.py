# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Shared spacing for custom dialog forms and native external-link rows."""
from gi.repository import Adw, GLib, Gtk
from . import localization as ui


def dialog_form(spacing=24, **properties):
    defaults = dict(orientation=Gtk.Orientation.VERTICAL, spacing=spacing,
                    margin_top=24, margin_bottom=24, margin_start=24, margin_end=24,
                    valign=Gtk.Align.START)
    return Gtk.Box(**(defaults | properties))


def external_row(title, uri, subtitle=None):
    row = ui.create(Adw.ActionRow, title=title,
                    subtitle=subtitle if subtitle is not None else uri.removeprefix('https://'),
                    tooltip_text=uri, activatable=True)
    row.add_suffix(Gtk.Image(icon_name='adw-external-link-symbolic'))
    row.connect('activated', lambda item: Gtk.UriLauncher.new(ui.render(uri)).launch(item.get_root(), None, None))
    return row


def scroll_to_widget(scroller, content, widget):
    def scroll():
        if not widget.get_mapped() or widget.get_height() == 0:
            return GLib.SOURCE_CONTINUE
        ok, bounds = widget.compute_bounds(content)
        if ok:
            adjustment = scroller.get_vadjustment()
            adjustment.set_value(max(adjustment.get_lower(), min(bounds.origin.y-12,
                adjustment.get_upper()-adjustment.get_page_size())))
        return GLib.SOURCE_REMOVE
    widget.add_tick_callback(lambda *_unused: scroll())


def fit_dialog_contents(dialog):
    """Recalculate natural height after asynchronous content changes."""
    if dialog.get_follows_content_size():
        return
    if getattr(dialog, '_fit_contents_idle', 0):
        return
    def resize():
        dialog._fit_contents_idle = 0
        if dialog.get_mapped():
            dialog.set_content_height(-1)
        return GLib.SOURCE_REMOVE
    dialog._fit_contents_idle = GLib.idle_add(resize)
