# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""A shared right-hand slot for tasks, comments, assignees and contextual actions."""
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Graphene, Gsk, Gtk, Pango
from .widgets import Card


class CardTileLayout(Gtk.OverlayLayout):
    def do_allocate(self, tile, width, height, baseline):
        Gtk.OverlayLayout.do_allocate(self, tile, width, height, baseline)
        heading = tile.card_widget.get_child().get_first_child()
        ok, _ = heading.compute_bounds(tile)
        if not ok:
            return
        title = heading.get_first_child()
        _, title_bounds = title.compute_bounds(tile)
        _, offset = title.get_layout_offsets()
        ink, _ = title.get_layout().get_extents()
        center = title_bounds.origin.y+offset+(ink.y+ink.height/2)/Pango.SCALE
        for child in (tile.indicators, tile.controls):
            if child is None:
                continue
            anchor = child.get_height()/2
            badges = [badge for badge in (tile.card_widget.task_badge, tile.card_widget.comment_badge) if badge]
            if child is tile.indicators and badges:
                centers = []
                for badge in badges:
                    number = badge.get_last_child()
                    _, text_bounds = number.compute_bounds(child)
                    _, text_offset = number.get_layout_offsets()
                    text_ink, _ = number.get_layout().get_extents()
                    centers.append(text_bounds.origin.y+text_offset+(text_ink.y+text_ink.height/2)/Pango.SCALE)
                anchor = sum(centers)/len(centers)
            _, bounds = child.compute_bounds(tile)
            start, end = child.get_margin_start(), child.get_margin_end()
            top, bottom = child.get_margin_top(), child.get_margin_bottom()
            position = Graphene.Point().init(bounds.origin.x-start, max(0, center-anchor)-top)
            child.allocate(child.get_width()+start+end, child.get_height()+top+bottom, -1,
                           Gsk.Transform.new().translate(position))


class CardTile(Gtk.Overlay):
    def __init__(self, card, window, min_width=252, *, measuring=False):
        super().__init__(hexpand=True, valign=Gtk.Align.FILL)
        self.card = card
        self.card_widget = Card(card, window, min_width=min_width, draggable=False, inline_assignees=False, measuring=measuring)
        self.set_child(self.card_widget)
        self.controls = None
        self.assignee_avatars = self.card_widget.assignee_avatars
        self.set_layout_manager(CardTileLayout())
        self.indicators = None
        indicators = [widget for widget in (self.card_widget.task_badge, self.card_widget.comment_badge, self.assignee_avatars) if widget]
        if indicators:
            self.indicators = Gtk.Box(spacing=8, halign=Gtk.Align.END, valign=Gtk.Align.START, margin_end=14)
            self.indicators.add_css_class('card-indicators')
            for widget in indicators:
                self.indicators.append(widget)
            self.add_overlay(self.indicators)
        # A reply-filtered comment total arrives asynchronously. Reserve its
        # bounded caption width now rather than moving the title when it loads.
        comment=self.card_widget.comment_badge
        total=card.get('commentsCount')
        if isinstance(total,int) and total>0:
            from .card_badges import comment_badge
            comment=comment_badge(total)
        reserved=[widget for widget in (self.card_widget.task_badge,comment,self.assignee_avatars) if widget]
        width=sum(widget.measure(Gtk.Orientation.HORIZONTAL,-1)[1] for widget in reserved)
        self.card_widget.get_child().set_margin_end(width+8*len(reserved))

    def add_actions(self, *buttons):
        self.add_css_class('has-card-controls')
        self.card_widget.get_child().set_margin_end(max(80, self.card_widget.get_child().get_margin_end()))
        actions = Gtk.Box(spacing=4, halign=Gtk.Align.END, valign=Gtk.Align.START, margin_end=8)
        self.controls = actions
        actions.add_css_class('hover-action')
        actions.add_css_class('card-controls')
        for button in buttons:
            actions.append(button)
        # Mouse/programmatic focus after a refresh is not a request to hide
        # the assignee. Keep the controls available for actual keyboard focus.
        for button in (self.card_widget, *buttons):
            button.connect('state-flags-changed', self.focus_changed)
        self.add_overlay(actions)

    def focus_changed(self, *_unused):
        buttons = [self.card_widget]
        child = self.controls.get_first_child()
        while child:
            buttons.append(child)
            child = child.get_next_sibling()
        if any(button.has_visible_focus() for button in buttons):
            self.add_css_class('keyboard-actions')
        else:
            self.remove_css_class('keyboard-actions')
