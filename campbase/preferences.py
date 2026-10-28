# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Native preferences grouped by language, appearance, startup and syncing."""
from . import localization as ui
from gi.repository import Adw, Gtk
from . import i18n
from .i18n import _
from .settings import SYNC_INTERVALS, sync_interval


class Preferences(Adw.PreferencesDialog):
    def __init__(self, window):
        super().__init__(title=_("Preferències"))
        ui.widget(self, title=_("Preferències"))
        self.window = window
        page = ui.create(Adw.PreferencesPage, title='Campbase', icon_name='preferences-system-symbolic')
        self.add(page)
        for build in (self.language_group, self.appearance_group, self.board_view_group,
                      self.startup_group, self.sync_group, self.account_group):
            page.add(build())

    def language_group(self):
        group = ui.create(Adw.PreferencesGroup, title=_("Idioma"))
        ids = ['auto', *i18n.LANGUAGES]
        row = ui.create(Adw.ComboRow, title=_("Idioma de l'aplicació"), model=ui.strings([_("Automàtic (sistema)"), *i18n.LANGUAGES.values()]))
        selected = self.window.store.settings().get('language', 'auto')
        row.set_selected(ids.index(selected) if selected in ids else 0)
        self.language = row
        ui.selection(row, lambda *_unused: self.language_changed(ids[row.get_selected()]))
        group.add(row)
        group.add(ui.create(Adw.ActionRow, title=_("L'idioma s'aplica immediatament."), subtitle=_("Si l'idioma del sistema no està disponible, es fa servir l'anglès.")))
        return group

    def appearance_group(self):
        group = ui.create(Adw.PreferencesGroup, title=_("Aparença"))
        theme = ui.create(Adw.ComboRow, title=_("Tema"), model=ui.strings([_("Automàtic (sistema)"), _("Clar"), _("Fosc")]))
        values = ['system', 'light', 'dark']
        selected = self.window.store.settings().get('theme', 'system')
        theme.set_selected(values.index(selected) if selected in values else 0)
        ui.selection(theme, lambda *_unused: self.window.set_theme(values[theme.get_selected()]))
        group.add(theme)
        return group

    def board_view_group(self):
        group = ui.create(Adw.PreferencesGroup, title=_("Vista del tauler"))
        triage = ui.create(Adw.SwitchRow, title=_("Primera columna en una fila superior"), subtitle=_("Les targetes de la primera columna s'adapten a l'amplada de la finestra."))
        triage.set_active(self.window.store.settings().get('triage', True))
        triage.connect('notify::active', lambda *_unused: (self.window.store.set_setting('triage', triage.get_active()), self.window.render()))
        group.add(triage)
        self.columns_per_row = ui.create(Adw.ComboRow, title=_("Màxim de columnes per fila"),
                                         subtitle=_("Les columnes es reparteixen l'amplada disponible."),
                                         model=ui.strings([_("Automàtic"), *[str(count) for count in range(1, 7)]]))
        selected = self.window.store.settings().get('columns_per_row', 0)
        self.columns_per_row.set_selected(selected if isinstance(selected, int) and 0 <= selected <= 6 else 0)
        ui.selection(self.columns_per_row, lambda *_unused: (self.window.store.set_setting(
            'columns_per_row', self.columns_per_row.get_selected()), self.window.render()))
        group.add(self.columns_per_row)
        self.archives_default = ui.create(Adw.SwitchRow, title=_("Mostra les targetes arxivades per defecte"),
            subtitle=_("S'aplica a totes les columnes i elimina les excepcions. Després pots mostrar-les o amagar-les a cada columna."))
        self.archives_default.set_active(self.window.store.settings().get('show_archived_default', False))
        self.archives_default.connect('notify::active', lambda *_unused:
            self.window.set_archived_default(self.archives_default.get_active()))
        group.add(self.archives_default)
        return group

    def startup_group(self):
        group = ui.create(Adw.PreferencesGroup, title=_("En iniciar l'aplicació"), description=_("Aquestes opcions s'apliquen quan tornes a obrir el Campbase."))
        boards = self.window.snapshot.get('boards', [])
        ids = [None, *[board['id'] for board in boards]]
        names = [_("Últim tauler utilitzat"), *[board['title'] for board in boards]]
        settings = self.window.store.settings()
        selected = settings.get('startup_board_id')
        if selected not in ids:
            ids.append(selected)
            names.append(_("Tauler no disponible"))
        self.startup_board = ui.create(Adw.ComboRow, title=_("Tauler d'inici"), model=ui.strings(names))
        self.startup_board.set_selected(ids.index(selected))
        ui.selection(self.startup_board, lambda *_unused: self.window.store.set_setting('startup_board_id', ids[self.startup_board.get_selected()]))
        group.add(self.startup_board)
        self.startup_sidebar = ui.create(Adw.SwitchRow, title=_("Mostra la barra lateral"))
        self.startup_sidebar.set_active(settings.get('startup_sidebar', settings.get('sidebar', False)))
        self.startup_sidebar.connect('notify::active', lambda *_unused: self.window.store.set_setting('startup_sidebar', self.startup_sidebar.get_active()))
        group.add(self.startup_sidebar)
        return group

    def sync_group(self):
        group = ui.create(Adw.PreferencesGroup, title=_("Sincronització"))
        self.auto_sync = ui.create(Adw.SwitchRow, title=_("Sincronització automàtica"), subtitle=_("Amb l'opció desactivada, sincronitza amb F5 o amb el botó de sincronització."))
        self.auto_sync.set_active(self.window.store.settings().get('auto_sync', True))
        group.add(self.auto_sync)
        names = [_("30 segons"), _("45 segons"), _("1 minut"), _("2 minuts"), _("5 minuts"), _("10 minuts")]
        self.interval = ui.create(Adw.ComboRow, title=_("Interval de sincronització"), model=ui.strings(names))
        self.interval.set_selected(SYNC_INTERVALS.index(sync_interval(self.window.store.settings())))
        self.interval.set_sensitive(self.auto_sync.get_active())
        ui.selection(self.interval, lambda *_unused: self.window.configure_sync(interval=SYNC_INTERVALS[self.interval.get_selected()]))
        self.auto_sync.connect('notify::active', self.automatic_changed)
        group.add(self.interval)
        return group

    def account_group(self):
        group = ui.create(Adw.PreferencesGroup, title=_("Compte connectat"))
        row = ui.create(Adw.ActionRow, title=_("Compte de Nextcloud"), subtitle=self.window.account.server if self.window.account else _("Cap compte connectat"), activatable=True)
        row.add_suffix(Gtk.Image(icon_name='go-next-symbolic'))
        def open_account(*_unused):
            from .dialogs import AccountDialog
            AccountDialog(self.window).present(self.window)
        row.connect('activated', open_account)
        group.add(row)
        if self.window.account:
            from .people import current_person, avatar
            user = current_person(self.window)
            identity = ui.create(Adw.ActionRow, title=user['displayname'],
                                 subtitle=_("Nom d'usuari: {username}").format(username=user['uid']))
            identity.add_prefix(avatar(self.window, user, 40))
            group.add(identity)
        group.add(ui.create(Adw.ActionRow, title=_("Comptes en línia de GNOME"), subtitle=_("GNOME gestiona les credencials. El Campbase només desa quin compte has seleccionat.")))
        return group

    def automatic_changed(self, *_unused):
        enabled = self.auto_sync.get_active()
        self.interval.set_sensitive(enabled)
        self.window.configure_sync(enabled=enabled)

    def language_changed(self, preference):
        if ui.updating():
            return
        self.window.store.set_setting('language', preference)
        i18n.change_language(preference)
