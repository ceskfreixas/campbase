# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Board label creation and card membership, using native Adwaita controls."""
from . import localization as ui
from gi.repository import Adw, GObject, Gtk, Pango
from .i18n import _
from .choosers import ColorChooser
from .widgets import label, text_icon_button, clear, color_dot
from .dialog_widgets import dialog_form


class LabelSelector(Gtk.Box):
    __gsignals__ = {"changed": (GObject.SignalFlags.RUN_FIRST, None, ())}

    def __init__(self, window, card=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.window = window
        self.board_id = window.board_id
        board = next((board for board in window.snapshot["boards"] if board["id"] == self.board_id), {})
        original = (card or {}).get("labels") or []
        self.labels = {item["id"]: item for item in [*(board.get("labels") or []), *original] if item.get("id")}
        self.selected = {item["id"] for item in original if item.get("id")}
        header = Gtk.Box(spacing=12)
        header.append(label(_("Etiquetes"), "heading", xalign=0, hexpand=True))
        create = text_icon_button("list-add-symbolic", _("Etiqueta nova"))
        create.add_css_class("flat")
        create.connect("clicked", lambda *_unused: NewLabelDialog(self).present(self.get_root()))
        header.append(create)
        self.append(header)
        self.choices = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                                   column_spacing=6, row_spacing=6, min_children_per_line=1,
                                   max_children_per_line=4, valign=Gtk.Align.START)
        self.choices.add_css_class("label-choices")
        self.append(self.choices)
        self.empty = label(_("Encara no hi ha etiquetes en aquest tauler."), "dim-label", wrap=True, xalign=0)
        self.append(self.empty)
        self.buttons = {}
        self.refresh()

    def refresh(self):
        clear(self.choices)
        self.buttons = {}
        for item in sorted(self.labels.values(), key=lambda item: item["title"].casefold()):
            button = ui.create(Gtk.ToggleButton, tooltip_text=item["title"])
            button.add_css_class("label-choice")
            box = Gtk.Box(spacing=6)
            box.append(color_dot(item.get("color") or "77767b"))
            box.append(label(item["title"], ellipsize=Pango.EllipsizeMode.END, max_width_chars=12))
            button.set_child(box)
            ui.accessible(button, [Gtk.AccessibleProperty.LABEL], [item["title"]])
            button.set_active(item["id"] in self.selected)
            button.connect("toggled", self.toggled, item["id"])
            self.buttons[item["id"]] = button
            self.choices.insert(button, -1)
        self.choices.set_visible(bool(self.labels))
        self.empty.set_visible(not self.labels)

    def toggled(self, button, label_id):
        if button.get_active():
            self.selected.add(label_id)
        else:
            self.selected.discard(label_id)
        self.emit("changed")

    def selected_labels(self):
        return [self.labels[label_id] for label_id in sorted(self.selected)]

    def created(self, item):
        self.labels[item["id"]] = item
        self.selected.add(item["id"])
        self.window.store.cache_label(self.board_id, item)
        self.refresh()
        self.emit("changed")
        self.window.render()
        if not self.window.demo:
            self.window.engine.sync(read_only=not self.window.store.settings().get("auto_sync", True))


class NewLabelDialog(Adw.Dialog):
    def __init__(self, selector):
        super().__init__(title=_("Etiqueta nova"), content_width=420)
        ui.widget(self, title=_("Etiqueta nova"))
        self.selector = selector
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        self.create_button = ui.create(Gtk.Button, label=_("Crea l'etiqueta"))
        self.create_button.add_css_class("suggested-action")
        self.create_button.connect("clicked", self.create)
        header.pack_end(self.create_button)
        outer.append(header)
        form = dialog_form()
        self.name = ui.create(Gtk.Entry, placeholder_text=_("Nom de l'etiqueta"), max_length=100, activates_default=True)
        form.append(self.name)
        color_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        color_section.append(label(_("Color"), "heading", xalign=0))
        self.color = ColorChooser("#3584e4")
        color_section.append(self.color)
        form.append(color_section)
        footer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        hint = label(_("Disponible per a totes les targetes d'aquest tauler."), "dim-label", wrap=True, xalign=0)
        hint.add_css_class("caption")
        footer.append(hint)
        self.status = label("", "dim-label", wrap=True, xalign=0, visible=False)
        footer.append(self.status)
        form.append(footer)
        outer.append(form)
        self.set_child(outer)
        self.set_default_widget(self.create_button)

    def create(self, *_unused):
        title = self.name.get_text().strip()
        if not title:
            self.name.add_css_class("error")
            self.name.grab_focus()
            return
        if self.selector.window.demo:
            item = {"id": max(self.selector.labels, default=0)+1, "title": title,
                    "color": self.color.selected_color[1:], "boardId": self.selector.board_id}
            self.selector.created(item)
            self.close()
            return
        self.create_button.set_sensitive(False)
        self.name.set_sensitive(False)
        self.color.set_sensitive(False)
        self.set_can_close(False)
        ui.text(self.status, 'text', _("S'està creant l'etiqueta…"))
        self.status.set_visible(True)
        def done(item, error):
            self.create_button.set_sensitive(True)
            self.name.set_sensitive(True)
            self.color.set_sensitive(True)
            self.set_can_close(True)
            if error:
                ui.text(self.status, 'text', error)
                return
            self.selector.created(item)
            self.close()
        self.selector.window.engine.run(
            lambda api: api.create_label(self.selector.board_id, title, self.color.selected_color), done)
