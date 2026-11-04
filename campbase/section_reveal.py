# SPDX-License-Identifier: GPL-3.0-or-later
"""Reveal live section contents in place, with a gentle, reversible collapse."""
import math
from gi.repository import Adw, Graphene, Gsk, Gtk


class SectionLayout(Gtk.BoxLayout):
    def do_get_request_mode(self, widget):
        return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH

    def do_measure(self, widget, orientation, for_size):
        low,natural,*_unused=widget.get_child().measure(orientation,for_size)
        if orientation==Gtk.Orientation.VERTICAL:
            low=math.ceil((low+widget.gap)*widget.position)
            natural=math.ceil((natural+widget.gap)*widget.position)
        return low,natural,-1,-1

    def do_allocate(self, widget, width, height, baseline):
        child=widget.get_child()
        if not child.get_visible():return
        natural=child.measure(Gtk.Orientation.VERTICAL,width)[1]
        offset=Graphene.Point().init(0,widget.gap*widget.position)
        child.allocate(width,natural,-1,Gsk.Transform.new().translate(offset))


class SectionReveal(Gtk.Box):
    def __init__(self, child, *, revealed=True, gap=0):
        super().__init__(visible=revealed,overflow=Gtk.Overflow.HIDDEN)
        self.position=1.0 if revealed else 0.0
        self.target=revealed
        self.gap=gap
        self.animation=None
        self.after_hidden=None
        self.serial=0
        self.set_layout_manager(SectionLayout())
        self.append(child)
        child.set_visible(revealed)

    def get_child(self):
        return self.get_first_child()

    def get_reveal_child(self):
        return self.target

    def get_child_revealed(self):
        return self.target if self.animation is None else not self.target

    def reveal(self, visible, *, animate=True, after_hidden=None, resizing=False):
        # Invalidating ownership first makes old animation callbacks harmless
        # when the user reverses direction before the previous motion finishes.
        self.serial+=1
        serial=self.serial
        previous,self.animation=self.animation,None
        if previous:
            previous.pause();previous.skip()
        self.target=visible
        self.after_hidden=after_hidden if not visible else None
        self.get_child().set_visible(True)
        self.get_child().set_can_target(visible)
        self.set_visible(True)
        if not animate or not self.get_mapped() or self.position==float(visible):
            self.position=float(visible)
            self.finish()
            return
        opening=visible and not resizing
        duration=240 if opening else 260
        def update(value):
            if self.serial!=serial:return
            self.position=value
            self.queue_resize()
        target=Adw.CallbackAnimationTarget.new(update)
        animation=Adw.TimedAnimation.new(self,self.position,float(visible),duration,target)
        animation.set_easing(Adw.Easing.EASE_OUT_CUBIC if opening else Adw.Easing.EASE_IN_OUT_CUBIC)
        self.animation=animation
        animation.connect('done',lambda *_:self.finish() if self.serial==serial else None)
        animation.play()

    def resize_from(self, height, *, animate=True, closing=False):
        """Animate a list mutation along with the section returning its cards."""
        natural=self.get_child().measure(Gtk.Orientation.VERTICAL,self.get_width())[1]+self.gap
        if natural<=0:return
        self.position=height/natural
        self.reveal(True,animate=animate,resizing=closing)

    def finish(self):
        self.animation=None
        self.position=float(self.target)
        self.queue_resize()
        if self.target:return
        callback,self.after_hidden=self.after_hidden,None
        self.get_child().set_visible(False)
        self.set_visible(False)
        if callback:callback()


class SectionBox(Gtk.Box):
    """Keep section spacing inside its animated height, not the parent layout."""
    def __init__(self, **kwargs):
        self.item_gap=kwargs.pop('spacing',10)
        super().__init__(spacing=0,**kwargs)

    def append(self, child):
        if self.get_first_child() is not None:
            if isinstance(child,SectionReveal):child.gap=self.item_gap
            else:child.set_margin_top(child.get_margin_top()+self.item_gap)
        super().append(child)
