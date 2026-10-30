# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Text chat with incremental reads, explicit sends and recoverable drafts."""
from datetime import datetime
import secrets
from gi.repository import Adw, GLib, Gtk, Pango
from . import localization as ui
from .i18n import _
from .widgets import label, icon_button
from .people import avatar
from .talk import Talk, token, message_text
from .talk_widgets import DialogWorker
from .scroll_position import ScrollPosition


class MessageScroll(ScrollPosition):
    def anchors(self, widget=None):
        child = self.content.get_first_child()
        while child:
            if hasattr(child, 'message_id'):
                yield ('message', child.message_id), child
            child = child.get_next_sibling()


class ChatDialog(Adw.Dialog):
    def __init__(self, window, room):
        title = room.get('displayName') or room.get('name') or _("Conversa")
        super().__init__(title=ui.render(title), content_width=640, content_height=640)
        ui.widget(self, title=title)
        self.window, self.room = window, room
        self.room_token = token(room['token'])
        self.worker = DialogWorker(self, window, name='campbase-talk-read')
        self.writer = DialogWorker(self, window, name='campbase-talk-write')
        self.talk = Talk(self.worker.api)
        self.features = set()
        self.uid = ''
        self.messages = {}
        self.message_rows = {}
        self.after = 0
        self.read_marker = 0
        self.draft_key = 'talk_draft:' + self.worker.api.server + ':' + self.room_token
        self.pending_key = self.draft_key + ':pending'
        self.pending = window.store.get(self.pending_key)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        header.pack_end(icon_button('adw-external-link-symbolic', _("Obre a Talk"), self.open_talk))
        header.pack_start(icon_button('view-refresh-symbolic', _("Missatges recents"), self.load_recent))
        self.review_button = icon_button('dialog-question-symbolic', _("Revisa l'enviament"), self.review_send)
        self.review_button.set_visible(bool(self.pending))
        header.pack_end(self.review_button)
        box.append(header)
        self.participant_label = label('', 'caption', xalign=0, wrap=True, lines=2,
                                       ellipsize=Pango.EllipsizeMode.END,
                                       margin_start=24, margin_end=24, margin_top=12)
        box.append(self.participant_label)
        self.status = label('', 'dim-label', xalign=0, wrap=True, visible=False,
                            margin_start=24, margin_end=24, margin_top=12)
        box.append(self.status)
        self.rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18,
                            margin_top=18, margin_bottom=18, margin_start=24, margin_end=24)
        self.older = ui.create(Gtk.Button, label=_("Missatges anteriors"), halign=Gtk.Align.CENTER)
        self.older.connect('clicked', self.load_older)
        self.rows.append(self.older)
        self.scroller = Gtk.ScrolledWindow(child=self.rows, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        box.append(self.scroller)
        self.scroller.get_vadjustment().connect('changed', self.adjusted)
        self.scroll_position = MessageScroll(self.scroller, self.rows)
        self.scroll_position.context = self.room_token
        self.follow_bottom = True
        editor = Gtk.Box(spacing=8, margin_start=18, margin_end=18, margin_top=12, margin_bottom=18)
        self.entry = ui.create(Gtk.Entry, placeholder_text=_("Escriu un missatge…"), hexpand=True, max_length=32000)
        self.entry.set_text(window.store.get(self.draft_key, ''))
        self.entry.connect('activate', self.send)
        self.entry.connect('changed', self.draft_changed)
        self.entry.set_sensitive(not bool(self.pending))
        editor.append(self.entry)
        self.send_button = icon_button('mail-send-symbolic', _("Envia el missatge"), self.send)
        self.send_button.set_sensitive(not bool(self.pending))
        editor.append(self.send_button)
        box.append(editor)
        self.set_child(box)
        self.connect('closed', self.closed)
        self.timer = GLib.timeout_add_seconds(5, self.refresh)
        def loaded(result, error):
            if error:
                self.set_status(error)
                return
            caps, profile, participants = result
            self.features = set(caps.get('features', []))
            self.uid = profile['uid']
            names = ', '.join(p.get('displayName') or p.get('actorId') or '' for p in participants)
            ui.text(self.participant_label, 'text', _("Participants: {names}").format(names=names))
            ui.text(self.participant_label, 'tooltip_text', _("Participants: {names}").format(names=names))
            if self.pending:
                self.set_status(_("No s'ha pogut confirmar l'enviament. Comprova la conversa a Talk abans de tornar-lo a enviar."))
            self.refresh()
        def initial():
            caps = self.talk.capabilities()
            profile = self.window.store.get('profile', {})
            if not profile.get('uid') or profile.get('account') != getattr(self.worker.api, 'goa_id', ''):
                profile = self.worker.api.profile()
                if self.worker.active():
                    import time
                    self.window.store.put('profile', profile | {'account': getattr(self.worker.api, 'goa_id', ''), 'checked': time.time()})
            return caps, profile, self.talk.participants(self.room_token)
        self.worker.run(initial, loaded)

    def set_status(self, text):
        ui.text(self.status, 'text', text)
        self.status.set_visible(bool(text))

    def draft_changed(self, *_unused):
        if self.worker.active():
            self.window.store.put(self.draft_key, self.entry.get_text())

    def open_talk(self, *_unused):
        Gtk.UriLauncher.new(self.worker.api.server + '/index.php/call/' + self.room_token).launch(self.window, None, None)

    def review_send(self, *_unused):
        prompt = ui.create(Adw.AlertDialog, heading=_("El missatge és a Talk?"),
            body=_("Comprova-ho abans de tornar-lo a enviar per evitar duplicats."))
        ui.response(prompt, 'cancel', _("Cancel·la"))
        ui.response(prompt, 'sent', _("Ja s'ha enviat"))
        ui.response(prompt, 'unsent', _("No s'ha enviat"))
        prompt.set_default_response('cancel')
        prompt.set_close_response('cancel')
        def response(_prompt, choice):
            if choice not in {'sent', 'unsent'} or not self.worker.active():
                return
            self.pending = None
            self.window.store.put(self.pending_key, None)
            if choice == 'sent':
                self.entry.set_text('')
            self.entry.set_sensitive(True)
            self.send_button.set_sensitive(True)
            self.review_button.set_visible(False)
            self.set_status('')
        prompt.connect('response', response)
        prompt.present(self)

    def adjusted(self, adjustment):
        if self.follow_bottom:
            adjustment.set_value(max(0, adjustment.get_upper() - adjustment.get_page_size()))

    def message_row(self, item):
        row = Gtk.Box(spacing=10, valign=Gtk.Align.START)
        row.message_id = int(item['id'])
        if item.get('actorType') == 'users':
            row.append(avatar(self.window, {'uid': item.get('actorId'), 'displayname': item.get('actorDisplayName')}, 28))
        contents = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5, hexpand=True)
        name = item.get('actorDisplayName') or item.get('actorId') or ''
        when = datetime.fromtimestamp(item.get('timestamp', 0)).astimezone().strftime('%x · %H:%M')
        contents.append(label(name + ' · ' + when, 'caption', xalign=0, wrap=True))
        contents.append(label(message_text(item), xalign=0, wrap=True, selectable=True))
        row.append(contents)
        from .chat_actions import message_actions
        actions = message_actions(self, item)
        if actions:
            row.append(actions)
        return row

    def add_messages(self, messages, older=False):
        if not messages:
            return
        adjustment = self.scroller.get_vadjustment()
        self.follow_bottom = adjustment.get_value() + adjustment.get_page_size() >= adjustment.get_upper() - 32
        if older or not self.follow_bottom:
            self.follow_bottom = False
            self.scroll_position.prepare(self.room_token)
        for item in sorted(messages, key=lambda m: int(m.get('id') or (m.get('parent') or {}).get('id', 0))):
            # Talk sends edits/deletions as system events carrying the updated
            # original in parent. Do not retain deleted private message text.
            if item.get('systemMessage') in {'message_deleted', 'message_edited'} and isinstance(item.get('parent'), dict):
                item = item['parent']
            key = int(item['id'])
            if item.get('deleted') or item.get('messageType') == 'comment_deleted':
                self.messages.pop(key, None)
                row = self.message_rows.pop(key, None)
                if row is not None:
                    self.rows.remove(row)
                continue
            if self.messages.get(key) == item:
                continue
            self.messages[key] = item
            if key in self.message_rows:
                self.rows.remove(self.message_rows.pop(key))
            before = max((k for k in self.message_rows if k < key), default=None)
            row = self.message_row(item)
            self.rows.insert_child_after(row, self.message_rows.get(before, self.older))
            self.message_rows[key] = row
        # History pages stay bounded; the header returns to recent messages.
        while len(self.messages) > 500:
            key = max(self.messages) if older else min(self.messages)
            self.messages.pop(key)
            self.rows.remove(self.message_rows.pop(key))
        if not self.follow_bottom:
            self.scroll_position.restore()
        if self.pending and any(m.get('referenceId') == self.pending for m in messages):
            self.pending = None
            self.window.store.put(self.pending_key, None)
            self.entry.set_text('')
            self.entry.set_sensitive(True)
            self.send_button.set_sensitive(True)
            self.review_button.set_visible(False)
            self.set_status('')

    def refresh(self):
        if not self.worker.active():
            self.force_close()
            return GLib.SOURCE_REMOVE
        if not self.get_mapped() and self.after:
            return GLib.SOURCE_CONTINUE
        def done(messages, error):
            if error:
                self.set_status(error)
                return
            self.add_messages(messages)
            self.after = max([self.after, *(int(m['id']) for m in messages)])
            if self.after > self.read_marker and self.get_mapped():
                marker = self.after
                def marked(_result, error):
                    if not error:
                        self.read_marker = max(self.read_marker, marker)
                # Read acknowledgements and sends stay ordered; long-polling
                # uses a separate worker and can never delay a deliberate send.
                self.writer.run(lambda: self.talk.mark_read(self.room_token, marker), marked)
        self.worker.run(lambda: self.talk.messages(self.room_token, after=self.after), done)
        return GLib.SOURCE_CONTINUE

    def load_older(self, *_unused):
        if not self.messages:
            return
        self.worker.run(lambda: self.talk.messages(self.room_token, before=min(self.messages)),
                        lambda messages, error: self.set_status(error) if error else self.add_messages(messages, older=True))

    def load_recent(self, *_unused):
        if self.worker.busy:
            return
        self.scroll_position.cancel()
        for row in self.message_rows.values():
            self.rows.remove(row)
        self.messages.clear()
        self.message_rows.clear()
        self.after = 0
        self.follow_bottom = True
        self.refresh()

    def send(self, *_unused):
        text = self.entry.get_text().strip()
        if not text or self.pending or not self.worker.active():
            return
        reference = secrets.token_hex(32)
        self.pending = reference
        self.window.store.put(self.pending_key, reference)
        self.entry.set_sensitive(False)
        self.send_button.set_sensitive(False)
        self.set_can_close(False)
        def done(result, error):
            self.set_can_close(True)
            if error:
                self.set_status(_("No s'ha pogut confirmar l'enviament. Comprova la conversa a Talk abans de tornar-lo a enviar."))
                self.review_button.set_visible(True)
                # Keep the draft and wait for a read to confirm this reference.
                self.refresh()
                return
            self.add_messages([result])
            self.pending = None
            self.window.store.put(self.pending_key, None)
            self.entry.set_text('')
            self.entry.set_sensitive(True)
            self.send_button.set_sensitive(True)
            self.set_status('')
            self.refresh()
        self.writer.run(lambda: self.talk.send(self.room_token, text, reference), done, queue=True)

    def closed(self, *_unused):
        self.scroll_position.cancel()
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0
