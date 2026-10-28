# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Paste clipboard images through the same private image pipeline as file uploads."""
from . import localization as ui
from .i18n import _, ngettext
from gi.repository import Adw, Gdk, Gio, GLib, GObject


class ImageClipboard:
    def setup_clipboard(self):
        self.clipboard = self.view.get_clipboard()
        self.clipboard_handler = 0
        actions = Gio.SimpleActionGroup()
        self.paste_image_action = Gio.SimpleAction.new("paste-image", None)
        self.paste_image_action.connect("activate", lambda *_unused: self.paste_image())
        actions.add_action(self.paste_image_action)
        self.view.insert_action_group("campbase", actions)
        menu = Gio.Menu()
        ui.menu_append(menu, _("Enganxa una imatge"), "campbase.paste-image")
        self.view.set_extra_menu(menu)
        self.view.connect("paste-clipboard", self.paste_requested)
        self.view.connect("realize", self.clipboard_realized)
        self.view.connect("unrealize", self.clipboard_unrealized)
        self.clipboard_changed()

    def clipboard_has_image(self):
        formats = self.clipboard.get_formats()
        return any(GObject.type_is_a(kind, Gdk.Texture) for kind in formats.get_gtypes()) or any(mime in formats.get_mime_types()
                    for mime in ("image/png", "image/jpeg", "image/webp", "image/gif"))

    def clipboard_changed(self, *_unused):
        self.paste_image_action.set_enabled(self.clipboard_has_image())

    def clipboard_realized(self, *_unused):
        if not self.clipboard_handler:
            self.clipboard_handler = self.clipboard.connect("changed", self.clipboard_changed)
        self.clipboard_changed()

    def clipboard_unrealized(self, *_unused):
        if self.clipboard_handler:
            self.clipboard.disconnect(self.clipboard_handler)
            self.clipboard_handler = 0

    def paste_requested(self, view):
        if self.clipboard_has_image():
            GObject.signal_stop_emission_by_name(view, "paste-clipboard")
            self.paste_image()

    def paste_image(self):
        if not self.clipboard_has_image():
            return
        bounds = self.buffer.get_selection_bounds()
        positions = bounds or (self.buffer.get_iter_at_mark(self.buffer.get_insert()),)
        marks = [self.buffer.create_mark(None, position, True) for position in positions]
        def received(clipboard, result):
            try:
                texture = clipboard.read_texture_finish(result)
                if texture is None:
                    raise ValueError(_("El porta-retalls no conté cap imatge compatible."))
                if texture.get_width()*texture.get_height() > 40_000_000:
                    raise ValueError(_("La imatge és massa gran. Tria'n una de mida més petita."))
                record = self.assets.import_bytes(texture.save_to_png_bytes().get_data(), _("Imatge enganxada.png"))
                self._capture()
                if len(marks) == 2:
                    self.buffer.delete(self.buffer.get_iter_at_mark(marks[0]), self.buffer.get_iter_at_mark(marks[1]))
                self.buffer.place_cursor(self.buffer.get_iter_at_mark(marks[0]))
                self.insert_image("bivac-image://"+record["token"], record["name"])
                self._capture()
                self.view.grab_focus()
            except (GLib.Error, ValueError):
                alert = ui.create(Adw.AlertDialog, heading=_("No s'ha pogut enganxar la imatge"),
                                        body=_("Copia una imatge compatible de menys de 16 MB i torna-ho a provar."))
                ui.response(alert, "close", _("D'acord"))
                alert.present(self.window)
            finally:
                for mark in marks:
                    self.buffer.delete_mark(mark)
        self.clipboard.read_texture_async(None, received)
