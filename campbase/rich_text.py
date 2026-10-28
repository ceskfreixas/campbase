# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Native formatted text, serialized to Deck-compatible Markdown."""
from . import localization as ui
from .i18n import _, ngettext
import re
from urllib.parse import urlsplit

import gi
gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk, Pango
from .rich_document import RichDocument, PARSER
from .clipboard import ImageClipboard

from .widgets import icon_button, label



class RichTextEditor(Gtk.Box, RichDocument, ImageClipboard):
    __gsignals__ = {"changed": (GObject.SignalFlags.RUN_FIRST, None, ())}

    def __init__(self, window, text=""):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.window = window
        self.assets = window.assets
        self.loading = False
        self.modified = False
        self.links = {}
        self.code_blocks = {}
        self.image_nodes = []
        self.history = []
        self.history_index = 0
        self.history_timer = 0
        self.add_css_class("rich-editor")
        self.buffer = Gtk.TextBuffer()
        self.buffer.create_tag("bold", weight=Pango.Weight.BOLD)
        self.buffer.create_tag("italic", style=Pango.Style.ITALIC)
        self.buffer.create_tag("strike", strikethrough=True)
        self.buffer.create_tag("underline", underline=Pango.Underline.SINGLE)
        self.buffer.create_tag("code", family="monospace")
        self.buffer.create_tag("literal", family="monospace")
        self.buffer.create_tag("codeblock", family="monospace")
        for level in range(1, 4):
            self.buffer.create_tag("h" + str(level), weight=Pango.Weight.BOLD, scale={1: 1.5, 2: 1.3, 3: 1.15}[level])
        self.view = Gtk.TextView(buffer=self.buffer, wrap_mode=Gtk.WrapMode.WORD_CHAR, accepts_tab=False,
                                 top_margin=14, bottom_margin=14, left_margin=14, right_margin=14)
        self.view.add_css_class("description-editor")
        self._toolbar()
        self.append(Gtk.ScrolledWindow(child=self.view, hscrollbar_policy=Gtk.PolicyType.NEVER,
                                       min_content_height=240, vexpand=True))
        self.set_markdown(text)
        self.history = [text]
        self.buffer.connect("changed", self._changed)
        self.keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        self.keys.connect("key-pressed", self.key_pressed)
        self.view.add_controller(self.keys)
        self.setup_clipboard()

    def _toolbar(self):
        tools = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, column_spacing=0, row_spacing=0,
                             min_children_per_line=1, max_children_per_line=30, halign=Gtk.Align.START)
        tools.add_css_class("format-toolbar")
        specs = [("format-text-bold-symbolic", _("Negreta · Ctrl+B"), lambda: self.toggle("bold")),
                 ("format-text-italic-symbolic", _("Cursiva · Ctrl+I"), lambda: self.toggle("italic")),
                 ("format-text-underline-symbolic", _("Subratllat · Ctrl+U · La visualització en altres clients pot variar"), lambda: self.toggle("underline")),
                 ("format-text-strikethrough-symbolic", _("Ratllat"), lambda: self.toggle("strike")),
                 ("view-list-bullet-symbolic", _("Llista amb pics"), lambda: self.list_format(False)),
                 ("view-list-ordered-symbolic", _("Llista numerada"), lambda: self.list_format(True)),
                 ("cat.cesk.Campbase-link-symbolic", _("Insereix un enllaç"), self.insert_link_dialog),
                 ("image-x-generic-symbolic", _("Insereix una imatge"), self.choose_image),
                 ("edit-undo-symbolic", _("Desfés · Ctrl+Z"), self.undo),
                 ("edit-redo-symbolic", _("Refés · Ctrl+Maj+Z"), self.redo)]
        for icon, title, callback in specs:
            button = icon_button(icon, title, lambda _unused, fn=callback: fn())
            button.add_css_class("flat")
            button.set_focus_on_click(False)
            tools.insert(button, -1)
        headings = ui.create(Gtk.MenuButton, icon_name="format-text-rich-symbolic", tooltip_text=_("Títols, citacions i codi"))
        headings.add_css_class("flat")
        popover = Gtk.Popover()
        menu = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, margin_top=6, margin_bottom=6, margin_start=6, margin_end=6)
        for title, callback in [(_("Text normal"), lambda: self.heading(0)), (_("Títol gran"), lambda: self.heading(1)),
                                (_("Títol mitjà"), lambda: self.heading(2)), (_("Títol petit"), lambda: self.heading(3)),
                                (_("Citació"), self.quote), (_("Codi"), lambda: self.toggle("code")),
                                (_("Treu el format"), self.clear_format)]:
            button = ui.create(Gtk.Button, label=title)
            button.add_css_class("flat")
            button.connect("clicked", lambda _unused, fn=callback: (popover.popdown(), fn()))
            menu.append(button)
        popover.set_child(menu)
        headings.set_popover(popover)
        tools.insert(headings, 4)
        self.append(tools)
        self.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

    def get_buffer(self):
        return self.buffer

    def _changed(self, *_unused):
        if self.loading:
            return
        self.modified = True
        self.emit("changed")
        if self.history_timer:
            GLib.source_remove(self.history_timer)
        self.history_timer = GLib.timeout_add(250, self._capture)

    def _capture(self):
        if self.history_timer:
            GLib.source_remove(self.history_timer)
            self.history_timer = 0
        value = self.get_markdown()
        if value != self.history[self.history_index]:
            self.history = self.history[:self.history_index+1] + [value]
            self.history_index += 1
        return GLib.SOURCE_REMOVE

    def undo(self):
        if self.history_timer:
            GLib.source_remove(self.history_timer)
            self.history_timer = 0
        self._capture()
        if self.history_index:
            self.history_index -= 1
            self.set_markdown(self.history[self.history_index])
            self.emit("changed")

    def redo(self):
        if self.history_index < len(self.history)-1:
            self.history_index += 1
            self.set_markdown(self.history[self.history_index])
            self.emit("changed")

    def selection(self, whole_line=False):
        bounds = self.buffer.get_selection_bounds()
        if bounds:
            start, end = bounds
        else:
            start = self.buffer.get_iter_at_mark(self.buffer.get_insert())
            end = start.copy()
            if not whole_line:
                start.backward_word_start()
                end.forward_word_end()
        if whole_line:
            start.set_line_offset(0)
            if not end.ends_line():
                end.forward_to_line_end()
        return start, end

    def toggle(self, name):
        self._capture()
        start, end = self.selection()
        if start.equal(end):
            return
        tag = self.buffer.get_tag_table().lookup(name)
        if start.has_tag(tag):
            self.buffer.remove_tag(tag, start, end)
        else:
            self.buffer.apply_tag(tag, start, end)
        self._changed()
        self._capture()
        self.view.grab_focus()

    def heading(self, level):
        self._capture()
        start, end = self.selection(True)
        for n in range(1,4):
            self.buffer.remove_tag_by_name("h"+str(n), start, end)
        if level:
            self.buffer.apply_tag_by_name("h"+str(level), start, end)
        self._changed(); self._capture(); self.view.grab_focus()

    def prefix_lines(self, replacement):
        self._capture()
        start, end = self.selection(True)
        first, last = start.get_line(), end.get_line()
        self.buffer.begin_user_action()
        for line in range(last, first-1, -1):
            start = self.buffer.get_iter_at_line(line).iter
            end = start.copy()
            if not end.ends_line():
                end.forward_to_line_end()
            text = self.buffer.get_text(start, end, True)
            match = re.match(r"^(\s*)(?:• |\d+\. |[-*] |❯ )?", text)
            prefix = replacement(line-first+1, match[1])
            cut = self.buffer.get_iter_at_offset(start.get_offset()+len(match[0]))
            self.buffer.delete(start, cut)
            self.buffer.insert(start, prefix)
        self.buffer.end_user_action()
        self.view.grab_focus()

    def list_format(self, ordered):
        self.prefix_lines(lambda index, indent: indent+(f"{index}. " if ordered else "• "))

    def quote(self):
        self.prefix_lines(lambda index, indent: indent+"❯ ")

    def clear_format(self):
        self._capture()
        start, end = self.selection()
        self.buffer.remove_all_tags(start, end)
        self._changed(); self._capture()

    def insert_link_dialog(self):
        bounds = self.selection()
        marks = [self.buffer.create_mark(None, it, True) for it in bounds]
        dialog = ui.create(Adw.AlertDialog, heading=_("Insereix un enllaç"))
        entry = ui.create(Gtk.Entry, placeholder_text="https://…", activates_default=True)
        dialog.set_extra_child(entry)
        ui.response(dialog, "cancel", _("Cancel·la"));ui.response(dialog, "add", _("Insereix"))
        dialog.set_default_response("add")
        def response(_unused, action):
            if action == "add":
                url = entry.get_text().strip()
                if urlsplit(url).scheme not in {"https", "http", "mailto"}:
                    return
                start, end = [self.buffer.get_iter_at_mark(m) for m in marks]
                if start.equal(end):
                    self.buffer.insert(start, url)
                    start = self.buffer.get_iter_at_mark(marks[0])
                    end = self.buffer.get_iter_at_offset(start.get_offset()+len(url))
                name = "link-" + str(len(self.links))
                self.links[name] = url
                tag = self.buffer.create_tag(name, underline=Pango.Underline.SINGLE, foreground="#3584e4")
                self.buffer.apply_tag(tag, start, end)
                self._changed()
            for mark in marks:
                self.buffer.delete_mark(mark)
        dialog.connect("response", response)
        dialog.present(self.window)

    def choose_image(self):
        dialog = ui.create(Gtk.FileDialog, title=_("Insereix una imatge"))
        filter = ui.create(Gtk.FileFilter, name=_("Imatges"))
        for mime in ["image/png", "image/jpeg", "image/webp", "image/gif"]:
            filter.add_mime_type(mime)
        filters = Gio.ListStore.new(Gtk.FileFilter); filters.append(filter)
        dialog.set_filters(filters)
        mark = self.buffer.create_mark(None, self.buffer.get_iter_at_mark(self.buffer.get_insert()), True)
        def selected(dialog, result):
            try:
                file = dialog.open_finish(result)
                record = self.assets.import_file(file)
                self.buffer.place_cursor(self.buffer.get_iter_at_mark(mark))
                self.insert_image("bivac-image://"+record["token"], record["name"])
            except GLib.Error:
                pass
            except ValueError as error:
                alert = ui.create(Adw.AlertDialog, heading=_("No s'ha pogut afegir la imatge"), body=str(error))
                ui.response(alert, "close", _("D'acord")); alert.present(self.window)
            finally:
                self.buffer.delete_mark(mark)
        dialog.open(self.window, None, selected)

    def insert_image(self, url, alt=_("Imatge")):
        position = self.buffer.get_end_iter() if self.loading else self.buffer.get_iter_at_mark(self.buffer.get_insert())
        anchor = self.buffer.create_child_anchor(position)
        widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, margin_top=8, margin_bottom=8)
        picture = Gtk.Picture(width_request=240, height_request=150, can_shrink=True, content_fit=Gtk.ContentFit.CONTAIN)
        widget.append(picture)
        caption = label(alt or _("Imatge"), "dim-label", max_width_chars=30, ellipsize=Pango.EllipsizeMode.END)
        widget.append(caption)
        self.view.add_child_at_anchor(widget, anchor)
        node = {"anchor": anchor, "widget": widget, "url": url, "alt": alt}
        self.image_nodes.append(node)
        record = self.assets.local(url)
        if record:
            picture.set_filename(str(self.assets.resolve(record["path"])))
        else:
            cached = self.assets.remote_path(url)
            if cached.exists():
                picture.set_filename(str(cached))
            elif not self.window.demo:
                def loaded(data, error):
                    if not error:
                        try:
                            path = self.assets.cache_image(url, data)
                            picture.set_filename(str(path))
                            return
                        except ValueError:
                            pass
                    ui.text(caption, 'text', (alt or _("Imatge")) + _(" · No s'ha pogut carregar"))
                self.window.engine.run(lambda api: api.fetch_image(url), loaded)

    def local_images(self):
        result = []
        for node in self.image_nodes:
            if not node["anchor"].get_deleted():
                record = self.assets.local(node["url"])
                if record:
                    result.append(record)
        return result

    def key_pressed(self, _controller, key, _keycode, state):
        if state & Gdk.ModifierType.CONTROL_MASK:
            if key in (Gdk.KEY_v, Gdk.KEY_V) and self.clipboard_has_image():
                self.paste_image()
                return True
            if key in (Gdk.KEY_b,Gdk.KEY_B):self.toggle("bold");return True
            if key in (Gdk.KEY_i,Gdk.KEY_I):self.toggle("italic");return True
            if key in (Gdk.KEY_u,Gdk.KEY_U):self.toggle("underline");return True
            if key in (Gdk.KEY_z,Gdk.KEY_Z):
                self.redo() if state & Gdk.ModifierType.SHIFT_MASK else self.undo()
                return True
        if key == Gdk.KEY_Return and not (state & Gdk.ModifierType.SHIFT_MASK):
            cursor = self.buffer.get_iter_at_mark(self.buffer.get_insert())
            start = cursor.copy(); start.set_line_offset(0)
            text = self.buffer.get_text(start, cursor, True)
            match = re.match(r"^(\s*)(• |\d+\. |❯ )",text)
            if match:
                prefix = match[0]
                if text == prefix:
                    self.buffer.delete(start,cursor)
                else:
                    number = re.match(r"(\s*)(\d+)\. ",prefix)
                    if number:prefix = number[1]+str(int(number[2])+1)+". "
                    self.buffer.insert_at_cursor("\n"+prefix)
                return True
        return False
