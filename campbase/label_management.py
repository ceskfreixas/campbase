# SPDX-License-Identifier: GPL-3.0-or-later
"""Small, confirmed board-label manager; changes preserve open card drafts."""
from gi.repository import Adw, GLib, Gtk
from . import localization as ui
from .i18n import _
from .widgets import label, icon_button, color_dot
from .dialog_widgets import dialog_form
from .choosers import ColorChooser


class LabelManagerDialog(Adw.Dialog):
    def __init__(self, selector):
        super().__init__(content_width=440, follows_content_size=True)
        ui.widget(self, title=_("Gestiona les etiquetes"))
        self.selector, self.window = selector, selector.window
        self.busy = False
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.append(Adw.HeaderBar())
        form = dialog_form()
        self.status = label('', 'dim-label', xalign=0, wrap=True, visible=False)
        form.append(self.status)
        self.group = Adw.PreferencesGroup()
        form.append(self.group)
        self.rows = []
        outer.append(Gtk.ScrolledWindow(child=form, propagate_natural_height=True, max_content_height=560,
            hscrollbar_policy=Gtk.PolicyType.NEVER))
        self.set_child(outer)
        self.load()

    def set_status(self, text):
        ui.text(self.status, 'text', text)
        self.status.set_visible(bool(text))

    def load(self):
        if self.busy or self.window.demo:
            return
        self.busy = True
        self.set_status(_("S'estan carregant les etiquetes…"))
        def loaded(board, error):
            self.busy = False
            self.set_status(error or '')
            if not error:
                self.display(board)
        self.window.engine.run(lambda api: api.check_board(self.selector.board_id), loaded)

    def display(self, board):
        for row in self.rows:
            self.group.remove(row)
        self.rows = []
        allowed = board.get('permissions', {}).get('PERMISSION_MANAGE', False)
        for item in sorted(board.get('labels') or [], key=lambda item: item['title'].casefold()):
            row = Adw.ActionRow(title=item['title'], use_markup=False)
            row.add_prefix(color_dot(item.get('color') or '77767b'))
            edit = icon_button('document-edit-symbolic', _("Edita l'etiqueta"),
                lambda *_, item=item: LabelEditDialog(self, item).present(self))
            edit.set_valign(Gtk.Align.CENTER)
            edit.set_margin_top(8)
            edit.set_margin_bottom(8)
            edit.set_sensitive(allowed)
            row.add_suffix(edit)
            self.group.add(row)
            self.rows.append(row)
        if not self.rows:
            self.set_status(_("Encara no hi ha etiquetes en aquest tauler."))

    def confirmed(self, board):
        self.window.store.replace_board_labels(board)
        self.selector.labels = {x['id']: x for x in board.get('labels') or []}
        self.selector.selected.intersection_update(self.selector.labels)
        self.selector.refresh()
        self.selector.emit('changed')
        self.window.render()
        self.display(board)


class LabelEditDialog(Adw.Dialog):
    def __init__(self, manager, original):
        super().__init__(content_width=420, follows_content_size=True)
        ui.widget(self, title=_("Edita l'etiqueta"))
        self.manager, self.original = manager, dict(original)
        self.busy = False
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        self.save = ui.create(Gtk.Button, label=_("Desa"))
        self.save.add_css_class('suggested-action')
        self.save.connect('clicked', lambda *_: self.perform())
        header.pack_end(self.save)
        outer.append(header)
        self.form = dialog_form()
        self.name = Gtk.Entry(text=original['title'], max_length=100)
        ui.accessible(self.name, [Gtk.AccessibleProperty.LABEL], [_("Nom de l'etiqueta")])
        self.form.append(self.name)
        self.color = ColorChooser('#'+original['color'].lstrip('#'))
        color_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        color_section.append(label(_("Color"), 'heading', xalign=0))
        color_section.append(self.color)
        self.form.append(color_section)
        remove = ui.create(Gtk.Button, label=_("Esborra l'etiqueta"), halign=Gtk.Align.START)
        remove.add_css_class('destructive-action')
        remove.connect('clicked', self.confirm_delete)
        self.form.append(remove)
        self.status = label('', 'dim-label', xalign=0, wrap=True, visible=False)
        self.form.append(self.status)
        outer.append(self.form)
        self.set_child(outer)

    def confirm_delete(self, *_unused):
        prompt = ui.create(Adw.AlertDialog, heading=_("Esborra l'etiqueta"),
            body=_("L'etiqueta «{title}» es retirarà de totes les targetes del tauler.").format(title=self.original['title']))
        ui.response(prompt, 'cancel', _("Cancel·la"))
        ui.response(prompt, 'delete', _("Esborra"))
        prompt.set_response_appearance('delete', Adw.ResponseAppearance.DESTRUCTIVE)
        prompt.set_default_response('cancel')
        prompt.set_close_response('cancel')
        prompt.connect('response', lambda _, choice: self.perform(delete=True) if choice == 'delete' else None)
        prompt.present(self)

    def perform(self, delete=False):
        if self.busy:
            return
        title, color = self.name.get_text().strip(), self.color.selected_color
        if not delete and not title:
            self.name.grab_focus()
            return
        window, board_id = self.manager.window, self.manager.selector.board_id
        if any(op['payload'].get('board_id') == board_id for op in window.store.operations()):
            ui.text(self.status, 'text', _("Sincronitza els canvis pendents del tauler abans de gestionar les etiquetes."))
            self.status.set_visible(True)
            return
        self.busy = True
        self.form.set_sensitive(False)
        self.save.set_sensitive(False)
        self.set_can_close(False)
        def done(board, error):
            self.busy = False
            self.set_can_close(True)
            self.form.set_sensitive(True)
            self.save.set_sensitive(True)
            if error:
                ui.text(self.status, 'text', error)
                self.status.set_visible(True)
            else:
                # Let Adwaita restore focus before replacing the row that
                # opened this dialog (notably on libadwaita 1.5).
                self.connect('closed', lambda *_: GLib.idle_add(self.manager.confirmed, board))
                self.force_close()
        window.engine.run(lambda api: api.manage_label(board_id, self.original,
            title=title, color=color, delete=delete), done)
