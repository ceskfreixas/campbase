# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Small native widgets shared by the board and dialogs."""
from . import localization as ui
from .i18n import _, ngettext
import re
from datetime import date
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk, Pango
from .dragging import CardDrag, ColumnDrop


def icon_button(icon, label, callback=None):
    button = ui.create(Gtk.Button, icon_name=icon, tooltip_text=label)
    ui.accessible(button, [Gtk.AccessibleProperty.LABEL], [label])
    if callback:
        button.connect("clicked", callback)
    return button


def label(text, css=None, **kwargs):
    widget = ui.create(Gtk.Label, label=text, **kwargs)
    if css:
        widget.add_css_class(css)
    return widget


def color_dot(color):
    dot = ui.create(Gtk.Label, label="●", valign=Gtk.Align.CENTER)
    rgba = Gdk.RGBA()
    if not rgba.parse("#" + color.lstrip("#")):
        rgba.parse("#77767b")
    attributes = Pango.AttrList()
    attributes.insert(Pango.attr_foreground_new(int(rgba.red * 65535), int(rgba.green * 65535), int(rgba.blue * 65535)))
    dot.set_attributes(attributes)
    return dot


def text_icon_button(icon, text, **kwargs):
    button = Gtk.Button(**kwargs)
    child = Gtk.Box(spacing=6)
    child.append(Gtk.Image(icon_name=icon))
    child.append(ui.create(Gtk.Label, label=text))
    button.set_child(child)
    return button


def clear(box):
    while box.get_first_child():
        box.remove(box.get_first_child())


def summary(text):
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text or "")
    text = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", text)
    return re.sub(r"[*_`#>~]+", "", text).strip()


def date_label(value):
    if not value:
        return ""
    try:
        from .due_dates import local_due
        parsed = local_due(value)
        return parsed.strftime('%x · %H:%M')
    except ValueError:
        return value[:10]


class Card(Gtk.Button):
    def __init__(self, card, window, min_width=252, draggable=True, inline_assignees=True):
        super().__init__(hexpand=True, valign=Gtk.Align.FILL)
        self.card = card
        self.window = window
        self.add_css_class("campbase-card")
        if card.get('archived'):
            self.add_css_class('card-archived')
        self.set_size_request(min_width, -1)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7, valign=Gtk.Align.CENTER)
        self.set_child(box)
        title = label(card.get("title", _("Sense títol")), "card-title", xalign=0, wrap=True,
                      wrap_mode=Pango.WrapMode.WORD_CHAR, lines=3, ellipsize=Pango.EllipsizeMode.END,
                      valign=Gtk.Align.CENTER, hexpand=True)
        heading = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER, halign=Gtk.Align.START)
        heading.set_hexpand(True)
        heading.append(title)
        if card.get('archived'):
            archived = ui.create(Gtk.Image, icon_name='folder-symbolic', pixel_size=14,
                                 valign=Gtk.Align.CENTER, tooltip_text=_("Targeta arxivada"))
            ui.accessible(archived, [Gtk.AccessibleProperty.LABEL], [_("Targeta arxivada")])
            heading.append(archived)
        if card.get("_pending"):
            status = _("Cal revisar el canvi") if card.get("_blocked") else _("Pendent de sincronitzar")
            indicator = ui.create(Gtk.Image, icon_name="dialog-warning-symbolic" if card.get("_blocked") else "document-open-recent-symbolic",
                                  tooltip_text=status, pixel_size=14, valign=Gtk.Align.CENTER)
            ui.accessible(indicator, [Gtk.AccessibleProperty.LABEL], [status])
            indicator.add_css_class("card-sync-warning" if card.get("_blocked") else "card-sync-pending")
            heading.append(indicator)
        count = card.get('_textCommentsCount', card.get('commentsCount') if window.demo else None)
        if isinstance(count, int) and count > 0:
            text = ngettext("{count} comentari", "{count} comentaris", count).format(count=count)
            # Caption ink sits above its line-box centre. This optical offset
            # aligns the small glyphs with the title, including wrapped titles.
            comments = ui.create(Gtk.Box, spacing=3, valign=Gtk.Align.CENTER, margin_top=4, tooltip_text=text)
            comments.add_css_class('card-comment-count')
            comments.add_css_class('dim-label')
            ui.accessible(comments, [Gtk.AccessibleProperty.LABEL], [text])
            # An odd-sized icon shares the caption digits' half-pixel ink centre.
            comments.append(Gtk.Image(icon_name='cat.cesk.Campbase-comments-symbolic', pixel_size=13,
                                      valign=Gtk.Align.CENTER))
            comments.append(label(str(count) if count < 100 else '99+', 'caption',
                                  valign=Gtk.Align.CENTER, yalign=.5))
            heading.append(comments)
        box.append(heading)
        metadata = (Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, column_spacing=6, row_spacing=4,
                                min_children_per_line=1, max_children_per_line=4, valign=Gtk.Align.CENTER)
                    if min_width == 0 else Gtk.Box(spacing=8, valign=Gtk.Align.CENTER))
        metadata.add_css_class("card-metadata")
        append = (lambda child: metadata.insert(child, -1)) if min_width == 0 else metadata.append
        for tag in (card.get("labels") or [])[:3]:
            badge = ui.create(Gtk.Box, spacing=4, tooltip_text=tag.get("title", ""))
            badge.add_css_class("tag")
            badge.append(color_dot(tag.get("color") or "77767b"))
            badge.append(label(tag.get("title", ""), ellipsize=Pango.EllipsizeMode.END, max_width_chars=14))
            append(badge)
        if card.get("duedate"):
            due = Gtk.Box(spacing=4, valign=Gtk.Align.CENTER)
            due.append(Gtk.Image(icon_name="x-office-calendar-symbolic", pixel_size=14, valign=Gtk.Align.CENTER))
            due.append(label(date_label(card["duedate"]), "caption", valign=Gtk.Align.CENTER))
            append(due)
        from .collaboration import assignment_users
        from .people import avatar
        users = assignment_users(card.get('assignedUsers'))
        self.assignee_avatars = None
        if users:
            avatars = Gtk.Box(spacing=4, valign=Gtk.Align.CENTER, halign=Gtk.Align.END)
            for user in users[:3]:
                avatars.append(avatar(window, user, 24))
            self.assignee_avatars = avatars
            if inline_assignees:
                heading.append(Gtk.Box(hexpand=True))
                heading.append(avatars)
        if metadata.get_first_child():
            box.append(metadata)
        self.connect("clicked", lambda *_unused: window.open_card(card))
        self.drag = CardDrag(self, card, window) if draggable and not card.get('archived') else None


PALETTE = {
    _("Vermell"): "#e01b24", _("Corall"): "#f66151", _("Taronja"): "#e98d26", _("Ambre"): "#c64600",
    _("Groc"): "#c7a600", _("Llima"): "#7a9c29", _("Verd"): "#33a56c", _("Verd fosc"): "#26734d",
    _("Turquesa"): "#2190a4", _("Blau cel"): "#62a0ea", _("Blau"): "#3584e4", _("Indi"): "#613583",
    _("Violeta"): "#9141ac", _("Malva"): "#c061cb", _("Rosa"): "#d56199", _("Gris"): "#77767b",
}


class Column(Gtk.Box):
    def __init__(self, stack, window, triage=False, flexible=False):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10, hexpand=True, valign=Gtk.Align.START)
        self.stack = stack
        self.window = window
        self.triage, self.flexible = triage, flexible
        self.archived_section = None
        self.add_css_class("board-column")
        self.add_css_class("triage" if triage else "workflow-column")
        if not triage and not flexible:
            self.set_size_request(274, -1)
        head = Gtk.Box(spacing=9)
        head.add_css_class("column-header")
        append_header = head.append
        color = window.column_color(stack)
        self.add_css_class("tint-" + color.lstrip("#").lower())
        dot = label("▎", "column-color")
        rgba = Gdk.RGBA()
        rgba.parse(color)
        attrs = Pango.AttrList()
        attrs.insert(Pango.attr_foreground_new(int(rgba.red * 65535), int(rgba.green * 65535), int(rgba.blue * 65535)))
        dot.set_attributes(attrs)
        append_header(dot)
        append_header(label(stack["title"], "heading", xalign=0, hexpand=True, width_chars=1, ellipsize=Pango.EllipsizeMode.END))
        cards = window.filtered_cards(stack)
        self.count = label(str(len(cards)), "count-badge")
        append_header(self.count)
        from .column_menu import column_menu
        menu_button = column_menu(window, stack)
        append_header(menu_button)
        self.append(head)
        from .people import author_text, creator
        if creator(window, 'stack', stack)['uid']:
            self.append(label(author_text(window, 'stack', stack), 'caption', xalign=0, wrap=True))
        if triage:
            cards_box = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                                    column_spacing=12, row_spacing=12, min_children_per_line=1,
                                    max_children_per_line=100, hexpand=True, valign=Gtk.Align.START)
        else:
            cards_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card_widgets = []
        from .active_cards import ActiveCard
        for card in [card for card in cards if not card.get('archived')]:
            child = ActiveCard(card, window, min_width=0 if flexible else 252)
            card_widgets.append(child)
            if triage:
                cards_box.insert(child, -1)
            else:
                cards_box.append(child)
        self.append(cards_box)
        add = text_icon_button("list-add-symbolic", _("Afegeix una targeta"), halign=Gtk.Align.START)
        add.add_css_class("flat")
        add.add_css_class("add-card")
        if flexible:
            add.get_child().get_last_child().set_ellipsize(Pango.EllipsizeMode.END)
            ui.text(add, 'tooltip_text', _("Afegeix una targeta"))
        add.connect("clicked", lambda *_unused: window.new_card(stack["id"]))
        self.append(add)
        self.drop = ColumnDrop(self, card_widgets, add, triage, cards_box)
        self.refresh_archives(update_menu=False)

    def refresh_archives(self, update_menu=True):
        cards = self.window.filtered_cards(self.stack)
        ui.text(self.count, 'text', str(len(cards)))
        if self.archived_section:
            self.remove(self.archived_section)
            self.archived_section = None
        if self.window.shows_archived(self.stack['id']):
            archived_cards = [card for card in cards if card.get('archived')]
            from .archived_cards import ArchivedCards
            self.archived_section = ArchivedCards(self.window, self.stack, archived_cards,
                                                   triage=self.triage, flexible=self.flexible, column=self)
            self.append(self.archived_section)
        if update_menu:
            from .column_menu import column_menu
            head = self.get_first_child()
            column_menu(self.window, self.stack, button=head.get_last_child())
