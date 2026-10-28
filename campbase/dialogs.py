# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Catalan native editors, account settings and pending-change review."""
from . import localization as ui
from .i18n import _, ngettext
import gi
gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk

from .account import Account, available_accounts, open_accounts_settings
from .deck import Deck
from .card_dialog import CardDialog
from .alerts import message
from .choosers import ColorChooser
from . import i18n
from .preferences import Preferences
from .widgets import icon_button, label, text_icon_button
from .dialog_widgets import dialog_form


class TextDialog(Adw.Dialog):
    def __init__(self, window, title, initial, callback):
        super().__init__(title=title, content_width=420)
        ui.widget(self, title=title)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_child(box)
        header = Adw.HeaderBar()
        button = ui.create(Gtk.Button, label=_("Desa"))
        button.add_css_class("suggested-action")
        header.pack_end(button)
        box.append(header)
        form = dialog_form()
        box.append(form)
        entry = ui.create(Gtk.Entry, text=initial, placeholder_text=_("Nom"), activates_default=True)
        entry.set_max_length(100)
        form.append(entry)
        self.entry = entry
        def save(*_unused):
            value = entry.get_text().strip()
            if value:
                callback(value, None)
                self.close()
        button.connect("clicked", save)
        entry.connect("activate", save)
        self.set_default_widget(button)


class ColumnColorDialog(Adw.Dialog):
    def __init__(self, window, stack, callback):
        super().__init__(content_width=420)
        ui.widget(self, title=_("Canvia el color"))
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        save = ui.create(Gtk.Button, label=_("Desa"))
        save.add_css_class('suggested-action')
        header.pack_end(save)
        outer.append(header)
        form = dialog_form()
        form.append(label(stack['title'], 'heading', xalign=0, wrap=True))
        form.append(label(_("Color de la columna en aquest ordinador"), 'dim-label', xalign=0, wrap=True))
        self.color = ColorChooser(window.column_color(stack))
        form.append(self.color)
        outer.append(form)
        self.set_child(outer)
        self.save_button = save
        save.connect('clicked', lambda *_unused: (callback(self.color.selected_color), self.close()))


class AccountDialog(Adw.Dialog):
    def __init__(self, window):
        super().__init__(title=_("Comptes en línia de GNOME"), content_width=520, follows_content_size=True)
        ui.widget(self, title=_("Comptes en línia de GNOME"))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.content_box = box
        self.set_child(Adw.Clamp(maximum_size=520, tightening_threshold=520, child=box))
        header = Adw.HeaderBar()
        box.append(header)
        form = dialog_form()
        group = ui.create(Adw.PreferencesGroup, title="Nextcloud Deck", description=_("El Campbase fa servir el compte de Nextcloud configurat a GNOME. No cal introduir cap contrasenya aquí."))
        try:
            accounts = available_accounts()
        except ValueError:
            accounts = []
        selection = ui.create(Adw.ComboRow, title=_("Compte de Nextcloud"), model=ui.strings([a["title"] for a in accounts]))
        if window.account:
            selection.set_selected(next((i for i, a in enumerate(accounts) if a["id"] == window.account.goa_id), 0))
        group.add(selection)
        form.append(group)
        actions = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        settings = text_icon_button("preferences-system-symbolic", _("Obre Comptes en línia"), halign=Gtk.Align.CENTER)
        settings.connect("clicked", lambda *_unused: open_accounts_settings())
        actions.append(settings)
        self.status = label("", "dim-label", wrap=True)
        self.status.set_visible(False)
        actions.append(self.status)
        form.append(actions)
        box.append(Gtk.ScrolledWindow(child=form, vexpand=True, propagate_natural_height=True,
                                      max_content_height=620, propagate_natural_width=True, max_content_width=520,
                                      hscrollbar_policy=Gtk.PolicyType.NEVER))
        save = ui.create(Gtk.Button, label=_("Utilitza aquest compte"), sensitive=bool(accounts))
        save.add_css_class("suggested-action")
        header.pack_end(save)
        if not accounts:
            self.set_status(_("Afegeix un compte de Nextcloud a Configuració → Comptes en línia i torna a obrir aquesta finestra."))
        def connect(*_unused):
            info = accounts[selection.get_selected()]
            previous_id = window.account.goa_id if window.account else Account.selected_id()
            same = info["id"] == previous_id
            if window.store.operations() and not same:
                self.set_status(_("Cal resoldre els canvis pendents abans de canviar de compte."))
                return
            save.set_sensitive(False)
            # Drain the separate inbox worker before replacing account-bound
            # cache. No late response from the old account may repopulate it.
            window.engine.account_changing = True
            self.set_status(_("S'està obrint el compte de GNOME…"))
            def done(result, error):
                save.set_sensitive(True)
                window.engine.account_changing = False
                if error:
                    self.set_status(error)
                    return
                candidate, snapshot = result
                candidate.save()
                window.account = candidate
                window.assets.account_key = candidate.goa_id
                window.store.put("asset_account", candidate.goa_id)
                window.engine.api = Deck(candidate)
                window.account_loading = False
                if not same:
                    for key, empty in [('creators', {}), ('updates', {}), ('updates_read', []), ('profile', {}), ('local_notices', []), ('updates_hidden', []), ('comment_counts', {})]:
                        window.store.put(key, empty)
                    window.store.put("board_metadata", {})
                    window.store.set_setting("colors", {})
                    window.store.set_setting('archived_columns', [])
                    window.store.set_setting('archived_overrides', {})
                    window.store.put('undo_action', None)
                    window.store.set_setting("startup_board_id", None)
                window.store.put("snapshot", snapshot)
                window.render()
                window.engine.sync(read_only=not window.store.settings().get("auto_sync", True))
                self.close()
            def probe():
                try:
                    candidate = Account.from_goa(info["id"])
                    result = (candidate, Deck(candidate).fetch())
                    window.engine.updates_executor.submit(lambda: None).result()
                    window.engine.dispatch(done, result, None)
                except Exception:
                    window.engine.dispatch(done, None, _("No s'ha pogut connectar. Revisa el compte de Nextcloud a Comptes en línia de GNOME."))
            window.engine.executor.submit(probe)
        save.connect("clicked", connect)


    def set_status(self, text):
        ui.text(self.status, 'text', text)
        self.status.set_visible(bool(text))


class PendingDialog(Adw.Dialog):
    def __init__(self, window):
        super().__init__(title=_("Canvis pendents"), content_width=560)
        ui.widget(self, title=_("Canvis pendents"))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(box)
        box.append(Adw.HeaderBar())
        operations = window.store.operations()
        if not operations:
            self.set_content_height(360)
            status = ui.create(Adw.StatusPage, title=_("Tot sincronitzat"), icon_name="object-select-symbolic",
                               description=_("No hi ha canvis pendents d'enviar a Deck."))
            box.append(Gtk.ScrolledWindow(child=status, vexpand=True,
                                          hscrollbar_policy=Gtk.PolicyType.NEVER))
            return
        content = dialog_form()
        box.append(Gtk.ScrolledWindow(child=content, vexpand=True, propagate_natural_height=True,
                                      hscrollbar_policy=Gtk.PolicyType.NEVER))
        names = {"create": _("Targeta nova"), "move": _("Moviment de targeta"), "update": _("Canvis a la targeta"), "archive": _("Arxivament"), "board_update": _("Nom del projecte")}
        for operation in operations:
            panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            panel.add_css_class("comment")
            panel.append(label(names.get(operation["kind"], _("Canvi")), "heading", xalign=0))
            card = window.find_card(operation["payload"].get("card_id", -operation["id"]))
            if card:
                panel.append(label(card["title"], xalign=0, wrap=True))
            panel.append(label(i18n.saved_error(operation["error"]) or _("S'enviarà quan hi hagi connexió."), "dim-label", wrap=True, xalign=0))
            actions = Gtk.Box(spacing=8)
            discard = ui.create(Gtk.Button, label=_("Descarta el canvi"))
            discard.connect("clicked", lambda _unused, op=operation: self.resolve(window, op, False))
            actions.append(discard)
            # A create may already have reached Deck; never offer an automatic resend.
            if operation["state"] == "blocked" and operation["kind"] != "create":
                retry = ui.create(Gtk.Button, label=_("Aplica el meu canvi"))
                retry.add_css_class("suggested-action")
                retry.connect("clicked", lambda _unused, op=operation: self.resolve(window, op, True))
                actions.append(retry)
            panel.append(actions)
            content.append(panel)

    def resolve(self, window, operation, retry):
        if retry:
            window.store.retry(operation["id"], force=True)
        else:
            window.store.discard(operation["id"])
        window.render()
        window.engine.sync()
        self.close()
