# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Background synchronization must preserve open menus and assignee widgets."""
import copy
import tempfile
import time
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, GLib, Gtk
from campbase.storage import Store
from campbase.window import Window

app = Adw.Application(application_id='cat.ceskfreixas.Campbase.SyncInteractionCheck')
app.register(None)


def settle():
    deadline = time.monotonic()+.3
    while time.monotonic() < deadline:
        while GLib.MainContext.default().pending():
            GLib.MainContext.default().iteration(False)
        time.sleep(.005)


with tempfile.TemporaryDirectory() as directory:
    store = Store(directory)
    store.set_setting('auto_sync', False)
    store.set_archived_default(True)
    user = {'participant': {'uid': 'alice', 'displayname': 'Alícia Miró'}}
    cards = [{'id': key, 'stackId': 10, 'title': f'Targeta {key}', 'order': key,
              'archived': key == 2, 'assignedUsers': [user]} for key in (1, 2)]
    snapshot = {'boards': [{'id': 1, 'title': 'Prova'}],
                'stacks': {'1': [{'id': 10, 'title': 'Columna', 'cards': cards}]}}
    store.put('snapshot', snapshot)
    window = Window(app, store, True)
    window.present()
    settle()
    column = window.board_body.get_first_child().get_next_sibling()
    menu = column.get_first_child().get_last_child()
    avatars = [column.drop.widgets[0].assignee_avatars, column.archived_section.cards[0].assignee_avatars]
    menu.popup()
    settle()
    popover = menu.get_popover()
    for busy in (True, False, True):
        window.engine.busy = busy
        window.sync_changed()
        settle()
        assert popover.get_mapped()
        assert column.drop.widgets[0].assignee_avatars is avatars[0]
        assert column.archived_section.cards[0].assignee_avatars is avatars[1]
    changed = copy.deepcopy(snapshot)
    changed['stacks']['1'][0]['cards'][0]['title'] = 'Actualitzada mentre el menú és obert'
    store.put('snapshot', changed)
    window.sync_changed()
    settle()
    assert popover.get_mapped() and window._render_after_menu
    menu.popdown()
    settle()
    assert not window._render_after_menu and window._open_column_menu is None
    assert window.find_card(1)['title'] == changed['stacks']['1'][0]['cards'][0]['title']
    column = window.board_body.get_first_child().get_next_sibling()
    window.set_focus(None)
    for tile in (column.drop.widgets[0], column.archived_section.cards[0]):
        assert tile.assignee_avatars is not None
        tile.card_widget.set_state_flags(Gtk.StateFlags.FOCUSED, False)
        tile.card_widget.unset_state_flags(Gtk.StateFlags.FOCUS_VISIBLE)
        assert not tile.has_css_class('keyboard-actions')
    window.close()
    settle()
print('PASS open column menu, deferred refresh, stable avatars and pointer versus keyboard focus')
