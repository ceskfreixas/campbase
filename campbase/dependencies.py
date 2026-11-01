# SPDX-License-Identifier: GPL-3.0-or-later
"""On-demand dependency controls sharing the serialized Deck worker."""
from gi.repository import Adw, Gtk
from . import localization as ui
from .i18n import _
from .widgets import label, icon_button, clear
from .card_dependencies import dependency_ids
from .deck import ConflictError, DeckError, ServiceUnavailable
from .detail_reads import DetailReads


class DependenciesPanel(Gtk.Box):
    def __init__(self, window, dialog, board, card):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.window, self.dialog, self.board, self.card = window, dialog, board, card
        self.api = window.engine.api
        self.reads = DetailReads(window.engine)
        self.closed, self.busy, self.supported, self.writing = False, False, False, False
        self.ids = []
        header = Gtk.Box(spacing=8)
        header.append(label(_("Targetes dependents"), 'heading', xalign=0, hexpand=True))
        self.add = icon_button('list-add-symbolic', _("Afegeix una dependència"), self.choose)
        self.reload = icon_button('view-refresh-symbolic', _("Actualitza les dependències"), self.load)
        self.spinner = Gtk.Spinner(visible=False)
        header.append(self.spinner)
        header.append(self.add);header.append(self.reload)
        self.append(header)
        self.status = label('', 'dim-label', xalign=0, wrap=True)
        self.append(self.status)
        self.rows = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.rows.add_css_class('boxed-list')
        self.append(self.rows)
        dialog.connect('closed', lambda *_unused: setattr(self, 'closed', True))
        dialog.connect('closed', self.reads.close)
        try:
            dependency_ids(card)
        except DeckError:
            pass
        else:
            self.display(card)
        self.load()

    def current(self):
        return not self.closed and not self.window.engine.account_changing and self.api is self.window.engine.api

    def editable(self):
        board = next((item for item in self.window.snapshot['boards'] if item['id'] == self.board['id']), {})
        card = self.window.find_card(self.card['id']) or self.card
        return (not card.get('archived') and not card.get('deletedAt') and not board.get('archived')
                and not board.get('deletedAt') and (self.window.demo or board.get('permissions', {}).get('PERMISSION_EDIT', False)))

    def controls(self):
        self.add.set_sensitive(self.supported and self.editable() and not self.busy)
        self.reload.set_sensitive(not self.busy)
        self.rows.set_sensitive(not self.busy)

    def run(self, action, done, *, writing=False):
        if self.busy or not self.current():
            return
        self.busy, self.writing = True, writing
        self.spinner.set_visible(True)
        self.spinner.start()
        self.controls()
        if writing:
            self.dialog.save_button.set_sensitive(False)
            self.dialog.set_can_close(False)
        def finished(result, error):
            if not self.current():
                return
            self.busy, self.writing = False, False
            self.spinner.stop()
            self.spinner.set_visible(False)
            if writing:
                self.dialog.save_button.set_sensitive(self.editable())
                self.dialog.changed()
            self.controls()
            ui.text(self.status, 'text', error or '')
            self.status.set_visible(bool(error))
            if not error:
                done(result)
        runner = self.window.engine.run if writing else self.reads.run
        if runner(action, finished) is None:
            finished(None, _("Connecta el compte de Nextcloud."))

    def load(self, *_unused):
        self.reads.bind()
        if self.api is None:
            self.api = self.reads.api
        if self.busy:
            return
        if self.window.demo:
            self.display(dict(self.card, dependentCards=self.card.get('dependentCards', [])))
            return
        self.status.set_visible(True)
        ui.text(self.status, 'text', _("S'estan carregant les dependències…"))
        def read(api):
            try:
                return api.card_dependencies(self.board['id'], self.card['stackId'], self.card['id'])
            except ServiceUnavailable:
                return None
        def loaded(card):
            if card is None:
                self.supported = False
                self.controls()
                ui.text(self.status, 'text', _("Aquest servidor encara no admet les dependències de targetes."))
                self.status.set_visible(True)
            else:
                self.display(card)
        self.run(read, loaded)

    def display(self, card):
        self.ids = dependency_ids(card)
        self.supported = True
        self.card['dependentCards'] = self.ids
        self.window.store.cache_card_dependencies(self.board['id'], card)
        current = self.window.find_card(self.card['id'])
        if current is not None:
            current['dependentCards'] = list(self.ids)
        clear(self.rows)
        self.rows.set_visible(bool(self.ids))
        ui.text(self.status, 'text', _("Encara no hi ha dependències.") if not self.ids else '')
        self.status.set_visible(not self.ids)
        known = {item['id']: item for item, _ in self.candidates()}
        for card_id in self.ids:
            item = known.get(card_id, {'id': card_id})
            title = item.get('title') or '#'+str(card_id)
            row = Adw.ActionRow(title=title, tooltip_text=title, use_markup=False)
            row.set_title_lines(2)
            open_button = icon_button('adw-external-link-symbolic', _("Obre la targeta"), lambda *_unused, item=item: self.open(item))
            remove = icon_button('list-remove-symbolic', _("Treu la dependència"), lambda *_unused, key=card_id: self.change(key, False))
            remove.set_sensitive(self.editable())
            for button in (open_button, remove):
                button.set_valign(Gtk.Align.CENTER)
                row.add_suffix(button)
            self.rows.append(row)
        self.controls()

    def candidates(self):
        snapshot = self.window.store.view()
        boards = {str(item['id']): item for item in snapshot.get('boards', []) if not item.get('deletedAt')}
        return [(card, boards[key].get('title', '')) for key, stacks in snapshot.get('stacks', {}).items()
                if key in boards for stack in stacks if not stack.get('deletedAt')
                for card in stack.get('cards', []) if card['id'] > 0 and not card.get('deletedAt')]

    def choose(self, *_unused):
        if not self.add.get_sensitive() or not self.current():
            return
        chooser = Adw.Dialog(content_width=440, follows_content_size=True)
        ui.widget(chooser, title=_("Afegeix una dependència"))
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.append(Adw.HeaderBar())
        form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                       margin_start=18, margin_end=18, margin_top=12, margin_bottom=18)
        search = ui.create(Gtk.SearchEntry, placeholder_text=_("Cerca una targeta…"))
        form.append(search)
        rows = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        rows.add_css_class('boxed-list')
        form.append(Gtk.ScrolledWindow(child=rows, propagate_natural_height=True,
                                       max_content_height=320, hscrollbar_policy=Gtk.PolicyType.NEVER))
        def refresh(*_unused):
            clear(rows)
            query = search.get_text().strip().casefold()
            choices = [(item, title) for item, title in self.candidates()
                       if item['id'] != self.card['id'] and item['id'] not in self.ids
                       and query in (item.get('title', '')+' '+title).casefold()]
            for item, title in choices[:50]:
                row = Adw.ActionRow(title=item.get('title', ''), subtitle=title, use_markup=False, activatable=True)
                row.set_title_lines(2)
                row.connect('activated', lambda *_unused, key=item['id']: (chooser.force_close(), self.change(key, True)))
                rows.append(row)
            if not choices:
                rows.append(label(_("No s'ha trobat cap targeta."), 'dim-label', xalign=0, wrap=True))
        search.connect('search-changed', refresh)
        refresh()
        outer.append(form);chooser.set_child(outer);chooser.present(self.dialog)

    def change(self, target_id, present):
        if self.busy or not self.current() or not self.supported or not self.editable():
            return
        if self.window.demo:
            values = set(self.ids)
            values.add(target_id) if present else values.discard(target_id)
            self.display(dict(self.card, dependentCards=sorted(values)))
            return
        ui.text(self.status, 'text', _("S'està desant la dependència…"))
        self.status.set_visible(True)
        def action(api):
            if any(op['payload'].get('card_id') == self.card['id'] for op in self.window.store.operations()):
                raise ConflictError(_("Sincronitza els canvis pendents d'aquesta targeta abans de modificar-ne les dependències."))
            result = api.set_card_dependency(self.board['id'], self.card['stackId'], self.card['id'], target_id, present)
            if api is self.window.engine.api and not self.window.engine.account_changing:
                self.window.store.cache_card_dependencies(self.board['id'], result)
            return result
        self.run(action, self.display, writing=True)

    def open(self, item):
        if not self.current():
            return
        local = self.window.find_card(item['id'])
        if local and self.window.board_id == self.board['id']:
            from .card_dialog import CardDialog
            CardDialog(self.window, local['stackId'], local).present(self.dialog)
        elif self.window.account:
            Gtk.UriLauncher.new(f'{self.window.account.server}/index.php/apps/deck/card/{item["id"]}').launch(self.window, None, None)
