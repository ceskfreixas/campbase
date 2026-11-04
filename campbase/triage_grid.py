# SPDX-License-Identifier: GPL-3.0-or-later
"""A stable Triage grid: available space sets cell width, card content sets height."""
import math
from gi.repository import Graphene, Gsk, Gtk


class TriageGridLayout(Gtk.BoxLayout):
    def cells(self, grid, width):
        cards=[]
        child=grid.get_first_child()
        while child:
            if child.should_layout():cards.append(child)
            child=child.get_next_sibling()
        count=grid.columns_for(width)
        cell=max(1,(width-(count-1)*grid.spacing)//count)
        height=max((card.measure(Gtk.Orientation.VERTICAL,cell)[1] for card in cards),default=0)
        return cards,count,cell,height

    def do_get_request_mode(self, grid):
        return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH

    def do_measure(self, grid, orientation, for_size):
        if orientation==Gtk.Orientation.HORIZONTAL:
            return grid.card_width,grid.card_width,-1,-1
        cards,count,cell,height=self.cells(grid,for_size if for_size>=0 else grid.card_width)
        rows=math.ceil(len(cards)/count)
        total=rows*height+max(0,rows-1)*grid.row_spacing
        return total,total,-1,-1

    def do_allocate(self, grid, width, height, baseline):
        cards,count,cell,row_height=self.cells(grid,width)
        rtl=Gtk.Widget.get_direction(grid)==Gtk.TextDirection.RTL
        for index,card in enumerate(cards):
            x=(index%count)*(cell+grid.spacing)
            if rtl:x=width-x-cell
            y=(index//count)*(row_height+grid.row_spacing)
            card.allocate(cell,row_height,-1,Gsk.Transform.new().translate(Graphene.Point().init(x,y)))


class TriageGrid(Gtk.Box):
    card_width=252
    spacing=10

    def __init__(self, *, row_spacing=10):
        super().__init__(orientation=Gtk.Orientation.VERTICAL,hexpand=True,valign=Gtk.Align.START)
        self.row_spacing=row_spacing
        self.set_layout_manager(TriageGridLayout(orientation=Gtk.Orientation.VERTICAL))

    def columns_for(self, width):
        return max(1,(max(1,width)+self.spacing)//(self.card_width+self.spacing))

    def cell_width(self):
        width=self.get_width() or self.card_width
        count=self.columns_for(width)
        return max(1,(width-(count-1)*self.spacing)//count)

    def get_column_spacing(self):return self.spacing
    def get_row_spacing(self):return self.row_spacing

    def insert(self, child, index):
        previous=None
        sibling=self.get_first_child()
        position=0
        while sibling and (index<0 or position<index):
            previous=sibling;sibling=sibling.get_next_sibling();position+=1
        self.insert_child_after(child,previous)
