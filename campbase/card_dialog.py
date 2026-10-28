# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Card content, rich descriptions and comments."""
from . import localization as ui
from .i18n import _, ngettext
from datetime import date
from gi.repository import Adw, Gtk, Pango
from .alerts import message
from .rich_text import RichTextEditor
from .comments import CommentsPanel
from .date_picker import DatePicker
from .due_dates import same_due
from .labels import LabelSelector
from .widgets import icon_button, label, text_icon_button
from .dialog_widgets import dialog_form, scroll_to_widget
from .people import AssigneeSelector, card_author_text, current_person, creator, avatar
from .collaboration import assignment_ids, person

class CardDialog(Adw.Dialog):
    def __init__(self, window, stack_id, card=None, target=None):
        super().__init__(title=_("Targeta") if card else _("Targeta nova"), content_width=680, follows_content_size=True)
        ui.widget(self, title=_("Targeta") if card else _("Targeta nova"))
        self.window, self.card, self.stack_id = window, card, stack_id
        self.target = target or {}
        self.sections = {}
        self._focused_target = None
        self._initializing = True
        self.stacks = window.stacks()
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.content_box = outer
        self.set_child(Adw.Clamp(maximum_size=680, tightening_threshold=680, child=outer))
        header = Adw.HeaderBar()
        save = ui.create(Gtk.Button, label=_("Desa") if card else _("Crea la targeta"))
        save.add_css_class("suggested-action")
        save.connect("clicked", lambda *_unused: self.save())
        header.pack_end(save)
        outer.append(header)
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True,
                                      propagate_natural_height=True, max_content_height=680,
                                      propagate_natural_width=True, max_content_width=680)
        form = dialog_form()
        self.scroller, self.form = scroller, form
        scroller.set_child(form)
        outer.append(scroller)
        identity = Gtk.Box(spacing=12)
        title_field = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, hexpand=True)
        title_field.append(label(_("Títol"), "heading", xalign=0))
        self.title_entry = ui.create(Gtk.Entry, text=card.get("title", "") if card else "", placeholder_text=_("Què vols treballar?"))
        self.title_entry.set_width_chars(6)
        self.title_entry.set_hexpand(True)
        self.title_entry.set_max_length(255)
        title_field.append(self.title_entry)
        identity.append(title_field)
        column_field = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        column_field.append(label(_("Columna"), "heading", xalign=0))
        self.column = Gtk.DropDown.new_from_strings([s["title"] for s in self.stacks])
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", lambda _factory, item: item.set_child(Gtk.Label(
            xalign=0, ellipsize=Pango.EllipsizeMode.END, max_width_chars=20, width_chars=16)))
        def bind_column(_factory, item):
            title = item.get_item().get_string()
            ui.text(item.get_child(), 'text', title)
            ui.text(item.get_child(), 'tooltip_text', title)
        factory.connect("bind", bind_column)
        self.column.set_factory(factory)
        self.column.set_selected(next((i for i, s in enumerate(self.stacks) if s["id"] == stack_id), 0))
        column_field.append(self.column)
        identity.append(column_field)
        self.sections.update(details=identity, column=column_field)
        form.append(identity)
        board = next((b for b in window.snapshot['boards'] if b['id'] == window.board_id), {})
        self.assignees = AssigneeSelector(window, board, card)
        self.sections['assignees'] = self.assignees
        identity.append(self.assignees)
        self.labels = LabelSelector(window, card)
        self.sections['labels'] = self.labels
        form.append(self.labels)
        description_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        description_section.append(label(_("Descripció"), "heading", xalign=0))
        self.description = RichTextEditor(window, (card.get("description") or "") if card else "")
        description_section.append(self.description)
        form.append(description_section)
        self.sections['description'] = description_section
        self.due = DatePicker((card.get("duedate") or "") if card else "")
        group = Adw.PreferencesGroup()
        group.add(self.due)
        group.add(self.due.time_row)
        form.append(group)
        self.sections['due'] = group
        if card and card["id"] > 0:
            section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            section.append(label(_("Comentaris"), "heading", xalign=0))
            self.comments = CommentsPanel(window, card, inline=True, target=self.target if self.target.get('section') == 'comments' else None)
            self.comments.on_loaded = self.focus_target
            self.sections['comments'] = section
            section.append(self.comments)
            form.append(section)
            if window.demo:
                self.comments.display([], None)
            else:
                self.comments.show()
        if card:
            buttons = Gtk.Box(spacing=8)
            archive = ui.create(Gtk.Button, label=_("Restaura la targeta") if card.get("archived") else _("Arxiva la targeta"))
            archive.connect("clicked", self.archive)
            buttons.append(archive)
            if card.get('archived') and card['id'] > 0:
                delete = ui.create(Gtk.Button, label=_("Esborra la targeta"))
                delete.add_css_class('destructive-action')
                delete.set_sensitive(window.demo or board.get('permissions', {}).get('PERMISSION_EDIT', True))
                stack = next(stack for stack in self.stacks if stack['id'] == stack_id)
                delete.connect('clicked', lambda *_unused: window.delete_archived_cards(
                    stack, [card], parent=self, after=self.force_close))
                buttons.append(delete)
            if card["id"] > 0:
                open_deck = text_icon_button("adw-external-link-symbolic", _("Obre a Deck"))
                open_deck.add_css_class("flat")
                open_deck.connect("clicked", lambda *_unused: window.open_deck(card))
                buttons.append(open_deck)
            footer = Gtk.Box(spacing=12)
            footer.append(buttons)
            footer.append(Gtk.Box(hexpand=True))
            user = creator(window, 'card', card)
            if not user['uid']:
                user = person(card.get('owner'))
            if user['uid']:
                self.author_avatar = avatar(window, user, 28)
                self.author_avatar.set_valign(Gtk.Align.CENTER)
                ui.text(self.author_avatar, 'tooltip_text', card_author_text(window, card))
                footer.append(self.author_avatar)
            form.append(footer)
        editable = window.demo or board.get('permissions', {}).get('PERMISSION_EDIT', True)
        save.set_sensitive(editable)
        for control in (self.title_entry, self.column, self.assignees, self.labels, self.description, self.due, self.due.time_row):
            control.set_sensitive(editable)
        if card:
            archive.set_sensitive(editable)
        self.connect("close-attempt", self.close_attempt)
        self._initializing = False
        self.title_entry.connect("changed", self.changed)
        self.description.connect("changed", self.changed)
        self.column.connect("notify::selected", self.changed)
        self.due.connect("changed", self.changed)
        self.labels.connect("changed", self.changed)
        self.assignees.connect("changed", self.changed)
        self.connect('map', lambda *_unused: self.focus_target())

    def focus_target(self):
        section = self.target.get('section')
        widget = self.sections.get(section)
        if section == 'comments' and self.comments.target_widget is not None:
            widget = self.comments.target_widget
        if widget is not None:
            if self._focused_target is not None and self._focused_target is not widget:
                self._focused_target.remove_css_class('notification-target')
            self._focused_target = widget
            widget.add_css_class('notification-target')
            scroll_to_widget(self.scroller, self.form, widget)

    def contents(self):
        return {"title": self.title_entry.get_text().strip(),
                "description": self.description.get_markdown(),
                "duedate": self.due.get_due(), "labels": self.labels.selected_labels(),
                "assignedUsers": self.assignees.selected_users()}

    def changed(self, *_unused):
        current = self.contents()
        original = self.card or {}
        dirty = current["title"] != original.get("title", "") or current["description"] != (original.get("description") or "")
        dirty |= not same_due(current["duedate"], original.get("duedate"))
        dirty |= {item["id"] for item in current["labels"]} != {item["id"] for item in original.get("labels") or []}
        dirty |= assignment_ids(current["assignedUsers"]) != assignment_ids(original.get("assignedUsers"))
        dirty |= self.stacks[self.column.get_selected()]["id"] != self.stack_id
        self.set_can_close(not dirty)

    def close_attempt(self, *_unused):
        prompt = ui.create(Adw.AlertDialog, heading=_("Vols descartar els canvis?"), body=_("La targeta encara no s'ha desat."))
        ui.response(prompt, "keep", _("Continua editant"))
        ui.response(prompt, "discard", _("Descarta els canvis"))
        prompt.set_response_appearance("discard", Adw.ResponseAppearance.DESTRUCTIVE)
        prompt.set_default_response("keep")
        prompt.connect("response", lambda _unused, response: self.force_close() if response == "discard" else None)
        prompt.present(self)

    def save(self, close=True):
        values = self.contents()
        if not values["title"]:
            self.title_entry.add_css_class("error")
            self.title_entry.grab_focus()
            return False
        due = values["duedate"]
        if due:
            try:
                date.fromisoformat(due[:10])
            except ValueError:
                message(self, _("Revisa la data"), _("Tria una data vàlida al calendari."))
                return False
        stack_id = self.stacks[self.column.get_selected()]["id"]
        if self.card:
            changes = {k: v for k, v in values.items() if k not in {"duedate", "labels", "assignedUsers"} and v != (self.card.get(k) or "")}
            if {item["id"] for item in values["labels"]} != {item["id"] for item in self.card.get("labels") or []}:
                changes["labels"] = values["labels"]
            if assignment_ids(values['assignedUsers']) != assignment_ids(self.card.get('assignedUsers')):
                changes['assignedUsers'] = values['assignedUsers']
            if not same_due(due, self.card.get("duedate")):
                changes["duedate"] = due
            if changes:
                self.window.update_card(self.card, changes, images=self.description.local_images())
            if stack_id != self.stack_id:
                self.window.move_card(self.card, stack_id)
        else:
            self.window.engine.enqueue("create", {"board_id": self.window.board_id, "stack_id": stack_id,
                                                   "title": values["title"], "description": values["description"],
                                                   "images": self.description.local_images(),
                                                   "labels": values["labels"], "assignedUsers": values["assignedUsers"],
                                                   "owner": current_person(self.window),
                                                   "duedate": due,
                                                   "order": len(self.window.cards_in_stack(stack_id))})
        if close:
            self.force_close()
        return True

    def archive(self, *_unused):
        if self.save(close=False):
            # Save may have just queued a move; archive in its destination.
            card = dict(self.card, stackId=self.stacks[self.column.get_selected()]['id'])
            self.window.update_card(card, {"archived": not card.get("archived", False)}, kind="archive")
            self.force_close()
