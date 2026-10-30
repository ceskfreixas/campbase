# SPDX-License-Identifier: GPL-3.0-or-later
"""Native file selection, explicit transfers and durable uncertain upload review."""
from gi.repository import Adw, Gio, GLib, Gtk
from . import localization as ui
from .i18n import _
from .widgets import label, icon_button, clear
from .talk_widgets import DialogWorker
from .deck import DeckError
from .deck_resources import MAX_ATTACHMENT, attachment_name


class AttachmentsPanel(Gtk.Box):
    def __init__(self, window, dialog, board_id, stack_id, card, editable):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.window, self.dialog = window, dialog
        self.board_id, self.stack_id, self.card = board_id, stack_id, card
        self.worker = DialogWorker(dialog, window, name='campbase-attachments') if not window.demo else None
        self.key = 'attachment_pending:' + (window.account.server if window.account else 'demo') + ':' + str(card['id'])
        header = Gtk.Box(spacing=8)
        header.append(label(_("Adjunts"), 'heading', xalign=0, hexpand=True))
        self.add = icon_button('list-add-symbolic', _("Afegeix un fitxer"), self.choose)
        self.add.set_sensitive(editable and self.worker is not None)
        header.append(self.add)
        self.reload = icon_button('view-refresh-symbolic', _("Actualitza els adjunts"), self.load)
        self.reload.set_sensitive(self.worker is not None)
        header.append(self.reload)
        self.append(header)
        self.status = label('', 'dim-label', xalign=0, wrap=True, visible=False)
        self.append(self.status)
        self.review = ui.create(Gtk.Button, label=_("Revisa l'adjunt pendent"), halign=Gtk.Align.START)
        self.review.connect('clicked', self.review_pending)
        self.review.set_visible(bool(window.store.get(self.key)))
        self.append(self.review)
        self.rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.append(self.rows)
        if self.worker:
            self.load()

    def set_status(self, value):
        ui.text(self.status, 'text', value)
        self.status.set_visible(bool(value))

    def run(self, action, done, *, transfer=False):
        if not self.worker or self.worker.busy or not self.worker.active():
            return
        self.add.set_sensitive(False)
        self.reload.set_sensitive(False)
        if transfer:
            self.dialog.set_can_close(False)
        def finished(result, error):
            self.dialog.set_can_close(True)
            self.add.set_sensitive(self.editable())
            self.reload.set_sensitive(True)
            self.set_status(error or '')
            self.review.set_visible(bool(self.window.store.get(self.key)))
            if not error:
                done(result)
        self.worker.run(action, finished)

    def editable(self):
        board = next((b for b in self.window.snapshot['boards'] if b['id'] == self.board_id), {})
        return board.get('permissions', {}).get('PERMISSION_EDIT', False)

    def load(self, *_unused):
        self.set_status(_("S'estan carregant els adjunts…"))
        self.run(lambda: self.worker.api.attachments(self.board_id, self.stack_id, self.card['id']), self.display)

    def display(self, items):
        clear(self.rows)
        if not items:
            self.rows.append(label(_("Encara no hi ha adjunts."), 'dim-label', xalign=0))
        for item in items:
            row = Adw.ActionRow(title=attachment_name(item), use_markup=False)
            row.add_css_class('card')
            extended = item.get('extendedData')
            size = extended.get('filesize') if isinstance(extended, dict) else None
            if type(size) is int and size >= 0:
                row.set_subtitle(GLib.format_size(size))
            save = icon_button('document-save-symbolic', _("Desa l'adjunt"),
                               lambda *_, item=item: self.download(item))
            save.set_valign(Gtk.Align.CENTER)
            save.set_margin_top(8)
            save.set_margin_bottom(8)
            row.add_suffix(save)
            self.rows.append(row)

    def choose(self, *_unused):
        if not self.worker or self.worker.busy:
            return
        if self.window.store.get(self.key):
            self.review_pending()
            return
        chooser = ui.create(Gtk.FileDialog, title=_("Afegeix un fitxer"))
        def selected(chooser, result):
            try:
                file = chooser.open_finish(result)
            except GLib.Error:
                return
            self.upload(file)
        chooser.open(self.window, None, selected)

    def upload(self, file):
        if self.window.store.get(self.key):
            self.review_pending()
            return
        self.set_status(_("S'està enviant l'adjunt…"))
        def send():
            stream = file.read(None)
            data = bytearray()
            try:
                while len(data) <= MAX_ATTACHMENT:
                    chunk = stream.read_bytes(min(1024*1024, MAX_ATTACHMENT+1-len(data)), None).get_data()
                    if not chunk:
                        break
                    data.extend(chunk)
            finally:
                stream.close(None)
            if len(data) > MAX_ATTACHMENT:
                raise DeckError(_("El fitxer supera el límit de 64 MiB."))
            name = file.get_basename() or 'attachment'
            result = self.worker.api.upload_attachment(self.board_id, self.stack_id, self.card['id'], name, bytes(data),
                before_send=lambda: self.window.store.put(self.key, {'name': name}))
            self.window.store.put(self.key, None)
            return result
        self.run(send, lambda _: self.load(), transfer=True)

    def review_pending(self, *_unused):
        prompt = ui.create(Adw.AlertDialog, heading=_("Revisa l'adjunt pendent"),
            body=_("Comprova els adjunts abans de repetir l'enviament per evitar duplicats."))
        ui.response(prompt, 'cancel', _("Cancel·la"))
        ui.response(prompt, 'reset', _("Ja ho he comprovat"))
        prompt.set_default_response('cancel')
        prompt.set_close_response('cancel')
        def response(_prompt, choice):
            if choice == 'reset' and self.worker.active():
                self.window.store.put(self.key, None)
                self.review.set_visible(False)
                self.load()
        prompt.connect('response', response)
        prompt.present(self.dialog)

    def download(self, item):
        if self.worker.busy:
            return
        chooser = ui.create(Gtk.FileDialog, title=_("Desa l'adjunt"), initial_name=attachment_name(item))
        def selected(chooser, result):
            try:
                target = chooser.save_finish(result)
            except GLib.Error:
                return
            self.set_status(_("S'està descarregant l'adjunt…"))
            def save():
                data = self.worker.api.download_attachment(self.card['id'], item['id'], item.get('type') or 'deck_file')
                target.replace_contents(data, None, False, Gio.FileCreateFlags.PRIVATE, None)
            self.run(save, lambda _: None, transfer=True)
        chooser.save(self.window, None, selected)
