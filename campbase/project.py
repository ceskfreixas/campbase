# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Project identity: the Deck title and private local presentation metadata."""
from . import localization as ui
from .i18n import _, ngettext
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk, Pango

from .widgets import icon_button, label, text_icon_button
from .dialog_widgets import dialog_form
from .choosers import IconChooser, PROJECT_ICONS

DESCRIPTION_LIMIT = 160


def project_image(window, metadata, size=44):
    path = window.assets.resolve(metadata.get("image"))
    if path:
        return Gtk.Image(gicon=Gio.FileIcon.new(Gio.File.new_for_path(str(path))),
                         pixel_size=size, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
    if metadata.get("icon") == "":
        return Gtk.Image(icon_name="view-grid-symbolic", pixel_size=min(size, 32))
    if metadata.get("icon") in PROJECT_ICONS:
        return Gtk.Image(icon_name=metadata["icon"], pixel_size=min(size, 32))
    if metadata.get("emoji"):
        attributes = Pango.AttrList()
        attributes.insert(Pango.attr_size_new(min(size, 38)*Pango.SCALE))
        return label(metadata["emoji"], attributes=attributes)
    return Gtk.Image(icon_name="view-grid-symbolic", pixel_size=min(size, 32))


def project_heading(window, board, metadata):
    row = Gtk.Box(spacing=12, halign=Gtk.Align.START)
    image = project_image(window, metadata)
    if image is not None:
        row.append(image)
    row.append(label(board["title"], "board-title", xalign=0, wrap=True))
    edit = icon_button("document-edit-symbolic", _("Edita el projecte"),
                       lambda *_unused: ProjectDialog(window, board).present(window))
    edit.set_sensitive(window.demo or board.get('permissions', {}).get('PERMISSION_MANAGE', True))
    edit.add_css_class("flat")
    edit.add_css_class('project-edit')
    edit.set_valign(Gtk.Align.CENTER)
    row.append(edit)
    return row


def board_header(window, board, count_text):
    """Two centered blocks: project identity and actions with board metadata."""
    from .collaboration import person, members
    from .people import avatar
    from .sharing import SharingDialog
    from .conversations import ConversationsDialog

    header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, hexpand=True)
    header.add_css_class('board-header')
    top = (Adw.WrapBox(child_spacing=24, line_spacing=12, align=1)
           if hasattr(Adw, 'WrapBox') else Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12))
    metadata = window.store.get('board_metadata', {}).get(str(board['id']), {})
    identity = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                       hexpand=True, valign=Gtk.Align.CENTER)
    identity.add_css_class('board-identity')
    identity.append(project_heading(window, board, metadata))
    description = metadata.get('description', board.get('description') or '')
    if description:
        identity.append(label(description, 'board-description', xalign=0, wrap=True))
    top.append(identity)

    tools = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, valign=Gtk.Align.CENTER)

    actions = Gtk.Box(spacing=8, halign=Gtk.Align.END, valign=Gtk.Align.CENTER)
    actions.add_css_class('board-actions')
    controls = [
        ('document-new-symbolic', _("Crea una targeta"), lambda: window.new_card(), 'PERMISSION_EDIT'),
        ('view-dual-symbolic', _("Crea una columna"), lambda: window.new_column(), 'PERMISSION_MANAGE'),
        ('system-users-symbolic', _("Comparteix el tauler"),
         lambda: SharingDialog(window, board).present(window), None),
        ('cat.cesk.Campbase-conversations-symbolic', _("Converses"),
         lambda: ConversationsDialog(window, board).present(window), None),
    ]
    for index, (icon, title, callback, permission) in enumerate(controls):
        if index == 2:
            actions.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL, margin_start=4, margin_end=4,
                                         margin_top=6, margin_bottom=6))
        button = icon_button(icon, title, lambda *_unused, action=callback: action())
        if index == 0:
            button.add_css_class('suggested-action')
        if permission:
            button.set_sensitive(window.demo or board.get('permissions', {}).get(permission, True))
        elif icon == 'cat.cesk.Campbase-conversations-symbolic':
            button.set_sensitive(not window.demo and window.engine.api is not None)
        actions.append(button)
    actions.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL, margin_start=4, margin_end=4,
                                 margin_top=6, margin_bottom=6))
    window.mine_filter = ui.create(Gtk.ToggleButton,
        icon_name='cat.cesk.Campbase-assigned-symbolic', tooltip_text=_("Assignades a mi"))
    window.mine_filter.set_active(window.only_mine)
    ui.accessible(window.mine_filter, [Gtk.AccessibleProperty.LABEL], [_("Assignades a mi")])
    window.mine_filter.connect('toggled', window.filter_mine)
    actions.append(window.mine_filter)
    tools.append(actions)
    top.append(tools)
    header.append(top)
    details = Gtk.Box(spacing=8, halign=Gtk.Align.END, valign=Gtk.Align.CENTER)
    details.add_css_class('board-details')
    window.board_count_label = label(count_text, 'dim-label', xalign=0)
    details.append(window.board_count_label)
    users = members(board)
    if users:
        details.append(label('·', 'dim-label'))
    participants = (Adw.WrapBox(child_spacing=4, line_spacing=4, align=1,
                               natural_line_length=min(240, max(20, len(users)*24-4)), valign=Gtk.Align.CENTER)
                    if hasattr(Adw, 'WrapBox') else Gtk.Box(spacing=4, valign=Gtk.Align.CENTER))
    participants.add_css_class('board-participants')
    owner = person(board.get('owner'))
    for user in users:
        tooltip = user['displayname']+'\n'+user['uid']
        if user['uid'] == owner['uid']:
            tooltip = _("Responsable del tauler: {name}").format(name=user['displayname'])+'\n'+user['uid']
        photo = avatar(window, user, 20)
        ui.text(photo, 'tooltip_text', tooltip)
        ui.accessible(photo, [Gtk.AccessibleProperty.LABEL], [tooltip])
        participants.append(photo)
    details.append(participants)
    tools.append(details)
    return header


class ProjectDialog(Adw.Dialog):
    def __init__(self, window, board):
        super().__init__(title=_("Edita el projecte"), content_width=560)
        ui.widget(self, title=_("Edita el projecte"))
        self.window, self.board = window, dict(board)
        self.metadata = dict(window.store.get("board_metadata", {}).get(str(board["id"]), {}))
        self.initial_metadata = dict(self.metadata)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(box)
        header = Adw.HeaderBar()
        save = ui.create(Gtk.Button, label=_("Desa"))
        save.add_css_class("suggested-action")
        save.connect("clicked", self.save)
        self.save_button = save
        header.pack_end(save)
        box.append(header)
        form = dialog_form(spacing=32)
        box.append(Gtk.ScrolledWindow(child=form, vexpand=True, propagate_natural_height=True,
                                      hscrollbar_policy=Gtk.PolicyType.NEVER))
        identity_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        identity = Gtk.Box(spacing=12)
        self.preview = Gtk.Box(valign=Gtk.Align.CENTER)
        self.refresh_preview()
        identity.append(self.preview)
        self.name = ui.create(Adw.EntryRow, title=_("Nom del projecte"))
        ui.text(self.name, 'text', board["title"])
        group = Adw.PreferencesGroup(hexpand=True)
        group.add(self.name)
        identity.append(group)
        identity_section.append(identity)
        actions = Gtk.Box(spacing=8)
        choose = text_icon_button("image-x-generic-symbolic", _("Tria una imatge…"))
        choose.connect("clicked", self.choose_image)
        actions.append(choose)
        actions.append(icon_button("edit-delete-symbolic", _("Treu la imatge o la icona"), self.remove_image))
        identity_section.append(actions)
        form.append(identity_section)
        icon_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        icon_section.append(label(_("Tria una icona d'Adwaita"), "heading", xalign=0))
        current = self.metadata.get("icon") if not self.metadata.get("image") else None
        self.icons = IconChooser(current, self.icon_changed)
        icon_section.append(self.icons)
        form.append(icon_section)
        description_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        description_heading = Gtk.Box(spacing=12)
        description_heading.append(label(_("Descripció"), "heading", xalign=0, hexpand=True))
        description_section.append(description_heading)
        self.description = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, accepts_tab=False,
                                        top_margin=8, bottom_margin=8, left_margin=10, right_margin=10)
        self.description.add_css_class("description-editor")
        self.initial_description = self.metadata.get("description", board.get("description") or "")
        ui.text(self.description.get_buffer(), 'text', self.initial_description)
        description_section.append(Gtk.ScrolledWindow(child=self.description, min_content_height=64, max_content_height=64,
                                        propagate_natural_height=True, vexpand=False,
                                        hscrollbar_policy=Gtk.PolicyType.NEVER))
        self.description_count = label("", "caption", xalign=1)
        ui.text(self.description_count, 'tooltip_text', _("Caràcters de la descripció"))
        description_heading.append(self.description_count)
        hint = label(_("El nom se sincronitza amb Deck. La descripció i la imatge es desen en aquest dispositiu."),
                     "dim-label", xalign=0, wrap=True)
        hint.add_css_class("caption")
        description_section.append(hint)
        form.append(description_section)
        self.name.connect("changed", self.changed)
        self.description.get_buffer().connect("changed", self.changed)
        self.connect("close-attempt", self.close_attempt)
        self.changed()

    def description_text(self):
        buffer = self.description.get_buffer()
        return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)

    def changed(self, *_unused):
        count = len(self.description_text())
        ui.text(self.description_count, 'text', f"{count} / {DESCRIPTION_LIMIT}")
        overflow = count > DESCRIPTION_LIMIT
        if overflow:
            self.description_count.add_css_class("error")
        else:
            self.description_count.remove_css_class("error")
        # Existing long descriptions remain intact until the user edits them.
        self.save_button.set_sensitive(not overflow or self.description_text() == self.initial_description)
        dirty = (self.name.get_text() != self.board["title"] or self.metadata != self.initial_metadata
                 or self.description_text() != self.initial_description)
        self.set_can_close(not dirty)

    def icon_changed(self, icon):
        self.metadata["icon"] = icon
        self.metadata.pop("image", None)
        self.metadata.pop("emoji", None)
        self.refresh_preview()
        self.changed()

    def refresh_preview(self):
        while self.preview.get_first_child():
            self.preview.remove(self.preview.get_first_child())
        image = project_image(self.window, self.metadata, 56)
        if image is not None:
            self.preview.append(image)

    def remove_image(self, *_unused):
        self.metadata.pop("image", None)
        self.metadata.pop("emoji", None)
        self.metadata["icon"] = ""
        self.icons.clear_selection()
        self.refresh_preview()
        self.changed()

    def choose_image(self, *_unused):
        dialog = ui.create(Gtk.FileDialog, title=_("Tria una imatge per al projecte"))
        filter = ui.create(Gtk.FileFilter, name=_("Imatges"))
        for mime in ["image/png", "image/jpeg", "image/webp", "image/gif", "image/svg+xml"]:
            filter.add_mime_type(mime)
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(filter)
        dialog.set_filters(filters)
        def selected(dialog, result):
            try:
                record = self.window.assets.import_file(dialog.open_finish(result), icon=True)
                self.metadata["image"] = record["path"]
                self.icons.clear_selection()
                self.refresh_preview()
                self.changed()
            except GLib.Error:
                pass
            except ValueError as error:
                alert = ui.create(Adw.AlertDialog, heading=_("No s'ha pogut afegir la imatge"), body=str(error))
                ui.response(alert, "close", _("D'acord"))
                alert.present(self.window)
        dialog.open(self.window, None, selected)

    def close_attempt(self, *_unused):
        prompt = ui.create(Adw.AlertDialog, heading=_("Vols descartar els canvis?"), body=_("El projecte encara no s'ha desat."))
        ui.response(prompt, "keep", _("Continua editant"))
        ui.response(prompt, "discard", _("Descarta els canvis"))
        prompt.set_response_appearance("discard", Adw.ResponseAppearance.DESTRUCTIVE)
        prompt.set_default_response("keep")
        prompt.connect("response", lambda _unused, response: self.force_close() if response == "discard" else None)
        prompt.present(self)

    def save(self, *_unused):
        if len(self.description_text()) > DESCRIPTION_LIMIT and self.description_text() != self.initial_description:
            self.description.grab_focus()
            return
        title = self.name.get_text().strip()
        if not title or len(title) > 100:
            self.name.add_css_class("error")
            self.name.grab_focus()
            return
        metadata = self.window.store.get("board_metadata", {})
        self.metadata["description"] = self.description_text().strip()
        metadata[str(self.board["id"])] = self.metadata
        self.window.store.put("board_metadata", metadata)
        if title != self.board["title"]:
            self.window.engine.enqueue("board_update", {"board_id": self.board["id"],
                                        "changes": {"title": title}, "base": {"title": self.board["title"]}})
        self.window.render()
        self.force_close()
