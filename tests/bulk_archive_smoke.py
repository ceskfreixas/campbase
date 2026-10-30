# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Native confirmation keeps all-column scope explicit even with filters."""
import copy
import tempfile
import time
import gi
gi.require_version('Gtk', '4.0');gi.require_version('Adw', '1')
from gi.repository import Adw, GLib
from campbase.__main__ import demo_snapshot
from campbase.storage import Store
from campbase.window import Window
from gui_helpers import wait_presented


def settle():
    end = time.monotonic()+.2
    while time.monotonic() < end:
        while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
        time.sleep(.005)


app = Adw.Application(application_id='cat.ceskfreixas.Campbase.BulkArchiveCheck');app.register(None)
with tempfile.TemporaryDirectory() as directory:
    store = Store(directory);store.set_setting('auto_sync', False)
    snapshot = demo_snapshot()
    stack = snapshot['stacks']['1'][0]
    card = copy.deepcopy(stack['cards'][0])
    card['assignedUsers'] = [{'participant': {'uid': 'test'}}]
    stack['cards'] = [dict(card, id=700+i, title='Targeta '+str(i), archived=i==3) for i in range(4)]
    store.put('snapshot', snapshot)
    window = Window(app, store, True);window.present();settle()
    window.query = 'no matching card';window.only_mine = True;window.render();settle()
    prompt = window.archive_column_cards(stack);wait_presented(prompt)
    assert '3' in prompt.get_body() and stack['title'] in prompt.get_body()
    assert prompt.get_default_response() == 'cancel'
    prompt.emit('response', 'cancel');prompt.force_close();settle()
    assert not store.operations()
    prompt = window.archive_column_cards(stack);wait_presented(prompt)
    snapshot['stacks']['1'][0]['cards'].append(dict(card, id=999, archived=False))
    store.put('snapshot', snapshot)
    prompt.emit('response', 'archive');prompt.force_close();settle()
    assert {operation['payload']['card_id'] for operation in store.operations()} == {700, 701, 702}
    cards = store.view()['stacks']['1'][0]['cards']
    assert all(card['archived'] for card in cards if card['id'] != 999)
    assert not next(card for card in cards if card['id'] == 999)['archived']
    assert next(card for card in cards if card['id'] == 700)['assignedUsers'] == stack['cards'][0]['assignedUsers']
    window.close();settle()
print('PASS archive confirmation, cancel, filters, fixed selection, assignments and durable outbox')
