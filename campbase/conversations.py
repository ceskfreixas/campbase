# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Talk inbox and explicit direct/group conversation entry points."""
from gi.repository import Adw, Gtk
from . import localization as ui
from .i18n import _
from .widgets import label, icon_button
from .dialog_widgets import dialog_form, fit_dialog_contents
from .collaboration import person
from .people import avatar
from .talk import Talk, local_members
from .talk_widgets import DialogWorker
from .chat import ChatDialog


class ConversationsDialog(Adw.Dialog):
    def __init__(self, window, board):
        super().__init__(content_width=520, follows_content_size=True)
        ui.widget(self, title=_("Converses"))
        self.window, self.board = window, board
        self.worker = DialogWorker(self, window)
        self.talk = Talk(self.worker.api)
        self.setup_key = 'talk_setup:' + self.worker.api.server + ':' + str(board['id'])
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, width_request=520)
        self.content_box = outer
        header = Adw.HeaderBar()
        header.pack_start(icon_button('adw-external-link-symbolic', _("Obre a Talk"), self.open_talk))
        header.pack_end(icon_button('view-refresh-symbolic', _("Actualitza"), self.load))
        outer.append(header)
        self.form = dialog_form()
        self.form.append(label(_("Missatgeria amb Nextcloud Talk"), 'heading', xalign=0, wrap=True))
        self.status = label('', 'dim-label', xalign=0, wrap=True, visible=False)
        self.form.append(self.status)
        self.groups = ui.create(Adw.PreferencesGroup, title=_("Xat del tauler"))
        self.form.append(self.groups)
        self.people = ui.create(Adw.PreferencesGroup, title=_("Missatges directes"))
        self.form.append(self.people)
        self.inbox = ui.create(Adw.PreferencesGroup, title=_("Converses de Talk"))
        self.form.append(self.inbox)
        self.rows = []
        self.scroller = Gtk.ScrolledWindow(child=self.form, vexpand=True,
            propagate_natural_height=True, max_content_height=620, hscrollbar_policy=Gtk.PolicyType.NEVER)
        outer.append(self.scroller)
        self.set_child(outer)
        ui.on_change(self.fit_contents)
        self.load()

    def fit_contents(self):
        fit_dialog_contents(self)

    def set_status(self, text):
        ui.text(self.status, 'text', text)
        self.status.set_visible(bool(text))
        fit_dialog_contents(self)

    def load(self, *_unused, after_error=None):
        def read():
            self.talk.capabilities()
            return self.worker.api.check_board(self.board['id']), self.worker.api.profile(), self.talk.conversations()
        self.worker.run(read, lambda result, error: self.loaded(result, error, after_error))

    def loaded(self, result, error, after_error=None):
        if error:
            self.set_status(error)
            return
        self.set_status(after_error or '')
        for group, row in self.rows:
            group.remove(row)
        self.rows = []
        board, profile, rooms = result
        self.board = board
        from .links import board_url
        board_rooms = [r for r in rooms if r.get('type') == 2 and r.get('description', '').strip() == board_url(self.worker.api.server, board['id'])]
        setup = self.window.store.get(self.setup_key)
        if setup and setup != 'pending':
            known = next((r for r in rooms if r.get('token') == setup), None)
            if known and known not in board_rooms:
                board_rooms.append(known)
        for room in board_rooms:
            self.room_row(self.groups, room)
        if not board_rooms and setup == 'pending':
            row = ui.create(Adw.ActionRow,
                title=_("Comprova la creació del xat a Talk abans de tornar-ho a provar."), activatable=True)
            row.connect('activated', self.review_setup)
            self.add_row(self.groups, row)
        elif not board_rooms and person(board.get('owner'))['uid'] == profile['uid']:
            row = ui.create(Adw.ActionRow, title=_("Crea el xat del tauler"), activatable=True)
            row.add_suffix(Gtk.Image(icon_name='list-add-symbolic'))
            row.connect('activated', self.confirm_group)
            self.add_row(self.groups, row)
        for user in local_members(board):
            if user['uid'] == profile['uid']:
                continue
            row = Adw.ActionRow(title=user['displayname'], subtitle=user['uid'], activatable=True)
            row.add_prefix(avatar(self.window, user, 28))
            row.add_suffix(Gtk.Image(icon_name='mail-message-new-symbolic'))
            row.connect('activated', lambda *_, uid=user['uid']: self.open_direct(uid))
            self.add_row(self.people, row)
        inbox = [room for room in rooms if room not in board_rooms]
        for room in inbox:
            self.room_row(self.inbox, room)
        self.inbox.set_visible(bool(inbox))
        self.groups.set_visible(bool(board_rooms) or person(board.get('owner'))['uid'] == profile['uid'])
        self.people.set_visible(any(u['uid'] != profile['uid'] for u in local_members(board)))

    def add_row(self, group, row):
        group.add(row)
        self.rows.append((group, row))

    def open_talk(self, *_unused):
        Gtk.UriLauncher.new(self.worker.api.server + '/index.php/apps/spreed').launch(self.window, None, None)

    def review_setup(self, *_unused):
        prompt = ui.create(Adw.AlertDialog, heading=_("Has comprovat si el xat existeix?"),
            body=_("Revisa les converses a Talk. Reinicia l'intent només si el xat no s'ha creat."))
        ui.response(prompt, 'cancel', _("Cancel·la"))
        ui.response(prompt, 'reset', _("No s'ha creat"))
        prompt.set_default_response('cancel')
        prompt.set_close_response('cancel')
        def response(_prompt, choice):
            if choice == 'reset' and self.worker.active():
                self.window.store.put(self.setup_key, None)
                self.load()
        prompt.connect('response', response)
        prompt.present(self)

    def room_row(self, group, room):
        row = Adw.ActionRow(title=room.get('displayName') or room.get('name') or '', activatable=True)
        unread = room.get('unreadMessages', 0)
        if unread:
            row.add_suffix(label(str(unread), 'dim-label', valign=Gtk.Align.CENTER))
        row.add_suffix(Gtk.Image(icon_name='go-next-symbolic'))
        row.connect('activated', lambda *_: ChatDialog(self.window, room).present(self))
        self.add_row(group, row)

    def open_direct(self, uid):
        def done(room, error):
            self.set_status(error or '')
            if room:
                ChatDialog(self.window, room).present(self)
        self.worker.run(lambda: self.talk.direct(uid), done)

    def confirm_group(self, *_unused):
        expected_users = {user['uid'] for user in local_members(self.board)}
        names = ', '.join(user['displayname'] for user in local_members(self.board))
        prompt = ui.create(Adw.AlertDialog, heading=_("Vols crear el xat del tauler?"),
            body=_("Es convidaran aquests membres del servidor: {names}. Els participants del xat es gestionen a Talk; els canvis al tauler no els modifiquen automàticament.").format(names=names))
        ui.response(prompt, 'cancel', _("Cancel·la"))
        ui.response(prompt, 'create', _("Crea el xat"))
        prompt.set_default_response('cancel')
        prompt.set_close_response('cancel')
        prompt.connect('response', lambda _, response: self.create_group(expected_users) if response == 'create' else None)
        prompt.present(self)

    def create_group(self, expected_users):
        if self.worker.busy:
            return
        self.set_can_close(False)
        def created(room_token):
            if self.worker.active():
                self.window.store.put(self.setup_key, room_token)
        def done(room, error):
            self.set_can_close(True)
            self.set_status(error or '')
            if room:
                ChatDialog(self.window, room).present(self)
            self.load(after_error=error)
        self.worker.run(lambda: self.talk.create_board_conversation(self.board['id'], created,
            expected_users=expected_users, creating=lambda: self.window.store.put(self.setup_key, 'pending')), done)
