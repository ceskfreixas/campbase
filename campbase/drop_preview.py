# SPDX-License-Identifier: GPL-3.0-or-later
"""Size insertion cues with the destination card's real layout, without loading avatars."""
from gi.repository import Gtk
from . import localization as ui
from .i18n import _


def insertion_cue(drop, card):
    from .card_tiles import CardTile
    from .workflow_state import held_labels
    preview=dict(card,archived=drop.archived)
    if drop.held is not None:
        preview['labels']=held_labels(drop.window,preview,drop.held)
    tile=CardTile(preview,drop.window,min_width=0 if drop.column.flexible else 252,measuring=True)
    tile.set_opacity(0)
    tile.set_accessible_role(Gtk.AccessibleRole.PRESENTATION)
    tile.update_state([Gtk.AccessibleState.HIDDEN],[True])
    def passive(widget):
        widget.set_can_target(False)
        widget.set_focusable(False)
        child=widget.get_first_child()
        while child:
            passive(child);child=child.get_next_sibling()
    passive(tile)
    content=tile.card_widget.get_child()
    content.set_margin_end(max(80,content.get_margin_end()))
    marker=Gtk.Box(can_target=False,hexpand=True,vexpand=True)
    marker.add_css_class('drop-placeholder')
    title=ui.create(Gtk.Label,label=_("Deixa anar aquí"),can_target=False,hexpand=True,vexpand=True,
                    wrap=True,justify=Gtk.Justification.CENTER)
    title.add_css_class('drop-placeholder-label');marker.append(title)
    cue=Gtk.Overlay(child=tile,hexpand=True,vexpand=True,can_target=False)
    cue.add_overlay(marker)
    return cue
