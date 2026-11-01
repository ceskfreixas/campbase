# SPDX-License-Identifier: GPL-3.0-or-later
"""Synthetic native dependency workflows never contact a Nextcloud account."""
import copy
import tempfile
import time
from types import SimpleNamespace
import gi
gi.require_version('Gtk', '4.0');gi.require_version('Adw', '1')
from gi.repository import Adw, GLib, Gtk
from campbase.deck import Deck
from campbase.card_dialog import CardDialog
from campbase.storage import Store
from campbase.window import Window


def settle(until=None):
    deadline = time.monotonic()+(6 if until else .2)
    while time.monotonic() < deadline:
        while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
        if until and until():return
        time.sleep(.005)
    if until:assert until()


class API(Deck):
    def __init__(self):
        super().__init__(SimpleNamespace(server='https://example.invalid', username='alice', password='dummy'))
        self.board = {'id': 1, 'title': 'Board', 'permissions': {'PERMISSION_EDIT': True}, 'labels': []}
        self.card = {'id': 3, 'boardId': 1, 'stackId': 2, 'title': 'Source', 'description': '- [ ] Task',
                     'dependentCards': [], 'assignedUsers': [], 'labels': []}
        self.target = dict(self.card, id=4, title='Target')
        self.writes = [];self.fetches = 0;self.delay = 0
    def get_card(self, *_):
        time.sleep(self.delay)
        return copy.deepcopy(self.card)
    def check_board(self, *_):return copy.deepcopy(self.board)
    def request(self, method, path, body=None, **kwargs):
        if method == 'GET':
            if path == '/cards/4':return self.target
            return []
        self.writes.append((method, path))
        self.card['dependentCards'] = [4] if method == 'POST' else []
        return copy.deepcopy(self.card)
    def fetch(self, **_):
        self.fetches += 1
        raise AssertionError('Dependency operations must not fetch the workspace')
    def comments(self, *_args, **_kwargs):return []
    def attachments(self, *_):return []


app = Adw.Application(application_id='cat.ceskfreixas.Campbase.DependenciesCheck');app.register(None)
with tempfile.TemporaryDirectory() as folder:
    store = Store(folder);store.set_setting('auto_sync', False)
    api = API()
    store.put('snapshot', {'boards': [api.board], 'stacks': {'1': [{'id': 2, 'title': 'Column', 'cards': [api.card, api.target]}]}})
    window = Window(app, store, True);window.set_default_size(1100,900);window.present();settle()
    window.demo = False;window.engine.api = api
    editor = CardDialog(window, 2, window.find_card(3));editor.present(window)
    panel = editor.dependencies
    settle(lambda: panel.supported and not panel.busy)
    assert panel.add.get_sensitive() and not panel.rows.get_visible()
    resources = panel.get_parent().get_parent()
    assert isinstance(resources, Gtk.FlowBox)
    assert editor.attachments.get_parent().get_parent() is resources
    _, left = panel.compute_bounds(resources)
    _, right = editor.attachments.compute_bounds(resources)
    assert abs(left.origin.y-right.origin.y)<1
    assert left.origin.x+left.size.width<=right.origin.x
    editor.attachments.display([{'id': 9, 'data': 'document' * 16 + '.pdf'}])
    window.set_default_size(520,900);settle()
    _, left = panel.compute_bounds(resources)
    _, right = editor.attachments.compute_bounds(resources)
    assert right.origin.y >= left.origin.y+left.size.height
    assert left.origin.x+left.size.width<=resources.get_width()+1
    assert right.origin.x+right.size.width<=resources.get_width()+1
    window.set_default_size(1100,900);settle()
    _, left = panel.compute_bounds(resources)
    _, right = editor.attachments.compute_bounds(resources)
    assert abs(left.origin.y-right.origin.y)<1
    editor.attachments.display([])


    editor.title_entry.set_text('Preserved title')
    editor.description.buffer.insert(editor.description.buffer.get_end_iter(), ' draft')
    description = editor.description.get_markdown()
    panel.choose();settle()
    chooser = window.get_visible_dialog()
    assert chooser is not editor
    chooser.force_close();settle()
    api.delay = .15
    panel.change(4, True)
    assert panel.writing and not editor.get_can_close() and not editor.save()
    settle(lambda: not panel.busy)
    assert panel.ids == [4] and panel.rows.get_first_child().get_title() == 'Target'
    assert editor.title_entry.get_text() == 'Preserved title'
    assert editor.description.get_markdown() == description and not editor.get_can_close()
    assert len(api.writes) == 1 and not api.fetches
    operation = store.enqueue('update', {'board_id': 1, 'stack_id': 2, 'card_id': 3,
                                        'changes': {'description': 'Pending draft'}, 'base': {'description': '- [ ] Task'}})
    panel.change(4, False);settle(lambda: not panel.busy)
    assert panel.ids == [4] and len(api.writes) == 1 and panel.status.get_visible()
    store.discard(operation)
    panel.change(4, False);settle(lambda: not panel.busy)
    assert not panel.ids and len(api.writes) == 2 and not api.fetches
    editor.force_close();settle()
    api.card.pop('dependentCards')
    editor = CardDialog(window, 2, window.find_card(3));editor.present(window)
    settle(lambda: not editor.dependencies.busy)
    assert not editor.dependencies.supported and not editor.dependencies.add.get_sensitive()
    assert editor.dependencies.status.get_visible()
    editor.force_close();settle()
    api.card['dependentCards'] = []
    api.board['permissions']['PERMISSION_EDIT'] = False
    store.cache_board(api.board);window.render();settle()
    editor = CardDialog(window, 2, window.find_card(3));editor.present(window)
    settle(lambda: not editor.dependencies.busy)
    assert not editor.dependencies.add.get_sensitive()
    before = len(api.writes)
    editor.dependencies.change(4, True)
    assert len(api.writes) == before
    editor.force_close();settle()
    window.close();settle()
print('PASS confirmed dependency links, preserved drafts, pending guards, old servers and read-only permissions')
