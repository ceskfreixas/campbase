# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""On-demand, board-scoped recovery without polling or full workspace reloads."""
from datetime import datetime
from gi.repository import Adw, Gtk
from . import localization as ui
from .i18n import _
from .dialog_widgets import dialog_form, fit_dialog_contents
from .widgets import label, icon_button, clear
from .trash_recovery import load_deleted_items, restore_deleted_card, restore_deleted_stack


class BoardTrashDialog(Adw.Dialog):
    def __init__(self, window, board):
        super().__init__(content_width=560)
        ui.widget(self, title=_("Elements esborrats"))
        self.window, self.board = window, dict(board)
        self.api = window.engine.api
        self.active, self.busy, self.generation = True, False, 0
        self.items, self.columns = [], []
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.content_box = outer
        header = Adw.HeaderBar()
        self.refresh = icon_button('view-refresh-symbolic', _("Actualitza"), lambda *_: self.load())
        header.pack_start(self.refresh)
        outer.append(header)
        self.form = dialog_form(spacing=16)
        self.form.append(label(board['title'], 'title-3', xalign=0, wrap=True))
        self.form.append(label(_("Pots restaurar targetes i columnes mentre Nextcloud encara les conservi."),
                               'dim-label', xalign=0, wrap=True))
        self.spinner = Gtk.Spinner(width_request=24, height_request=24, halign=Gtk.Align.CENTER)
        self.form.append(self.spinner)
        self.status = label('', 'dim-label', xalign=0, wrap=True)
        self.form.append(self.status)
        self.column_heading = label(_("Columnes"), 'heading', xalign=0, visible=False)
        self.form.append(self.column_heading)
        self.column_rows = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, visible=False)
        self.column_rows.add_css_class('boxed-list')
        self.form.append(self.column_rows)
        self.card_heading = label(_("Targetes"), 'heading', xalign=0, visible=False)
        self.form.append(self.card_heading)
        self.rows = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.rows.add_css_class('boxed-list')
        self.rows.set_visible(False)
        self.form.append(self.rows)
        outer.append(Gtk.ScrolledWindow(child=self.form, propagate_natural_height=True,
            max_content_height=520, hscrollbar_policy=Gtk.PolicyType.NEVER))
        self.set_child(outer)
        self.connect('closed', self.closed)
        self.load()

    def closed(self, *_unused):
        self.active = False
        self.generation += 1

    def current(self):
        return self.active and self.api is self.window.engine.api

    def set_busy(self, busy):
        self.busy = busy
        self.refresh.set_sensitive(not busy)
        self.rows.set_sensitive(not busy)
        self.column_rows.set_sensitive(not busy)
        self.spinner.set_visible(busy)
        self.spinner.set_spinning(busy)

    def show_status(self, text):
        ui.text(self.status, 'text', text)
        self.status.set_visible(bool(text))
        fit_dialog_contents(self)

    def load(self):
        if self.busy or not self.current():
            return
        self.generation += 1
        generation = self.generation
        self.set_busy(True)
        self.show_status(_("S'està carregant…"))
        def done(items, error):
            if not self.current() or generation != self.generation:
                return
            self.set_busy(False)
            if error:
                self.show_status(error)
            else:
                self.items, self.columns = items['cards'], items['columns']
                self.display()
        if self.window.engine.run(lambda api: load_deleted_items(api, self.board['id']), done) is None:
            self.set_busy(False)
            self.show_status(_("Connecta el compte de Nextcloud."))

    def display(self):
        clear(self.rows)
        clear(self.column_rows)
        stacks = self.window.snapshot.get('stacks', {}).get(str(self.board['id']), [])
        names = {stack['id']: stack['title'] for stack in stacks}
        board = next((board for board in self.window.snapshot.get('boards', [])
                      if board['id'] == self.board['id']), {})
        allowed = bool(board) and not board.get('archived') and board.get('permissions', {}).get('PERMISSION_EDIT', False)
        manage = bool(board) and not board.get('archived') and board.get('permissions', {}).get('PERMISSION_MANAGE', False)
        for stack in self.columns:
            row, button = self.recovery_row(stack, '', lambda *_, stack=stack: self.restore_column(stack))
            button.set_sensitive(manage)
            self.column_rows.append(row)
        self.column_heading.set_visible(bool(self.columns))
        self.column_rows.set_visible(bool(self.columns))
        self.card_heading.set_visible(bool(self.items))
        deleted_names = {stack['id']: stack['title'] for stack in self.columns}
        for card in self.items:
            column = names.get(card['stackId'], deleted_names.get(card['stackId'], _("Columna no disponible")))
            row, button = self.recovery_row(card, column, lambda *_, card=card: self.restore(card))
            button.set_sensitive(allowed and card['stackId'] in names)
            self.rows.append(row)
        self.rows.set_visible(bool(self.items))
        self.show_status('' if self.items or self.columns else _("No hi ha elements esborrats."))

    def recovery_row(self, item, prefix, callback):
        try:
            when = datetime.fromtimestamp(item['deletedAt']).astimezone().strftime('%x · %H:%M')
        except (ValueError, OverflowError, OSError):
            when = ''
        row = Adw.ActionRow(title=item.get('title') or str(item['id']),
                            subtitle=' · '.join(part for part in (prefix, when) if part), use_markup=False)
        button = icon_button('edit-undo-symbolic', _("Restaura"), callback)
        button.set_valign(Gtk.Align.CENTER)
        button.set_margin_top(8);button.set_margin_bottom(8)
        row.add_suffix(button)
        return row, button

    def restore(self, card):
        self.start_restore('card', card)

    def restore_column(self, stack):
        self.start_restore('column', stack)

    def start_restore(self, kind, item):
        if self.busy or not self.current():
            return
        self.set_busy(True)
        self.set_can_close(False)
        self.show_status(_("S'està restaurant…"))
        def done(result, error):
            self.set_can_close(True)
            if not self.current():
                return
            self.set_busy(False)
            if error:
                self.show_status(error)
                return
            if kind == 'card':
                cached = self.window.store.cache_restored_card(self.board['id'], result)
                self.items = [card for card in self.items if card['id'] != item['id']]
            else:
                cached = self.window.store.cache_restored_stack(self.board['id'], result)
                self.columns = [stack for stack in self.columns if stack['id'] != item['id']]
            self.window.render()
            self.display()
            if not cached:
                self.window.engine.sync(read_only=True)
        action = restore_deleted_card if kind == 'card' else restore_deleted_stack
        if self.window.engine.run(lambda api: action(api, self.window.store, self.board['id'], item), done) is None:
            self.set_can_close(True)
            self.set_busy(False)
            self.show_status(_("Connecta el compte de Nextcloud."))
