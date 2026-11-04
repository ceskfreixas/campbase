# SPDX-License-Identifier: GPL-3.0-or-later
"""Native, interruptible folding without squeezing the deferred cards."""
from gi.repository import Adw, GLib, Graphene, Gsk, Gtk


class DeferredTransition:
    duration=300

    def __init__(self, row):
        self.row=row
        self.animation=None
        self.side=None
        self.full_width=0
        self.stacked=False
        self.scroll_offset=None
        self.progress=0
        self.main_width=0
        self.main_height=0
        self.start_height=0
        self.end_height=0
        self.triage_motion=None

    def start(self, expanded, *, keyboard_focus=False):
        from .workflow_sections import apply_fold
        row=self.row
        column=row.get_last_child()
        if self.animation:
            self.animation.pause()
        main=row.get_first_child()
        if getattr(main,'triage',False):
            from .triage_motion import TriageMotion
            self.triage_motion=TriageMotion(main)
        _,self.main_start=main.compute_bounds(row)
        self.start_height=row.get_height()
        _,self.rail_start=column.compute_bounds(row)
        scroll=column.not_now_scroll
        adjustment=scroll.get_vadjustment()
        if not expanded and self.side is None:
            self.scroll_offset=adjustment.get_value()
        scroll._folding=True
        valid,bounds=column.compute_bounds(row)
        start=self.side if self.side is not None else (bounds.size.width if valid else column.get_width())
        # Both directions render the full contents until the animation ends.
        column.expanded=True
        apply_fold(column)
        row.reference_width=row.reference_side_width()
        self.full_width=max(column.measure(Gtk.Orientation.HORIZONTAL,-1)[0],row.reference_width or 300)
        minimum=row.get_first_child().measure(Gtk.Orientation.HORIZONTAL,-1)[0]
        end=self.full_width if expanded else 52
        self.stacked=row.get_width()<minimum+14+end
        self.side=start
        self.progress=0
        self.main_width=row.get_width() if self.stacked else max(1,row.get_width()-end-14)
        self.main_height=main.measure(Gtk.Orientation.VERTICAL,self.main_width)[1]
        rail_height=column.measure(Gtk.Orientation.VERTICAL,min(row.get_width(),self.full_width))[1]
        if self.stacked:
            self.rail_height=max(self.main_height,rail_height)
            self.end_height=self.main_height+self.rail_height+14
            self.rail_x=0;self.rail_y=self.main_height+14
        else:
            self.end_height=max(self.main_height,rail_height)
            self.main_height=self.end_height
            self.rail_height=self.end_height
            self.rail_x=row.get_width()-end;self.rail_y=0
        if self.triage_motion:
            # Let GTK calculate both endpoints once. During the animation each
            # live child follows those endpoints instead of switching grid rows.
            main.allocate(self.main_width,self.main_height,-1,None)
            self.triage_motion.destination()
            main.allocate(round(self.main_start.size.width),round(self.main_start.size.height),-1,None)
            self.triage_motion.allocate(0)
        row.set_overflow(Gtk.Overflow.HIDDEN)

        def update(progress):
            self.progress=progress
            self.side=start+(end-start)*progress
            progress=max(0,min(1,(self.side-52)/max(1,self.full_width-52)))
            column.body.set_opacity(progress)
            column.get_first_child().set_opacity(progress)
            row.queue_resize()

        target=Adw.CallbackAnimationTarget.new(update)
        animation=Adw.TimedAnimation.new(row,0,1,self.duration,target)
        animation.set_easing(Adw.Easing.EASE_OUT_CUBIC)
        self.animation=animation

        def finish(*_unused):
            if self.animation is not animation:return
            self.animation=None;self.side=None;self.triage_motion=None
            column.body.set_opacity(1)
            column.get_first_child().set_opacity(1)
            column.expanded=expanded
            apply_fold(column)
            row.set_overflow(Gtk.Overflow.VISIBLE)
            if keyboard_focus:
                (column.fold_button if expanded else column.expand_button).grab_focus()
            row.queue_resize()
            if expanded and self.scroll_offset is not None:
                desired=self.scroll_offset
                def restore():
                    if self.animation is None and column.expanded:
                        adjustment.set_value(desired)
                        scroll._folding=False
                    return False
                GLib.timeout_add(64,restore)
            else:
                scroll._folding=False

        animation.connect('done',finish)
        animation.play()

    def height(self):
        return round(self.start_height+(self.end_height-self.start_height)*self.progress)

    def interpolate(self, start, end):
        return start+(end-start)*self.progress

    def allocate(self, width):
        main,column=self.row.get_first_child(),self.row.get_last_child()
        main_width=round(self.interpolate(self.main_start.size.width,self.main_width))
        main_height=round(self.interpolate(self.main_start.size.height,self.main_height))
        main.allocate(max(1,main_width),max(1,main_height),-1,None)
        if self.triage_motion:self.triage_motion.allocate(self.progress)
        x=self.interpolate(self.rail_start.origin.x,self.rail_x)
        y=self.interpolate(self.rail_start.origin.y,self.rail_y)
        height=round(self.interpolate(self.rail_start.size.height,self.rail_height))
        column.allocate(min(width,self.full_width),max(1,height),-1,
            Gsk.Transform.new().translate(Graphene.Point().init(x,y)))
