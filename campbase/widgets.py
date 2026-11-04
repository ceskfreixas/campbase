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
from .section_reveal import SectionBox, SectionReveal


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
    def __init__(self, card, window, min_width=252, draggable=True, inline_assignees=True, measuring=False):
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
        pending=bool(card.get('_pending'))
        status = _("Cal revisar el canvi") if card.get("_blocked") else _("Pendent de sincronitzar")
        indicator = ui.create(Gtk.Image, icon_name="dialog-warning-symbolic" if card.get("_blocked") else "document-open-recent-symbolic",
                              tooltip_text=status if pending else None, pixel_size=14, valign=Gtk.Align.CENTER,
                              opacity=1 if pending else 0, can_target=pending)
        if pending:
            ui.accessible(indicator,[Gtk.AccessibleProperty.LABEL],[status])
            indicator.add_css_class("card-sync-warning" if card.get("_blocked") else "card-sync-pending")
        else:
            indicator.set_accessible_role(Gtk.AccessibleRole.PRESENTATION)
        # Keep this small slot when sync finishes, so titles do not rewrap.
        heading.append(indicator)
        count = card.get('_textCommentsCount', card.get('commentsCount') if window.demo else None)
        self.comment_badge = None
        if isinstance(count, int) and count > 0:
            from .card_badges import comment_badge
            self.comment_badge = comment_badge(count)
        from .card_badges import task_badge
        self.task_badge = task_badge(card.get('description'))
        box.append(heading)
        metadata = (Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, column_spacing=6, row_spacing=4,
                                min_children_per_line=1, max_children_per_line=4, valign=Gtk.Align.CENTER)
                    if min_width == 0 else Gtk.Box(spacing=8, valign=Gtk.Align.CENTER))
        metadata.add_css_class("card-metadata")
        append = (lambda child: metadata.insert(child, -1)) if min_width == 0 else metadata.append
        from .workflow_state import visible_labels
        for tag in visible_labels(window,card.get("labels"))[:3]:
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
                avatars.append(Gtk.Box(width_request=24,height_request=24) if measuring else avatar(window,user,24))
            self.assignee_avatars = avatars
        if inline_assignees and (self.task_badge or self.comment_badge or self.assignee_avatars):
            heading.append(Gtk.Box(hexpand=True))
            for badge in (self.task_badge, self.comment_badge):
                if badge:
                    heading.append(badge)
            if self.assignee_avatars:
                heading.append(self.assignee_avatars)
        if metadata.get_first_child():
            box.append(metadata)
        if not measuring:self.connect("clicked",lambda *_unused:window.open_card(card))
        self.drag = CardDrag(self,card,window) if draggable and not measuring and not card.get('archived') else None


PALETTE = {
    _("Vermell"): "#e01b24", _("Corall"): "#f66151", _("Taronja"): "#e98d26", _("Ambre"): "#c64600",
    _("Groc"): "#c7a600", _("Llima"): "#7a9c29", _("Verd"): "#33a56c", _("Verd fosc"): "#26734d",
    _("Turquesa"): "#2190a4", _("Blau cel"): "#62a0ea", _("Blau"): "#3584e4", _("Indi"): "#613583",
    _("Violeta"): "#9141ac", _("Malva"): "#c061cb", _("Rosa"): "#d56199", _("Gris"): "#77767b",
}


class Column(SectionBox):
    def __init__(self, stack, window, triage=False, flexible=False, not_now=False):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10, hexpand=True, valign=Gtk.Align.START)
        self.stack = stack
        self.window = window
        self.triage, self.flexible = triage, flexible
        self.archived_section = None
        self.hold_section = None
        self.not_now = not_now
        from .workflow_state import hold_enabled, is_held
        paused = hold_enabled(window,stack['id'])
        self.add_css_class("board-column")
        self.add_css_class("triage" if triage else "workflow-column")
        if not triage and not flexible:
            self.set_size_request(274, -1)
        head = Gtk.Box(spacing=9)
        head.add_css_class("column-header")
        append_header = head.append
        if not_now:
            from .workflow_state import presentation
            from .workflow_sections import fold_column
            self.add_css_class('not-now-column')
            self.expanded = bool(window.query or presentation(window,window.board_id).get('not_now_expanded'))
            self.fold_button = icon_button('pan-down-symbolic' if self.expanded else 'pan-end-symbolic',
                _("Plega «Ara no»") if self.expanded else _("Desplega «Ara no»"),
                lambda *_: fold_column(self,not self.expanded))
            self.fold_button.add_css_class('flat')
            self.fold_button.add_css_class('not-now-toggle')
            self.fold_button.set_focus_on_click(False)
            append_header(self.fold_button)
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
        self.body=self
        if not_now:
            from .deferred_viewport import DeferredViewport
            self.body=SectionBox(orientation=Gtk.Orientation.VERTICAL,spacing=10)
            viewport=DeferredViewport(window,self.body)
            self.not_now_scroll=viewport.scroll
            self.not_now_scrollbar=viewport.scrollbar
            self.append(viewport)
        from .people import author_text, creator
        if not not_now and creator(window, 'stack', stack)['uid']:
            self.append(label(author_text(window, 'stack', stack), 'caption', xalign=0, wrap=True))
        if triage:
            from .triage_grid import TriageGrid
            cards_box = TriageGrid()
        else:
            cards_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card_widgets = []
        from .active_cards import ActiveCard
        for card in [card for card in cards if not card.get('archived') and not (paused and is_held(window,card))]:
            child = ActiveCard(card, window, min_width=0 if self.flexible else 252)
            card_widgets.append(child)
            if triage:
                cards_box.insert(child, -1)
            else:
                cards_box.append(child)
        self.active_revealer=SectionReveal(cards_box)
        self.body.append(self.active_revealer)
        add = text_icon_button("list-add-symbolic", _("Afegeix una targeta"), halign=Gtk.Align.START)
        add.add_css_class("flat")
        add.add_css_class("add-card")
        if flexible:
            add.get_child().get_last_child().set_ellipsize(Pango.EllipsizeMode.END)
            ui.text(add, 'tooltip_text', _("Afegeix una targeta"))
        board = next((item for item in window.snapshot['boards'] if item['id']==window.board_id),{})
        add.set_sensitive(window.demo or board.get('permissions',{}).get('PERMISSION_EDIT',False))
        add.connect("clicked", lambda *_unused: window.new_card(stack["id"]))
        self.body.append(add)
        self.drop = ColumnDrop(self, card_widgets, add, triage, cards_box, held=False if paused else None)
        if paused:
            from .workflow_sections import HoldSection
            self.hold_section = HoldSection(self,[card for card in cards if not card.get('archived') and is_held(window,card)])
            self.body.append(self.hold_section.revealer)
            self.hold_section.revealer.reveal(True,animate=False)
        if not_now:
            from .triage_layout import install_rail
            install_rail(self)
        self.refresh_archives(update_menu=False)

    def refresh_archives(self, update_menu=True):
        from .column_sections import refresh_archives
        refresh_archives(self,update_menu=update_menu)
