# SPDX-License-Identifier: GPL-3.0-or-later
"""A native inner viewport with a narrow, reserved scrollbar gutter."""
from gi.repository import Gtk


class DeferredViewport(Gtk.Box):
    def __init__(self, window, body):
        super().__init__(spacing=4,vexpand=True)
        self.scroll=Gtk.ScrolledWindow(child=body,hexpand=True,vexpand=True,
            hscrollbar_policy=Gtk.PolicyType.NEVER,vscrollbar_policy=Gtk.PolicyType.EXTERNAL,
            min_content_height=0,propagate_natural_height=False)
        self.append(self.scroll)
        adjustment=self.scroll.get_vadjustment()
        gutter=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,width_request=6)
        self.scrollbar=Gtk.Scrollbar(orientation=Gtk.Orientation.VERTICAL,adjustment=adjustment,vexpand=True)
        self.scrollbar.add_css_class('deferred-scrollbar')
        gutter.append(self.scrollbar);self.append(gutter)
        def visibility(*_unused):
            self.scrollbar.set_visible(adjustment.get_upper()>adjustment.get_page_size()+1)
        adjustment.connect('changed',visibility);visibility()
        retain_deferred_scroll(window,self.scroll)


def retain_deferred_scroll(window, scroller):
    """Keep the inner viewport through sync rebuilds; searches start at the top."""
    account=window.account
    key=(getattr(account,'goa_id',None),getattr(account,'server',None),window.board_id)
    context=(window.query,window.only_mine)
    if not hasattr(window,'_deferred_scroll_offsets'):
        window._deferred_scroll_offsets={}
    positions=window._deferred_scroll_offsets
    adjustment=scroller.get_vadjustment()
    restoring=[True]
    def remember(*_unused):
        if not restoring[0] and not getattr(scroller,'_folding',False) and scroller.get_mapped():
            positions[key]=(context,adjustment.get_value())
    def mapped(*_unused):
        previous_context,value=positions.get(key,(context,0))
        desired=value if previous_context==context else 0
        restoring[0]=True
        frames=[0]
        previous=[None]
        def restore(*_unused):
            frames[0]+=1
            if frames[0]<2:
                return True
            adjustment.set_value(desired)
            geometry=(adjustment.get_upper(),adjustment.get_page_size(),scroller.get_width())
            stable=geometry==previous[0]
            previous[0]=geometry
            # Card widths can settle after the outer and inner viewports have
            # both allocated. Do not remember an intermediate clamped offset.
            if frames[0]<4 or not stable and frames[0]<8:
                return True
            restoring[0]=False;remember()
            return False
        scroller.add_tick_callback(restore)
    adjustment.connect('value-changed',remember)
    scroller.connect('map',mapped)
