# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Owner-only board deletion from the sidebar, with explicit confirmation."""
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gtk
from . import localization as ui
from .i18n import _
from .collaboration import person
from .people import current_person
from .dialog_widgets import dialog_form
from .widgets import label, icon_button
from .deck import ConflictError
from .alerts import message


def is_board_owner(window, board):
    uid = current_person(window)['uid']
    return bool(uid and uid == person(board.get('owner'))['uid'])


def board_delete_button(window, board):
    if not is_board_owner(window, board):
        return None
    button = icon_button('user-trash-symbolic', _("Esborra el tauler"),
                         lambda *_unused: BoardDeletionDialog(window, board).present(window))
    button.add_css_class('flat')
    button.add_css_class('destructive-action')
    button.add_css_class('hover-action')
    button.set_valign(Gtk.Align.CENTER)
    return button


class BoardDeletionDialog(Adw.Dialog):
    def __init__(self, window, board):
        super().__init__(content_width=440, follows_content_size=True)
        ui.widget(self, title=_("Esborra el tauler"))
        self.window, self.board = window, dict(board)
        self.started = False
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, width_request=440)
        header = Adw.HeaderBar()
        self.cancel_button = ui.create(Gtk.Button, label=_("Cancel·la"))
        self.cancel_button.connect('clicked', lambda *_unused: self.close())
        header.pack_start(self.cancel_button)
        self.action = ui.create(Gtk.Button, label=_("Esborra"))
        self.action.add_css_class('destructive-action')
        self.action.connect('clicked', self.start)
        header.pack_end(self.action)
        outer.append(header)
        form = dialog_form()
        form.append(label(board['title'], 'title-3', xalign=0, wrap=True))
        stacks = window.snapshot.get('stacks', {}).get(str(board['id']), [])
        count = sum(len(stack.get('cards') or []) for stack in stacks)
        form.append(label(_("Columnes: {columns} · Targetes: {cards}").format(columns=len(stacks), cards=count), xalign=0, wrap=True))
        form.append(label(_("S'esborrarà el tauler de Nextcloud Deck, amb les columnes i les targetes que conté."), xalign=0, wrap=True))
        self.spinner = Gtk.Spinner(visible=False, halign=Gtk.Align.CENTER)
        self.status = label('', 'dim-label', xalign=0, wrap=True, visible=False)
        form.append(self.spinner)
        form.append(self.status)
        outer.append(Gtk.ScrolledWindow(child=form, propagate_natural_height=True, max_content_height=500,
                                        hscrollbar_policy=Gtk.PolicyType.NEVER))
        self.set_child(outer)
        self.set_default_widget(self.cancel_button)
        self.set_focus(self.cancel_button)
        self.action.set_sensitive(is_board_owner(window, board) and not self.pending())
        if self.pending():
            self.set_status(_("Resol els canvis pendents d'aquest tauler abans d'esborrar-lo."))

    def pending(self):
        return any(operation['payload'].get('board_id') == self.board['id'] for operation in self.window.store.operations())

    def set_status(self, text):
        ui.text(self.status, 'text', text)
        self.status.set_visible(bool(text))

    def start(self, *_unused):
        if self.started or self.pending() or not is_board_owner(self.window, self.board):
            return
        self.started = True
        self.set_can_close(False)
        self.cancel_button.set_sensitive(False)
        self.action.set_sensitive(False)
        self.spinner.set_visible(True)
        self.spinner.set_spinning(True)
        self.set_status(_("S'està esborrant el tauler…"))
        def remove(api):
            if self.pending():
                raise ConflictError(_("Resol els canvis pendents d'aquest tauler abans d'esborrar-lo."))
            api.delete_board(self.board['id'])
            self.window.store.remove_board(self.board['id'])
        self.window.engine.run(remove, self.finished)

    def finished(self, _result, error):
        self.force_close()
        self.window.render()
        if error:
            message(self.window, _("No s'ha pogut esborrar el tauler"), error)
