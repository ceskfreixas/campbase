# SPDX-License-Identifier: GPL-3.0-or-later
"""Deferred cards scroll within Triage's height instead of stretching the board."""
import copy
import tempfile
import time
from pathlib import Path
import gi
gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
from gi.repository import Adw, Gdk, GLib, Gtk
from campbase.__main__ import demo_snapshot
from campbase.storage import Store
from campbase.window import Window
from campbase.widgets import Column
from campbase.workflow_sections import fold_column
from campbase.workflow_state import save_options


def settle(duration=.5):
    end=time.monotonic()+duration
    while time.monotonic()<end:
        while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
        time.sleep(.005)


def descendants(widget):
    yield widget
    child=widget.get_first_child()
    while child:
        yield from descendants(child);child=child.get_next_sibling()


def column(window,key):
    return next(item for item in descendants(window.board_body) if isinstance(item,Column) and item.stack['id']==key)


app=Adw.Application(application_id='cat.ceskfreixas.Campbase.DeferredHeightCheck');app.register(None)
css=Gtk.CssProvider();css.load_from_path(str(Path(__file__).resolve().parents[1]/'campbase/style.css'))
Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
with tempfile.TemporaryDirectory() as folder:
    store=Store(folder);store.set_setting('auto_sync',False)
    snapshot=demo_snapshot();sample=copy.deepcopy(snapshot['stacks']['1'][1]['cards'][0])
    snapshot['stacks']['1'][1]['cards']=[dict(sample,id=2000+i,title=f'Deferred {i}',order=i) for i in range(40)]
    store.put('snapshot',snapshot)
    save_options(store,1,not_now_enabled=True,not_now_stack=2,not_now_expanded=True)
    w=Window(app,store,True);w.set_default_size(1200,1000);w.present();settle()
    deferred=column(w,2);row=deferred.get_parent()
    first=column(w,1)
    assert first.drop.cards_box.get_column_spacing()==10
    assert first.drop.cards_box.get_row_spacing()==10
    assert column(w,3).drop.cards_box.get_spacing()==10
    full=deferred.get_width()
    fold_column(deferred,False);settle(.08)
    assert row.transition.side is not None
    intermediate=row.transition.side
    assert 52<intermediate<full,(intermediate,full)
    assert deferred.get_width()==full
    # The live Triage stays visible and expands as the deferred pane folds.
    assert first.get_visible() and first.get_opacity()==1
    intermediate_width=first.get_width()
    settle(.04)
    assert first.get_width()>=intermediate_width
    assert first.get_visible() and first.get_opacity()==1
    fold_column(deferred,True);settle(.5)
    assert row.transition.side is None and deferred.expanded
    assert row.get_overflow()==Gtk.Overflow.VISIBLE
    fold_column(deferred,False);settle(.5)
    assert not deferred.expanded and deferred.get_width()<=52,(deferred.expanded,deferred.get_width())
    fold_column(deferred,True);settle(.08)
    assert 52<row.transition.side<full
    settle(.5)
    assert deferred.expanded and row.transition.side is None
    # A fresh folded board must resolve its final width before the first frame.
    save_options(store,1,not_now_expanded=False);w.render();settle()
    deferred=column(w,2);row=deferred.get_parent()
    fold_column(deferred,True);settle(.08)
    destination=row.transition.full_width
    settle()
    valid,bounds=deferred.compute_bounds(row)
    assert valid and abs(bounds.size.width-destination)<=1,(bounds.size.width,destination)
    many=store.get('snapshot')
    many['stacks']['1'][0]['cards'] *= 3
    store.put('snapshot',many);w.render();settle()
    deferred=column(w,2);row=deferred.get_parent()
    fold_column(deferred,False)
    settle(.26)
    nearing=row.get_height()
    settle(.24)
    assert abs(nearing-row.get_height())<12,(nearing,row.get_height())
    fold_column(deferred,True);settle()
    settings=Gtk.Settings.get_default()
    settings.set_property('gtk-enable-animations',False)
    fold_column(deferred,False);settle(.04)
    assert not deferred.expanded and row.transition.side is None
    fold_column(deferred,True);settle(.04)
    assert deferred.expanded and row.transition.side is None
    settings.set_property('gtk-enable-animations',True)
    w.set_default_size(480,1000);settle()
    fold_column(column(w,2),False);settle()
    fold_column(column(w,2),True);settle()
    assert column(w,2).expanded
    w.close()
print('Deferred transition: intermediate widths, reversal, reduced motion and narrow layout PASS')
