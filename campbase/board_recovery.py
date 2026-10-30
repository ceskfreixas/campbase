# SPDX-License-Identifier: GPL-3.0-or-later
"""Account-scoped recent board recovery, including local presentation metadata."""
from gi.repository import Adw, Gtk
from . import localization as ui
from .i18n import _
from .widgets import label, icon_button
from .dialog_widgets import dialog_form
from .alerts import message


def recovery_key(api, board_id):
    return 'deleted_board:' + api.server + '|' + api.username + ':' + str(board_id)


def remember_deletion(window, board):
    api = window.engine.api
    record = {'id': board['id'], 'title': board['title'],
              'metadata': window.store.get('board_metadata', {}).get(str(board['id'])), 'colors': {}}
    colors = window.store.settings().get('colors', {})
    for stack in window.snapshot.get('stacks', {}).get(str(board['id']), []):
        if str(stack['id']) in colors:
            record['colors'][str(stack['id'])] = colors[str(stack['id'])]
    key = recovery_key(api, board['id'])
    # One independently indexed row avoids read/modify/write races across deletions.
    window.store.put(key, record)
    return key


def restore(window, key, finished=lambda: None):
    api = window.engine.api
    record = window.store.get(key)
    if not record or not api or key != recovery_key(api, record['id']):
        finished()
        return
    def action(current_api):
        current_api.restore_board(record['id'])
        snapshot = current_api.fetch(refresh_auth=False)
        if not any(board['id'] == record['id'] for board in snapshot['boards']):
            from .deck import DeckError
            raise DeckError(_("Deck no ha confirmat la restauració del tauler."))
        return snapshot
    def done(snapshot, error):
        if error:
            message(window, _("No s'ha pogut restaurar el tauler"), error)
        else:
            window.store.put('snapshot', snapshot)
            window.store.restore_board_presentation(record)
            window.store.put(key, None)
            window.board_id = record['id']
            window.render()
        finished()
    if window.engine.run(action, done) is None:
        finished()


def offer_undo(window, board):
    key = recovery_key(window.engine.api, board['id'])
    toast = ui.create(Adw.Toast, title=_("Tauler esborrat"), button_label=_("Desfés"), timeout=8)
    toast.connect('button-clicked', lambda *_: restore(window, key))
    window.toast_overlay.add_toast(toast)


class BoardRecoveryDialog(Adw.Dialog):
    def __init__(self, window):
        super().__init__(content_width=440, follows_content_size=True)
        ui.widget(self, title=_("Taulers esborrats recentment"))
        self.window = window
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.append(Adw.HeaderBar())
        self.form = dialog_form()
        self.explanation = label(_("Pots recuperar els taulers mentre Nextcloud encara els conservi."),
                                 'dim-label', xalign=0, wrap=True)
        self.form.append(self.explanation)
        # ActionRow inherits ListBoxRow and needs a ListBox for keyboard focus.
        self.rows = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.rows.add_css_class('boxed-list')
        self.form.append(self.rows)
        self.empty_status = label(_("No hi ha taulers per recuperar."), 'dim-label', xalign=0, wrap=True)
        self.form.append(self.empty_status)
        outer.append(Gtk.ScrolledWindow(child=self.form, propagate_natural_height=True,
            max_content_height=560, hscrollbar_policy=Gtk.PolicyType.NEVER))
        self.set_child(outer)
        self.display()

    def display(self):
        from .widgets import clear
        clear(self.rows)
        api = self.window.engine.api
        records = self.window.store.deleted_boards(api.server, api.username) if api else []
        self.explanation.set_visible(bool(records))
        self.rows.set_visible(bool(records))
        self.empty_status.set_visible(not records)
        for key, item in records:
            row = Adw.ActionRow(title=item['title'], use_markup=False)
            button = icon_button('edit-undo-symbolic', _("Restaura el tauler"),
                lambda *_, key=key: self.start(key))
            button.set_valign(Gtk.Align.CENTER)
            button.set_margin_top(8)
            button.set_margin_bottom(8)
            row.add_suffix(button)
            self.rows.append(row)
    def start(self, key):
        self.form.set_sensitive(False)
        self.set_can_close(False)
        def finished():
            self.set_can_close(True)
            self.form.set_sensitive(True)
            self.display()
        restore(self.window, key, finished)
