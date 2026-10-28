# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Deck notifications and board activity in an accessible native inbox."""
from gi.repository import Adw, Gtk
from . import localization as ui
from .i18n import _
from .dialog_widgets import dialog_form, fit_dialog_contents
from .widgets import label, clear, icon_button
from .people import timestamp
from .updates import entries, mark_read, erase_entries
from .mention_style import MentionStyle, board_tokens


class NotificationsDialog(Adw.Dialog):
    def __init__(self, window):
        super().__init__(content_width=560)
        ui.widget(self, title=_("Notificacions"))
        self.window = window
        self.busy = False
        self.outside_click = Gtk.GestureClick(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        self.outside_click.set_propagation_limit(Gtk.PropagationLimit.NONE)
        self.outside_click.set_button(1)
        self.outside_click.connect('pressed', self.claim_outside)
        self.outside_click.connect('released', self.dismiss_outside)
        self.connect('map', lambda *_unused: window.add_controller(self.outside_click)
                     if self.outside_click.get_widget() is None else None)
        self.connect('closed', lambda *_unused: window.remove_controller(self.outside_click)
                     if self.outside_click.get_widget() is window else None)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        self.refresh_button = icon_button('view-refresh-symbolic', _("Actualitza les notificacions"), self.refresh)
        header.pack_start(self.refresh_button)
        self.clear_button = icon_button('user-trash-symbolic', _("Esborra tots els avisos"), self.confirm_clear)
        header.pack_end(self.clear_button)
        outer.append(header)
        self.form = dialog_form()
        self.status = label('', 'dim-label', xalign=0, wrap=True, visible=False)
        self.form.append(self.status)
        self.list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.form.append(self.list)
        self.form.append(label(_("Els avisos depenen de les notificacions i de l'activitat habilitades a Nextcloud."),
                               'dim-label', xalign=0, wrap=True))
        outer.append(Gtk.ScrolledWindow(child=self.form, vexpand=True, propagate_natural_height=True,
                                        max_content_height=600, hscrollbar_policy=Gtk.PolicyType.NEVER))
        self.set_child(outer)
        ui.on_change(self.fit_contents)
        self.display()
        if not window.demo:
            self.refresh(force=False)

    def fit_contents(self):
        fit_dialog_contents(self)

    def outside_at(self, x, y):
        if self.window.get_visible_dialog() is not self or not self.get_can_close():
            return False
        ok, bounds = self.get_child().compute_bounds(self.window)
        return ok and not (bounds.origin.x <= x <= bounds.origin.x+bounds.size.width and
                           bounds.origin.y <= y <= bounds.origin.y+bounds.size.height)

    def claim_outside(self, gesture, _presses, x, y):
        if self.outside_at(x, y):
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)

    def dismiss_outside(self, _gesture, _presses, x, y):
        if self.outside_at(x, y):
            self.close()

    def set_status(self, text):
        ui.text(self.status, 'text', text)
        self.status.set_visible(bool(text))
        fit_dialog_contents(self)

    def display(self, error=None):
        self.list.set_visible(True)
        clear(self.list)
        rows = entries(self.window.store)
        errors = self.window.store.get('updates', {}).get('errors', {})
        problem = error or (_("No s'han pogut actualitzar tots els avisos. Es mostra la informació desada.") if errors else '')
        self.set_status(problem)
        self.clear_button.set_sensitive(bool(rows) and not self.busy)
        if not rows:
            self.list.append(ui.create(Adw.StatusPage,
                title=_("No s'han pogut carregar els avisos") if problem else _("No hi ha notificacions"),
                icon_name='network-error-symbolic' if problem else 'preferences-system-notifications-symbolic',
                description=_("Torna-ho a provar amb el botó d'actualització.") if problem else
                    _("Aquí veuràs comparticions, comentaris, mencions i assignacions dels teus taulers.")))
        for item in rows:
            row = Gtk.Box()
            row.add_css_class('notification-row')
            if not item['read']:
                row.add_css_class('card')
            button = Gtk.Button(hexpand=True)
            button.add_css_class('flat')
            content = Gtk.Box(spacing=12, margin_top=12, margin_bottom=12, margin_start=12, margin_end=6)
            content.append(Gtk.Image(icon_name=item['icon'], valign=Gtk.Align.START, pixel_size=20))
            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, hexpand=True)
            text.append(label(item['title'], 'heading' if not item['read'] else None, xalign=0, wrap=True))
            if item.get('body'):
                body = label(item['body'], 'notification-body', xalign=0, wrap=True, lines=4)
                tokens = list(item.get('mentions') or [])
                for board in self.window.snapshot.get('boards', []):
                    if not item.get('board_id') or item['board_id'] == board['id']:
                        tokens.extend(board_tokens(self.window, board['id']))
                MentionStyle(body, tokens)
                text.append(body)
            when = timestamp(item.get('datetime'))
            if when:
                when_label = label(when, 'notification-time', xalign=0)
                when_label.add_css_class('caption')
                when_label.add_css_class('dim-label')
                text.append(when_label)
            content.append(text)
            button.set_child(content)
            button.connect('clicked', lambda *_unused, item=item: self.activate(item))
            row.append(button)
            remove = icon_button('user-trash-symbolic', _("Esborra l'avís"),
                                 lambda *_unused, item=item: self.erase([item]))
            remove.add_css_class('flat')
            remove.add_css_class('notification-delete')
            remove.set_valign(Gtk.Align.CENTER)
            remove.set_margin_end(8)
            row.append(remove)
            self.list.append(row)
        fit_dialog_contents(self)

    def working(self, message):
        self.busy = True
        self.refresh_button.set_sensitive(False)
        self.clear_button.set_sensitive(False)
        self.list.set_sensitive(False)
        if not entries(self.window.store):
            clear(self.list)
            self.list.set_visible(False)
        self.set_status(message)

    def finished(self, _result, error):
        self.busy = False
        self.refresh_button.set_sensitive(True)
        self.list.set_sensitive(True)
        self.display(error)
        self.window.update_notification_badge()

    def refresh(self, *_unused, force=True):
        if self.busy:
            return
        self.working(_("S'estan actualitzant les notificacions…"))
        self.window.engine.refresh_updates(self.finished, force=force)

    def erase(self, rows):
        if self.busy or not rows:
            return
        self.working(_("S'estan esborrant els avisos…"))
        self.window.engine.run_updates(lambda api: erase_entries(api, self.window.store, rows), self.finished)

    def confirm_clear(self, *_unused):
        rows = entries(self.window.store)
        if not rows or self.busy:
            return
        prompt = ui.create(Adw.AlertDialog, heading=_("Vols esborrar tots els avisos?"),
                           body=_("S'esborraran els avisos que es mostren a la llista."))
        ui.response(prompt, 'cancel', _("Cancel·la"))
        ui.response(prompt, 'erase', _("Esborra-ho tot"))
        prompt.set_response_appearance('erase', Adw.ResponseAppearance.DESTRUCTIVE)
        prompt.set_default_response('cancel')
        prompt.connect('response', lambda _dialog, response: self.erase(rows) if response == 'erase' else None)
        prompt.present(self)

    def activate(self, row):
        if self.busy:
            return
        if row.get('notice_id'):
            self.working(_("S'estan actualitzant les notificacions…"))
            def done(result, error):
                if error:
                    self.finished(result, error)
                    return
                mark_read(self.window.store, row['key'])
                self.window.update_notification_badge()
                self.close()
                self.window.open_update(row)
            self.window.engine.run_updates(lambda api: api.dismiss_notification(row['notice_id']), done)
        else:
            mark_read(self.window.store, row['key'])
            self.window.update_notification_badge()
            self.close()
            self.window.open_update(row)
