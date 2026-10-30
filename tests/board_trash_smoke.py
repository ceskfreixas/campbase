# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Native trash loading, retry, restoration and close races use synthetic data."""
import copy
from pathlib import Path
import campbase
import tempfile
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock
import gi
gi.require_version('Gtk', '4.0');gi.require_version('Adw', '1')
from gi.repository import Adw, GLib, Gdk, Gtk
from campbase.__main__ import demo_snapshot
from campbase.storage import Store
from campbase.window import Window
from campbase.board_trash import BoardTrashDialog
from campbase.deck import OfflineError
from gui_helpers import wait_until, wait_presented


def settle():
    end = time.monotonic()+.2
    while time.monotonic() < end:
        while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
        time.sleep(.005)


app = Adw.Application(application_id='cat.ceskfreixas.Campbase.TrashCheck');app.register(None)
css = Gtk.CssProvider();css.load_from_path(str(Path(campbase.__file__).parent/'style.css'))
Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
with tempfile.TemporaryDirectory() as directory:
    store = Store(directory);store.set_setting('auto_sync', False)
    snapshot = demo_snapshot();board = snapshot['boards'][0]
    board['permissions'] = {'PERMISSION_EDIT': True, 'PERMISSION_MANAGE': True}
    stack = snapshot['stacks'][str(board['id'])][0]
    card = dict(copy.deepcopy(stack['cards'][0]), id=999, deletedAt=1700000000, archived=True)
    store.put('snapshot', snapshot)
    window = Window(app, store, True);window.present();settle()
    release = threading.Event()
    api = SimpleNamespace(server='https://cloud.example.invalid', username='test')
    api.deleted_cards = Mock(side_effect=lambda _board: (release.wait(5), [card])[1])
    api.deleted_stacks = Mock(return_value=[])
    api.restore_card = Mock(return_value=card | {'deletedAt': 0})
    window.engine.api = api
    dialog = BoardTrashDialog(window, board);dialog.present(window);wait_presented(dialog)
    assert dialog.spinner.get_spinning() and dialog.busy
    assert dialog.content_box.get_width() >= 500, dialog.content_box.get_width()
    release.set();wait_until(lambda: not dialog.busy)
    assert dialog.rows.get_first_child().get_subtitle().startswith(stack['title'])
    assert dialog.explanation.get_visible()
    before = len(store.view()['stacks'][str(board['id'])][0]['cards'])
    dialog.restore(card);wait_until(lambda: not dialog.busy)
    assert dialog.items == [] and dialog.status.get_label() == 'No hi ha elements esborrats.'
    assert not dialog.explanation.get_visible()
    assert len(store.view()['stacks'][str(board['id'])][0]['cards']) == before+1
    assert window.find_card(999)['archived']
    api.restore_card.assert_called_once_with(board['id'], stack['id'], 999)
    api.deleted_cards.side_effect = OfflineError('offline')
    dialog.load();wait_until(lambda: not dialog.busy)
    assert dialog.refresh.get_sensitive() and dialog.status.get_label() == 'offline'
    api.deleted_cards.side_effect = lambda _board: []
    dialog.load();wait_until(lambda: not dialog.busy)
    assert dialog.status.get_label() == 'No hi ha elements esborrats.'
    dialog.force_close();settle()
    column = {'id': 987, 'boardId': board['id'], 'title': 'Deleted column', 'order': 5,
              'deletedAt': 1700000000, 'cards': [dict(card, id=1001, stackId=987, archived=False, deletedAt=0),
                                               dict(card, id=1002, stackId=987, archived=True, deletedAt=0)]}
    api.deleted_stacks.return_value = [column]
    api.restore_stack = Mock(return_value=column | {'deletedAt': 0})
    columns = BoardTrashDialog(window, board);columns.present(window);wait_presented(columns)
    wait_until(lambda: not columns.busy)
    assert columns.column_heading.get_visible() and columns.column_rows.get_first_child()
    columns.restore_column(column);wait_until(lambda: not columns.busy)
    assert columns.columns == []
    assert [card['archived'] for card in window.cards_in_stack(987)] == [False, True]
    api.restore_stack.assert_called_once_with(board['id'], 987)
    columns.force_close();settle();api.deleted_stacks.return_value = []
    store.enqueue('update', {'board_id': board['id'], 'stack_id': stack['id'], 'card_id': 999,
                            'changes': {'title': 'Draft'}})
    api.deleted_cards.side_effect = lambda _board: [card]
    blocked = BoardTrashDialog(window, board);blocked.present(window);wait_presented(blocked)
    wait_until(lambda: not blocked.busy)
    blocked.restore(card);wait_until(lambda: not blocked.busy)
    assert api.restore_card.call_count == 1
    assert store.operations()
    blocked.force_close();settle()
    release.clear()
    api.deleted_cards.side_effect = lambda _board: (release.wait(5), [card])[1]
    closed = BoardTrashDialog(window, board);closed.present(window);wait_presented(closed)
    closed.force_close();settle();release.set();settle()
    assert not closed.active and closed.items == []
    for width in [720, 380]:
        window.set_default_size(width, 900);settle()
        sized = BoardTrashDialog(window, board);sized.present(window);wait_presented(sized)
        wait_until(lambda: not sized.busy);settle()
        assert sized.content_box.get_width() <= window.get_width()
        if width == 720:assert sized.content_box.get_width() >= 500
        row = sized.rows.get_first_child()
        if row:assert row.get_width() <= sized.content_box.get_width()-48
        sized.force_close();settle()
    window.close();settle()
print('PASS trash loading, empty state, retry, incremental restore, drafts and closed-dialog race')
