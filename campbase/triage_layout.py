# SPDX-License-Identifier: GPL-3.0-or-later
"""A narrow deferred-work rail beside Triage, with a stacked narrow-screen fallback."""
from gi.repository import GLib, Graphene, Gsk, Gtk
from . import localization as ui
from .i18n import _
from .widgets import label


class RotatedLayout(Gtk.BoxLayout):
    def do_measure(self, widget, orientation, for_size):
        other=Gtk.Orientation.VERTICAL if orientation==Gtk.Orientation.HORIZONTAL else Gtk.Orientation.HORIZONTAL
        low,natural,*_unused=widget.get_first_child().measure(other,-1)
        return low,natural,-1,-1

    def do_allocate(self, widget, width, height, baseline):
        transform=Gsk.Transform.new().translate(Graphene.Point().init(0,height)).rotate(-90)
        widget.get_first_child().allocate(height,width,-1,transform)


class RotatedTitle(Gtk.Box):
    def __init__(self, title):
        super().__init__(can_target=False)
        self.set_layout_manager(RotatedLayout())
        self.append(label(title,'heading',xalign=.5,can_target=False))


class TriageLayout(Gtk.BoxLayout):
    gap=14

    def do_get_request_mode(self, widget):
        return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH

    def geometry(self, widget, width):
        main,rail=widget.get_first_child(),widget.get_last_child()
        minimum=main.measure(Gtk.Orientation.HORIZONTAL,-1)[0]
        minimum_side=rail.measure(Gtk.Orientation.HORIZONTAL,-1)[0]
        side=max(minimum_side,widget.reference_width or 300) if rail.expanded else rail.measure(Gtk.Orientation.HORIZONTAL,-1)[1]
        stacked=width<minimum+self.gap+side
        return main,rail,side,stacked

    def do_measure(self, widget, orientation, for_size):
        main,rail=widget.get_first_child(),widget.get_last_child()
        if orientation==Gtk.Orientation.HORIZONTAL:
            a=main.measure(orientation,-1);b=rail.measure(orientation,-1)
            side=max(b[0],widget.reference_width or 300) if rail.expanded else b[1]
            return max(a[0],b[0]),a[1]+side+self.gap,-1,-1
        if widget.transition.side is not None:
            height=widget.transition.height()
            return height,height,-1,-1
        width=for_size if for_size>=0 else 900
        main,rail,side,stacked=self.geometry(widget,width)
        a=main.measure(orientation,width if stacked else max(1,width-side-self.gap))
        b=rail.measure(orientation,min(width,side) if stacked else side)
        if stacked:
            # Keep the same usable height when the expanded column wraps below
            # Triage; its scrollable content must not dictate the row height.
            return a[0]+max(a[0],b[0])+self.gap,a[1]+max(a[1],b[1])+self.gap,-1,-1
        return max(a[0],b[0]),max(a[1],b[1]),-1,-1

    def do_allocate(self, widget, width, height, baseline):
        if widget.transition.side is not None:
            widget.transition.allocate(width)
            return
        widget.sync_reference_width()
        main,rail,side,stacked=self.geometry(widget,width)
        if stacked:
            top=main.measure(Gtk.Orientation.VERTICAL,width)[1]
            main.allocate(width,top,-1,None)
            offset=Graphene.Point().init(0,top+self.gap)
            rail.allocate(min(width,side),max(1,height-top-self.gap),-1,Gsk.Transform.new().translate(offset))
        else:
            main.allocate(max(1,width-side-self.gap),height,-1,None)
            offset=Graphene.Point().init(width-side,0)
            rail.allocate(side,height,-1,Gsk.Transform.new().translate(offset))


class TriageRow(Gtk.Box):
    def __init__(self, main, deferred, reference=None):
        super().__init__(hexpand=True)
        self.reference_column=reference
        self.reference_width=None
        self._width_tick=0
        from .deferred_transition import DeferredTransition
        self.transition=DeferredTransition(self)
        self.add_css_class('triage-row')
        self.set_layout_manager(TriageLayout())
        main.set_valign(Gtk.Align.FILL)
        self.append(main);self.append(deferred)

    def reference_side_width(self):
        """Resolve the destination before opening, even on a folded first render."""
        reference=self.reference_column
        if reference is None or reference.get_width()<=0:return self.reference_width
        deferred=self.get_last_child()
        padding=deferred.get_style_context().get_padding()
        viewport=deferred.not_now_scroll.get_parent()
        gutter=viewport.get_last_child().measure(Gtk.Orientation.HORIZONTAL,-1)[0]
        overhead=padding.left+padding.right+viewport.get_spacing()+gutter
        content=reference.drop.cards_box.get_width() or reference.get_first_child().get_width()
        width=content+overhead
        main=self.get_first_child()
        if reference.is_ancestor(main):
            valid,bounds=reference.compute_bounds(main)
            if valid and bounds.size.width>0:
                count=max(1,round((main.get_width()+14)/(bounds.size.width+14)))
                reference_overhead=bounds.size.width-content
                width=(self.get_width()-count*14+count*(overhead-reference_overhead))/(count+1)
        return round(width)

    def sync_reference_width(self):
        if self._width_tick or self.reference_column is None or self.transition.side is not None:
            return
        frames=[0]
        def sync(*_unused):
            frames[0]+=1
            if frames[0]<2:
                return True
            reference=self.reference_column
            parent=self.get_parent()
            deferred=self.get_last_child()
            if reference.get_width()>0 and deferred.expanded and parent:
                width=self.reference_side_width()
                if width and (self.reference_width is None or abs(width-self.reference_width)>1):
                    self.reference_width=width
                    self.queue_resize()
            # The reference viewport can allocate one frame after this one.
            # Recheck before stopping so resizing cannot leave a stale width.
            if frames[0]<3:
                return True
            self._width_tick=0
            return False
        self._width_tick=GLib.timeout_add(16,sync)


def install_rail(column):
    from .column_menu import column_menu
    from .workflow_sections import fold_column
    rail=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8,halign=Gtk.Align.CENTER,vexpand=True)
    rail.add_css_class('not-now-rail')
    rail.append(column_menu(column.window,column.stack))
    expand=ui.create(Gtk.Button,tooltip_text=_("Desplega «Ara no»"),vexpand=True)
    expand.add_css_class('flat');expand.add_css_class('not-now-toggle')
    expand.set_focus_on_click(False)
    expand.set_child(RotatedTitle(column.stack['title']))
    expand.connect('clicked',lambda *_:fold_column(column,True))
    rail.append(expand)
    column.expand_button=expand
    column.rail=rail
    column.append(rail)
    rail.set_margin_top(0)
