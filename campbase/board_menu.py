# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Compact sidebar actions keep recovery separate from deleting a board."""
from gi.repository import GLib, Gtk
from . import localization as ui
from .i18n import _
from .board_deletion import BoardDeletionDialog, is_board_owner
from .board_trash import BoardTrashDialog
from .widgets import label


def board_options_button(window, board):
    button = ui.create(Gtk.MenuButton, icon_name='view-more-symbolic',
                       tooltip_text=_("Opcions del tauler"), valign=Gtk.Align.CENTER)
    button.add_css_class('flat')
    button.add_css_class('hover-action')
    popover = Gtk.Popover()
    popover.add_css_class('menu')
    popover.add_css_class('board-options-menu')
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                  margin_top=6, margin_bottom=6, margin_start=6, margin_end=6)
    popover.set_child(box)
    button.set_popover(popover)
    pending = []
    def focus_changed(*_unused):
        if button.has_visible_focus() or button.get_first_child().has_visible_focus():
            button.add_css_class('keyboard-actions')
        else:
            button.remove_css_class('keyboard-actions')
    button.connect('state-flags-changed', focus_changed)
    button.get_first_child().connect('state-flags-changed', focus_changed)
    popover.connect('map', lambda *_: button.add_css_class('menu-open'))

    def open_after_close(callback):
        pending[:] = [callback]
        popover.popdown()

    def closed(*_unused):
        button.remove_css_class('menu-open')
        if pending:
            callback = pending.pop()
            def present():
                if not window.engine.closed:
                    callback()
                return GLib.SOURCE_REMOVE
            GLib.idle_add(present)
    popover.connect('closed', closed)
    recover = Gtk.Button()
    recover.set_child(label(_("Elements esborrats"), xalign=0))
    recover.add_css_class('flat')
    recover.add_css_class('board-menu-action')
    recover.set_sensitive(window.engine.api is not None)
    recover.connect('clicked', lambda *_: open_after_close(lambda: BoardTrashDialog(window, board).present(window)))
    box.append(recover)
    if is_board_owner(window, board):
        box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        remove = Gtk.Button()
        remove.add_css_class('flat')
        remove.add_css_class('board-menu-action')
        remove.add_css_class('destructive-action')
        content = Gtk.Box(spacing=8)
        content.append(Gtk.Image(icon_name='user-trash-symbolic'))
        content.append(label(_("Esborra el tauler"), xalign=0))
        remove.set_child(content)
        remove.connect('clicked', lambda *_: open_after_close(lambda: BoardDeletionDialog(window, board).present(window)))
        box.append(remove)
    return button
