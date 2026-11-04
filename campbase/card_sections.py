# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared column sections: heading, folding, visibility, cards and drop feedback."""
from gi.repository import Gio, GLib, Gtk
from . import localization as ui
from .i18n import _
from .widgets import label, icon_button
from .workflow_state import presentation, options, save_options


class CardSection(Gtk.Box):
    def __init__(self, window, stack, cards, *, kind, title, icon, empty, triage, hide, hide_title, column=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0, margin_top=8)
        self.window, self.stack, self.kind = window, stack, kind
        self.add_css_class('card-section');self.add_css_class(kind+'-section')
        self.key=f"{stack['id']}:{kind}"
        self.collapsed=bool(presentation(window,window.board_id).get('collapsed_sections',{}).get(self.key))
        self.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        self.heading=Gtk.Box(spacing=8,margin_top=10)
        self.fold=icon_button('pan-end-symbolic' if self.collapsed else 'pan-down-symbolic',
            _("Desplega la secció") if self.collapsed else _("Plega la secció"),lambda *_:self.toggle())
        self.fold.add_css_class('flat');self.heading.append(self.fold)
        self.heading.append(Gtk.Image(icon_name=icon,pixel_size=14))
        self.heading.append(label(title,'caption',xalign=0,hexpand=True))
        self.heading.append(label(str(len(cards)),'caption',xalign=1))
        self.menu=ui.create(Gtk.MenuButton,icon_name='view-more-symbolic',tooltip_text=_("Opcions de la secció"))
        self.menu.add_css_class('flat')
        group=Gio.SimpleActionGroup()
        action=Gio.SimpleAction.new('hide',None);action.connect('activate',lambda *_:self.hide_after_close(hide))
        group.add_action(action);self.menu.insert_action_group('section',group)
        model=Gio.Menu();ui.menu_append(model,hide_title,'section.hide')
        self.menu.set_menu_model(model);self.heading.append(self.menu)
        self.append(self.heading)
        from .section_reveal import SectionReveal
        self.body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10)
        if triage:
            from .triage_grid import TriageGrid
            self.cards_box=TriageGrid()
        else:
            self.cards_box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10)
        self.body.append(self.cards_box)
        if not cards:
            self.body.append(label(empty,'dim-label',xalign=0,wrap=True,margin_bottom=8))
        self.body_revealer=SectionReveal(self.body,revealed=not self.collapsed,gap=10)
        self.append(self.body_revealer)
        self.revealer=SectionReveal(self,revealed=False)
        self.cards=[]
        self.widgets=self.cards
        self.triage=triage

    def hide_after_close(self, callback):
        popover=self.menu.get_popover()
        def run():
            if not self.window.engine.closed:
                callback()
            return GLib.SOURCE_REMOVE
        if not popover.get_mapped():
            GLib.idle_add(run)
            return
        def closed(*_unused):
            popover.disconnect(handler)
            GLib.idle_add(run)
        handler=popover.connect('closed',closed)
        popover.popdown()

    def add_card(self, tile):
        self.cards.append(tile)
        self.cards_box.insert(tile,-1) if self.triage else self.cards_box.append(tile)

    def add_action(self, button):
        self.heading.insert_child_after(button,self.menu.get_prev_sibling())

    def toggle(self):
        self.collapsed=not self.collapsed
        values=dict(options(self.window.store,self.window.board_id).get('collapsed_sections',{}))
        values[self.key]=self.collapsed
        save_options(self.window.store,self.window.board_id,collapsed_sections=values)
        self.body_revealer.reveal(not self.collapsed)
        self.fold.set_icon_name('pan-end-symbolic' if self.collapsed else 'pan-down-symbolic')
        ui.text(self.fold,'tooltip_text',_("Desplega la secció") if self.collapsed else _("Plega la secció"))
