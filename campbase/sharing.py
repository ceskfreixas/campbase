# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Explicit same-server board sharing with per-member permissions."""
from gi.repository import Adw, Gtk
from . import localization as ui
from .i18n import _
from .collaboration import person
from .dialog_widgets import dialog_form, fit_dialog_contents, scroll_to_widget
from .widgets import label, clear, icon_button
from .people import identity, avatar
from .alerts import message
from .links import board_url

PERMISSIONS = ('permissionEdit', 'permissionShare', 'permissionManage')


class SharingDialog(Adw.Dialog):
    def __init__(self, window, board, focus_members=False):
        super().__init__(content_width=520, follows_content_size=True)
        ui.widget(self, title=_("Comparteix el tauler"))
        self.window, self.board = window, board
        self.focus_members = focus_members
        self.busy = False
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, width_request=520)
        self.content_box = outer
        outer.append(Adw.HeaderBar())
        self.form = dialog_form()
        intro = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        intro.append(label(board['title'], 'title-3', xalign=0, wrap=True))
        intro.append(label(_("Convida usuaris del mateix servidor de Nextcloud."), 'dim-label', xalign=0, wrap=True))
        self.form.append(intro)
        self.link_row = ui.create(Adw.ActionRow, title=_("Enllaç del tauler"),
            subtitle=_("Només hi poden accedir els membres amb permís. L'enllaç no convida usuaris ni fa públic el tauler."),
            subtitle_lines=0)
        self.copy_button = icon_button('edit-copy-symbolic', _("Copia l'enllaç"), self.copy_link)
        self.copy_button.set_valign(Gtk.Align.CENTER)
        self.copy_button.set_margin_top(8)
        self.copy_button.set_margin_bottom(8)
        self.copy_button.set_sensitive(bool(window.account) and board['id'] > 0 and not window.demo)
        self.link_row.add_suffix(self.copy_button)
        link_group = Adw.PreferencesGroup()
        link_group.add(self.link_row)
        self.form.append(link_group)
        self.search = ui.create(Gtk.SearchEntry, placeholder_text=_("Cerca un usuari pel nom o identificador…"))
        self.search.connect('activate', self.search_users)
        search_line = Gtk.Box(spacing=8)
        self.search.set_hexpand(True)
        search_line.append(self.search)
        search_line.append(icon_button('system-search-symbolic', _("Cerca usuaris"), self.search_users))
        search_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        search_section.append(search_line)
        search_section.append(label(_("Cerca pel nom o identificador. També pots provar el correu complet si el servidor ho permet."),
                                    'caption', xalign=0, wrap=True))
        self.form.append(search_section)
        self.initial_permission = ui.create(Adw.ComboRow, title=_("Permís inicial"),
                                            model=ui.strings([_("Només lectura"), _("Pot editar targetes")]))
        self.initial_permission.set_selected(1)
        permissions_group = Adw.PreferencesGroup()
        permissions_group.add(self.initial_permission)
        self.form.append(permissions_group)
        self.results = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, visible=False)
        self.form.append(self.results)
        self.status = label('', 'dim-label', xalign=0, wrap=True, visible=False)
        self.form.append(self.status)
        self.member_group = ui.create(Adw.PreferencesGroup, title=_("Membres del tauler"))
        self.form.append(self.member_group)
        self.rows = []
        self.scroller = Gtk.ScrolledWindow(child=self.form, vexpand=True, propagate_natural_height=True,
                                          max_content_height=620, hscrollbar_policy=Gtk.PolicyType.NEVER)
        outer.append(self.scroller)
        self.set_child(outer)
        ui.on_change(self.fit_contents)
        self.display(board)
        self.connect('map', lambda *_unused: self.focus_member_list())
        if not window.demo:
            self.perform(lambda api: api.check_board(board['id']))

    def display(self, board):
        self.board = board
        for row in self.rows:
            self.member_group.remove(row)
        self.rows = []
        owner = person(board.get('owner'))
        row = ui.create(Adw.ActionRow, title=owner['displayname'], subtitle=_("Responsable · {username}").format(username=owner['uid']))
        row.add_prefix(avatar(self.window, owner, 32))
        self.member_group.add(row)
        self.rows.append(row)
        allowed = board.get('permissions', {}).get('PERMISSION_SHARE', False)
        self.search.set_sensitive(allowed)
        self.initial_permission.set_sensitive(allowed)
        for acl in board.get('acl') or []:
            user = person(acl.get('participant'))
            row = ui.create(Adw.ExpanderRow, title=user['displayname'], subtitle='@'+user['uid'])
            row.add_prefix(avatar(self.window, user, 32))
            row.connect('notify::expanded', lambda *_unused: self.fit_contents())
            remove = icon_button('user-trash-symbolic', _("Retira l'accés"), lambda *_, acl=acl: self.confirm_remove(acl))
            remove.add_css_class('flat')
            remove.set_sensitive(allowed)
            row.add_suffix(remove)
            switches = {}
            for key, title in zip(PERMISSIONS, [_("Pot editar targetes"), _("Pot compartir el tauler"), _("Pot gestionar el tauler")]):
                control = ui.create(Adw.SwitchRow, title=title, active=bool(acl.get(key)), sensitive=allowed)
                row.add_row(control)
                switches[key] = control
            save = ui.create(Gtk.Button, label=_("Desa els permisos"), halign=Gtk.Align.END, sensitive=allowed,
                             margin_top=8, margin_bottom=8, margin_end=12)
            save.connect('clicked', lambda *_, acl=acl, controls=switches: self.perform(
                lambda api: api.change_access(board['id'], acl['id'], {k: c.get_active() for k, c in controls.items()})))
            row.add_row(save)
            self.member_group.add(row)
            self.rows.append(row)
        if not allowed:
            self.set_status(_("No tens permís per compartir aquest tauler."))
        self.focus_member_list()

    def focus_member_list(self):
        if self.focus_members:
            self.member_group.add_css_class('notification-target')
            scroll_to_widget(self.scroller, self.form, self.member_group)

    def set_status(self, value):
        ui.text(self.status, 'text', value)
        self.status.set_visible(bool(value))
        self.fit_contents()

    def copy_link(self, *_unused):
        if self.window.account and self.board['id'] > 0 and not self.window.demo:
            self.copy_button.get_clipboard().set(board_url(self.window.account.server, self.board['id']))
            self.set_status(_("Enllaç copiat."))

    def fit_contents(self):
        fit_dialog_contents(self)

    def perform(self, action):
        if self.busy:
            return
        self.busy = True
        self.form.set_sensitive(False)
        self.set_can_close(False)
        self.set_status(_("S'estan actualitzant els membres…"))
        def done(board, error):
            self.busy = False
            self.form.set_sensitive(True)
            self.set_can_close(True)
            self.set_status(error or '')
            if not error:
                self.display(board)
                self.window.store.cache_board(board)
                self.window.render()
                clear(self.results)
                self.results.set_visible(False)
            self.fit_contents()
        self.window.engine.run(action, done)

    def search_users(self, *_unused):
        query = self.search.get_text().strip()
        if self.busy or len(query) < 2:
            self.set_status(_("Escriu almenys dos caràcters per cercar."))
            return
        self.busy = True
        self.search.set_sensitive(False)
        self.set_status(_("S'estan cercant usuaris…"))
        def done(users, error):
            self.busy = False
            self.search.set_sensitive(True)
            clear(self.results)
            self.results.set_visible(bool(users))
            self.set_status(error or (_("No s'ha trobat cap usuari.") if not users else ''))
            existing = {person(a.get('participant'))['uid'] for a in self.board.get('acl') or [] if a.get('type') == 0}
            existing.add(person(self.board.get('owner'))['uid'])
            for user in users or []:
                line = identity(user, window=self.window)
                add = ui.create(Gtk.Button, label=_("Comparteix"), sensitive=user['uid'] not in existing)
                add.connect('clicked', lambda *_, uid=user['uid']: self.perform(lambda api: api.share_board(
                    self.board['id'], uid, dict(zip(PERMISSIONS, [self.initial_permission.get_selected() == 1, False, False])))))
                line.append(add)
                self.results.append(line)
            self.fit_contents()
        self.window.engine.run(lambda api: api.search_users(query), done)

    def confirm_remove(self, acl):
        prompt = ui.create(Adw.AlertDialog, heading=_("Vols retirar l'accés?"),
                           body=_("Aquest membre deixarà de tenir accés a través d'aquesta compartició."))
        ui.response(prompt, 'cancel', _("Cancel·la"))
        ui.response(prompt, 'remove', _("Retira l'accés"))
        prompt.set_response_appearance('remove', Adw.ResponseAppearance.DESTRUCTIVE)
        prompt.set_default_response('cancel')
        prompt.connect('response', lambda _, response: self.perform(lambda api: api.change_access(
            self.board['id'], acl['id'])) if response == 'remove' else None)
        prompt.present(self)
