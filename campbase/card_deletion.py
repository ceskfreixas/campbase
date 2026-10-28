# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Explicit archived-card deletion with bounded scope and confirmed progress."""
import threading
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gtk
from . import localization as ui
from .i18n import _
from .deck import ConflictError
from .dialog_widgets import dialog_form
from .widgets import label
from .alerts import message


def delete_archived_batch(api, store, board_id, stack_id, cards, stopped):
    selected = {card['id']: card for card in cards}
    for card_id in selected:
        if stopped.is_set():
            return
        if any(operation['payload'].get('card_id') in selected for operation in store.operations()):
            raise ConflictError(_("Resol els canvis pendents d'aquestes targetes abans d'esborrar-les."))
        api.delete_archived_card(board_id, stack_id, card_id)
        store.remove_card(board_id, card_id)
        yield card_id


class CardDeletionDialog(Adw.Dialog):
    def __init__(self, window, stack, cards, after=None):
        super().__init__(content_width=420, follows_content_size=True)
        self.window, self.stack = window, stack
        self.board_id = window.board_id
        self.cards = [dict(card) for card in cards if card.get('archived') and card['id'] > 0]
        ui.widget(self, title=_("Esborra la targeta") if len(self.cards) == 1 else _("Esborra les targetes arxivades"))
        self.after = after
        self.stopped = threading.Event()
        self.started = False
        self.deleted = 0
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, width_request=420)
        header = Adw.HeaderBar()
        self.action = ui.create(Gtk.Button, label=_("Esborra"))
        self.action.add_css_class('destructive-action')
        self.action.connect('clicked', lambda *_unused: self.stop() if self.started else self.start())
        header.pack_end(self.action)
        outer.append(header)
        form = dialog_form()
        form.append(label(stack['title'], 'title-3', xalign=0, wrap=True))
        form.append(label(_("Targetes arxivades: {count}").format(count=len(self.cards)), xalign=0))
        form.append(label(_("S'esborraran aquestes targetes de Nextcloud Deck. Les targetes actives es conservaran."), xalign=0, wrap=True))
        for card in self.cards[:5]:
            form.append(label(card['title'], 'dim-label', xalign=0, wrap=True))
        self.spinner = Gtk.Spinner(spinning=False, visible=False, halign=Gtk.Align.CENTER)
        form.append(self.spinner)
        self.status = label('', 'dim-label', xalign=0, wrap=True, visible=False)
        form.append(self.status)
        outer.append(Gtk.ScrolledWindow(child=form, propagate_natural_height=True,
                                        max_content_height=500, hscrollbar_policy=Gtk.PolicyType.NEVER))
        self.set_child(outer)
        board = next((board for board in window.snapshot['boards'] if board['id'] == self.board_id), {})
        allowed = window.demo or board.get('permissions', {}).get('PERMISSION_EDIT', True)
        self.action.set_sensitive(bool(self.cards) and allowed and not self.pending())
        if self.pending():
            self.set_status(_("Resol els canvis pendents d'aquestes targetes abans d'esborrar-les."))
        elif not allowed:
            self.set_status(_("No tens permís per esborrar targetes d'aquest tauler."))
        self.connect('close-attempt', lambda *_unused: self.stop())

    def pending(self):
        ids = {card['id'] for card in self.cards}
        return any(operation['payload'].get('card_id') in ids for operation in self.window.store.operations())

    def set_status(self, text):
        ui.text(self.status, 'text', text)
        self.status.set_visible(bool(text))

    def start(self):
        if self.started or self.pending() or not self.cards:
            return
        self.started = True
        self.set_can_close(False)
        self.action.remove_css_class('destructive-action')
        ui.text(self.action, 'label', _("Atura"))
        self.spinner.set_visible(True)
        self.spinner.set_spinning(True)
        self.progress(0)
        def remove(api):
            for _card_id in delete_archived_batch(api, self.window.store, self.board_id, self.stack['id'], self.cards, self.stopped):
                self.deleted += 1
                self.window.engine.dispatch(self.progress, self.deleted)
        self.window.engine.run(remove, self.finished)

    def progress(self, count):
        self.set_status(_("Targetes esborrades: {count} / {total}").format(count=count, total=len(self.cards)))

    def stop(self):
        self.stopped.set()
        self.action.set_sensitive(False)
        self.set_status(_("S'està aturant…"))

    def finished(self, _result, error):
        self.force_close()
        self.window.render()
        if error:
            message(self.window, _("No s'han pogut esborrar totes les targetes"),
                    _("Targetes esborrades: {count} / {total}").format(count=self.deleted, total=len(self.cards))+'\n'+error)
        elif self.deleted == len(self.cards) and self.after:
            self.after()
