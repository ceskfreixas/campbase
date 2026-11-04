# SPDX-License-Identifier: GPL-3.0-or-later
"""Move live Triage widgets between native layout endpoints, without a reflow jump."""
from gi.repository import Graphene, Gsk, Gtk
from .card_tiles import CardTile


def bounds(widget, parent):
    valid, rect=widget.compute_bounds(parent)
    if not valid:return None
    left,right=widget.get_margin_start(),widget.get_margin_end()
    if Gtk.Widget.get_direction(widget)==Gtk.TextDirection.RTL:left,right=right,left
    top,bottom=widget.get_margin_top(),widget.get_margin_bottom()
    return rect.origin.x-left,rect.origin.y-top,rect.size.width+left+right,rect.size.height+top+bottom


class MovingChild:
    def __init__(self, widget, parent):
        self.widget,self.parent=widget,parent
        self.start=bounds(widget,parent)
        self.end=self.start
        self.children=[]
        # Card contents keep their native text/icon layout. Move the whole card,
        # including its FlowBox wrapper, rather than distorting individual labels.
        if isinstance(widget,(CardTile,Gtk.FlowBoxChild,Gtk.Button,Gtk.MenuButton)):
            return
        child=widget.get_first_child()
        while child:
            if child.should_layout():self.children.append(MovingChild(child,widget))
            child=child.get_next_sibling()

    def destination(self):
        self.end=bounds(self.widget,self.parent)
        for child in self.children:child.destination()

    def allocate(self, progress):
        if self.widget.get_parent() is not self.parent or self.start is None or self.end is None:return
        x,y,width,height=(a+(b-a)*progress for a,b in zip(self.start,self.end))
        transform=Gsk.Transform.new().translate(Graphene.Point().init(x,y))
        self.widget.allocate(max(1,round(width)),max(1,round(height)),-1,transform)
        for child in self.children:child.allocate(progress)


class TriageMotion:
    def __init__(self, column):
        self.children=[]
        child=column.get_first_child()
        while child:
            if child.should_layout():self.children.append(MovingChild(child,column))
            child=child.get_next_sibling()

    def destination(self):
        for child in self.children:child.destination()

    def allocate(self, progress):
        for child in self.children:child.allocate(progress)
