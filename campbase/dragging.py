# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Native card dragging with a stable source, viewport and insertion cues."""
from . import localization as ui
from .i18n import _, ngettext
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, GObject, Gtk


class DragSession:
    def __init__(self, window):
        self.window = window
        self.source = None
        self.source_slot = None
        self.source_column = None
        self.source_size = None
        self.target = None
        self.scroll_handlers = ()
        self.scroll_value = 0
        self.drop_committed = False

    def begin(self, source, card):
        self.window.scroll_position.cancel()
        adjustment = self.window.scroll.get_vadjustment()
        self.scroll_value = adjustment.get_value()
        self.scroll_handlers = tuple(adjustment.connect(signal, self.hold_scroll)
                                     for signal in ('value-changed', 'changed'))
        self.drop_committed = False
        self.source = source
        self.window.dragged_card = card
        source.add_css_class("drag-source")
        parent = source.get_parent()
        self.source_slot = parent if isinstance(parent, Gtk.FlowBoxChild) else source
        column = source.get_ancestor(Gtk.Box)
        while column and not (hasattr(column, 'drop') and column.drop.column is column):
            column = column.get_parent()
        if column:
            self.source_column = column
            self.source_size = column.get_size_request()
            column.set_size_request(self.source_size[0], round(column.compute_bounds(column)[1].size.height))
            drop = column.archived_section.drop if card.get('archived') and column.archived_section else column.drop
            ok, bounds = source.compute_bounds(drop.widget)
            self.source_slot.set_visible(False)
            if ok:
                self.show(drop, bounds.origin.x+bounds.size.width/2, bounds.origin.y+bounds.size.height/2)

    def show(self, target, x, y):
        if self.target is not target:
            prepare = getattr(target, 'prepare', None)
            if prepare:
                prepare(self.target)
            self.clear_target()
            self.target = target
        if not target.archived:
            target.column.add_css_class("drop-active")
        target.mark_position(x, y)

    def clear_target(self, target=None):
        if target is not None and self.target is not target:
            return
        previous = self.target
        self.target = None
        # Removing a placeholder can synchronously emit another leave signal.
        if previous:
            previous.clear_mark()
            previous.column.remove_css_class("drop-active")

    def hold_scroll(self, adjustment):
        limit = max(adjustment.get_lower(), adjustment.get_upper()-adjustment.get_page_size())
        value = max(adjustment.get_lower(), min(self.scroll_value, limit))
        if abs(adjustment.get_value()-value) > .01:
            adjustment.set_value(value)

    def finish(self):
        self.window.dragged_card = None
        if self.source_slot:
            self.source_slot.set_visible(True)
        self.source_slot = None
        self.clear_target()
        if self.source_column:
            self.source_column.set_size_request(*self.source_size)
        self.source_column = None
        self.source_size = None
        if self.source:
            self.source.remove_css_class("drag-source")
        self.source = None
        adjustment = self.window.scroll.get_vadjustment()
        for handler in self.scroll_handlers:
            adjustment.disconnect(handler)
        self.scroll_handlers = ()
        if self.window._render_after_drag:
            self.window._render_after_drag = False
            # Let GTK release the native drag grab before replacing its source.
            GLib.idle_add(self.render_after_drag)

    def render_after_drag(self):
        if not self.window.engine.closed:
            self.window.render()
        return GLib.SOURCE_REMOVE


class CardDrag:
    def __init__(self, widget, card, window, handle=None):
        self.widget, self.card, self.window = widget, card, window
        self.handle = handle or widget
        self.anchor = (12, 12)
        # Capture motion before GtkButton's click gesture claims the sequence.
        self.controller = Gtk.DragSource(actions=Gdk.DragAction.MOVE,
                                         propagation_phase=Gtk.PropagationPhase.CAPTURE)
        self.controller.connect("prepare", self.prepare)
        self.controller.connect("drag-begin", self.begin)
        self.controller.connect("drag-end", lambda *_unused: window.drag_session.finish())
        self.controller.connect("drag-cancel", self.cancel)
        self.handle.add_controller(self.controller)

    def prepare(self, _source, x, y):
        self.anchor = (x, y)
        if self.handle is not self.widget:
            ok, bounds = self.handle.compute_bounds(self.widget)
            if ok:
                self.anchor = (x+bounds.origin.x, y+bounds.origin.y)
        return Gdk.ContentProvider.new_for_value(f"campbase-card:{self.card['id']}")

    def begin(self, _source, drag):
        # Freeze the actual card before dimming its source, and keep the grab
        # position under the pointer instead of jumping to its top-left corner.
        image = Gtk.WidgetPaintable.new(self.widget).get_current_image()
        bounds = self.widget.compute_bounds(self.widget)[1]
        preview = Gtk.Box()
        preview.add_css_class("drag-preview")
        preview.append(Gtk.Picture(paintable=image, can_shrink=True,
                                   width_request=round(bounds.size.width),
                                   height_request=round(bounds.size.height)))
        Gtk.DragIcon.get_for_drag(drag).set_child(preview)
        drag.set_hotspot(round(self.anchor[0]-bounds.origin.x)+6, round(self.anchor[1]-bounds.origin.y)+6)
        self.window.drag_session.begin(self.widget, self.card)

    def cancel(self, *_unused):
        self.window.drag_session.finish()
        return False  # Keep GTK's native return animation for a cancelled drag.


class ColumnDrop:
    def __init__(self, column, widgets, add_button, triage, cards_box, *, widget=None, archived=False):
        self.column, self.window = column, column.window
        self.widget, self.archived = widget or column, archived
        self.widgets, self.add_button, self.triage = widgets, add_button, triage
        self.marked = None
        self.before = None
        self.edge = None
        self.cards_box = cards_box
        self.placeholder = None
        # One native target owns the whole column. Archive insertion is routed
        # from it; nested targets can be invalidated by their own moving preview.
        if not archived:
            target = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)
            target.connect("accept", lambda *_unused: self.accepts())
            target.connect("enter", self.motion)
            target.connect("motion", self.motion)
            target.connect("leave", self.leave)
            target.connect("drop", self.drop)
            self.widget.add_controller(target)

    def leave(self, *_unused):
        target = self.window.drag_session.target
        if target and target.column is self.column:
            self.window.drag_session.clear_target(target)

    def accepts(self):
        board = next((board for board in self.window.snapshot.get('boards', []) if board['id'] == self.window.board_id), {})
        editable = self.window.demo or board.get('permissions', {}).get('PERMISSION_EDIT', True)
        return bool(editable and self.window.dragged_card and
                    (not self.archived or self.window.shows_archived(self.column.stack['id'])))

    def positions(self):
        result = []
        dragged = (self.window.dragged_card or {}).get("id")
        for widget in self.widgets:
            if widget.card["id"] == dragged:
                continue
            ok, bounds = widget.compute_bounds(self.widget)
            if ok:
                result.append((widget, bounds))
        return result

    def position(self, x, y):
        if self.placeholder and self.placeholder.get_parent():
            ok, bounds = self.placeholder.compute_bounds(self.widget)
            if ok and bounds.origin.x <= x <= bounds.origin.x+bounds.size.width and bounds.origin.y <= y <= bounds.origin.y+bounds.size.height:
                return self.before, self.marked, self.edge
        cards = self.positions()
        if not cards:
            return None, None, None
        if not self.triage:
            for widget, bounds in cards:
                if y < bounds.origin.y+bounds.size.height/2:
                    return widget.card["id"], widget, "top"
            return None, cards[-1][0], "bottom"
        # FlowBox reading order may wrap onto several rows. Choose the nearest
        # row first, then insert before/after a card using its horizontal midpoint.
        rows = []
        for widget, bounds in cards:
            if not rows or abs(rows[-1][0][1].origin.y-bounds.origin.y) > 2:
                rows.append([])
            rows[-1].append((widget, bounds))
        row_index = min(range(len(rows)), key=lambda i: abs(y-rows[i][0][1].origin.y-rows[i][0][1].size.height/2))
        if y > cards[-1][1].origin.y+cards[-1][1].size.height:
            return None, cards[-1][0], "right"
        for widget, bounds in rows[row_index]:
            if x < bounds.origin.x+bounds.size.width/2:
                return widget.card["id"], widget, "left"
        following = rows[row_index+1][0][0].card["id"] if row_index+1 < len(rows) else None
        return following, rows[row_index][-1][0], "right"

    def remove_placeholder(self):
        if self.placeholder and self.placeholder.get_parent():
            parent = self.placeholder.get_parent()
            self.cards_box.remove(parent if self.triage else self.placeholder)

    def clear_mark(self):
        self.remove_placeholder()
        self.placeholder = None
        self.marked = None
        self.before = None
        self.edge = None

    def mark_position(self, x, y):
        before, marked, edge = self.position(x, y)
        if self.placeholder and self.placeholder.get_parent() and before == self.before:
            return
        first = self.placeholder is None
        self.remove_placeholder()
        self.before, self.marked, self.edge = before, marked, edge
        if first:
            source = self.window.drag_session.source
            height = max(54, round(source.compute_bounds(source)[1].size.height) if source else 54)
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5,
                              valign=Gtk.Align.FILL, halign=Gtk.Align.FILL)
            content.add_css_class("drop-placeholder")
            title = ui.create(Gtk.Label, label=_("Deixa anar aquí"), vexpand=True, valign=Gtk.Align.CENTER,
                              wrap=True, justify=Gtk.Justification.CENTER)
            title.add_css_class("drop-placeholder-label")
            content.append(title)
            content.set_size_request(252 if self.triage else -1, height)
            self.placeholder = Gtk.Revealer(child=content, can_target=False,
                                            transition_duration=130,
                                            transition_type=Gtk.RevealerTransitionType.NONE if self.column.stack["id"] == (self.window.dragged_card or {}).get("stackId") else Gtk.RevealerTransitionType.CROSSFADE if self.triage else Gtk.RevealerTransitionType.SLIDE_DOWN)
        index = next((i for i, widget in enumerate(self.widgets) if widget.card["id"] == before), len(self.widgets))
        if self.triage:
            self.cards_box.insert(self.placeholder, index)
        else:
            previous = self.widgets[index-1] if index else None
            self.cards_box.insert_child_after(self.placeholder, previous)
        self.placeholder.set_reveal_child(True)

    def motion(self, _target, x, y):
        if not self.accepts():
            return Gdk.DragAction(0)
        archive = self.archive_target(x, y)
        if archive:
            return archive.motion(_target, *archive.coordinates(self.column, x, y))
        self.window.drag_session.show(self, x, y)
        return Gdk.DragAction.MOVE

    def archive_target(self, x, y):
        if self.archived:
            return None
        section = self.column.archived_section
        if section:
            ok, bounds = section.compute_bounds(self.column)
            if ok and bounds.origin.x <= x <= bounds.origin.x+bounds.size.width and bounds.origin.y <= y <= bounds.origin.y+bounds.size.height:
                return section.drop
        return None

    def drop(self, _target, value, x, y):
        archive = self.archive_target(x, y)
        if archive:
            return archive.drop(_target, value, *archive.coordinates(self.column, x, y))
        active = self.window.dragged_card
        if not self.accepts() or self.window.drag_session.drop_committed or value != f"campbase-card:{active['id']}":
            return False
        card = self.window.find_card(active["id"])
        if not card:
            return False
        before, _unused, _unused = self.position(x, y)
        self.window.drag_session.drop_committed = True
        self.window.drag_session.clear_target()
        archived = self.archived if self.archived or card.get('archived') else None
        self.window.move_card(card, self.column.stack["id"], before=before, archived=archived)
        self.window._render_after_drag = True
        return True
