# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Native, left-aligned column commands with no preselected action."""
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gdk, Gio, GLib, Gtk
from . import localization as ui
from .i18n import _
from .column_archiving import archive_action_title


def column_menu(window, stack, button=None):
    if button is None:
        button = ui.create(Gtk.MenuButton, icon_name='view-more-symbolic', tooltip_text=_("Opcions de la columna"))
    button.add_css_class('flat')
    group = Gio.SimpleActionGroup()
    button.insert_action_group('column', group)
    board = next((b for b in window.snapshot.get('boards', []) if b['id'] == window.board_id), {})
    model, create, commands, view = Gio.Menu(), Gio.Menu(), Gio.Menu(), Gio.Menu()
    active_count = sum(not card.get('archived') for card in stack.get('cards', []))
    actions = [
        ('new', _("Afegeix una targeta"), lambda: window.new_card(stack['id']), 'PERMISSION_EDIT', create),
        ('rename', _("Canvia el nom"), lambda: window.edit_column(stack), 'PERMISSION_MANAGE', commands),
        ('color', _("Canvia el color"), lambda: window.edit_column_color(stack), None, commands),
        ('archive-all', archive_action_title(active_count), lambda: window.archive_column_cards(stack), 'PERMISSION_EDIT', view),
        ('archives', _("Amaga les arxivades") if window.shows_archived(stack['id']) else _("Mostra les arxivades"),
         lambda: window.show_archived(stack['id'], not window.shows_archived(stack['id'])), None, view),
    ]
    for name, title, callback, permission, section in actions:
        action = Gio.SimpleAction.new(name, None)
        action.set_enabled(window.demo or not permission or board.get('permissions', {}).get(permission, True))
        if name == 'archive-all' and not active_count:
            action.set_enabled(False)
        action.connect('activate', lambda *_unused, callback=callback: callback())
        group.add_action(action)
        ui.menu_append(section, title, 'column.'+name)
    model.append_section(None, create)
    model.append_section(None, commands)
    model.append_section(None, view)
    popover = Gtk.PopoverMenu.new_from_model(model)
    button.set_popover(popover)
    popover.connect('map', lambda *_unused: setattr(window, '_open_column_menu', popover))
    popover.connect('closed', lambda *_unused: window.column_menu_closed(popover))
    def command_widgets(widget):
        if isinstance(widget, Gtk.Actionable) and widget.get_focusable():
            yield widget
        child = widget.get_first_child()
        while child:
            yield from command_widgets(child)
            child = child.get_next_sibling()
    def navigate(_keys, key, _code, modifiers):
        if not popover.get_child().has_focus() or key not in (Gdk.KEY_Down, Gdk.KEY_Up, Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab):
            return False
        items = [item for item in command_widgets(popover) if item.get_sensitive()]
        if not items:
            return False
        backwards = key in (Gdk.KEY_Up, Gdk.KEY_ISO_Left_Tab) or bool(modifiers & Gdk.ModifierType.SHIFT_MASK)
        return items[-1 if backwards else 0].grab_focus()
    keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
    keys.connect('key-pressed', navigate)
    popover.add_controller(keys)
    def focus_menu():
        if popover.get_mapped():
            content = popover.get_child()
            content.add_css_class('column-menu')
            content.set_focusable(True)
            content.grab_focus()
            # GtkPopoverMenu retains SELECTED on its first/previous model item
            # even after focus moves to the neutral container.
            def clear_selection(widget):
                widget.unset_state_flags(Gtk.StateFlags.SELECTED | Gtk.StateFlags.PRELIGHT | Gtk.StateFlags.ACTIVE)
                child = widget.get_first_child()
                while child:
                    clear_selection(child)
                    child = child.get_next_sibling()
            clear_selection(content)
        return GLib.SOURCE_REMOVE
    popover.connect('map', lambda *_unused: GLib.idle_add(focus_menu, priority=GLib.PRIORITY_LOW))
    return button
