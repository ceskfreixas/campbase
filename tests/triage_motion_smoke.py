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
    snapshot['stacks']['1'][1]['cards']=[dict(sample,id=2000+i,title=f'Deferred {i}',order=i) for i in range(5)]
    snapshot['stacks']['1'][0]['cards']=[dict(sample,id=5000+i,stackId=1,title=f'Targeta de Triatge número {i+1}',order=i) for i in range(6)]
    store.set_setting('columns_per_row',3)
    store.put('snapshot',snapshot)
    save_options(store,1,not_now_enabled=True,not_now_stack=2,not_now_expanded=True)
    w=Window(app,store,True);w.set_default_size(943,900);w.present();settle()
    first=column(w,1);deferred=column(w,2);row=deferred.get_parent()
    def positions():
        result=[]
        for card in first.drop.widgets:
            valid,rect=card.compute_bounds(first)
            assert valid and card.get_visible() and card.get_opacity()==1
            result.append((rect.origin.x,rect.origin.y,rect.size.width,rect.size.height))
        return result
    def close_to(actual,expected,tolerance=1):
        assert all(abs(a-b)<=tolerance for a,b in zip(actual,expected)),(actual,expected)
    settings=Gtk.Settings.get_default()
    settings.set_property('gtk-enable-animations',False)
    narrow=positions()
    fold_column(deferred,False);settle()
    wide=positions()
    assert abs(wide[1][0]-wide[0][0])>100
    assert abs(narrow[1][1]-narrow[0][1])>20
    fold_column(deferred,True);settle()
    settings.set_property('gtk-enable-animations',True)
    row.transition.duration=600
    for expanded,start,end in [(False,narrow,wide),(True,wide,narrow)]:
        fold_column(deferred,expanded)
        middle=0
        while row.transition.side is not None:
            settle(.035)
            if row.transition.side is None:break
            progress=row.transition.progress
            actual=positions()
            for before,after,current in zip(start,end,actual):
                expected=tuple(a+(b-a)*progress for a,b in zip(before,after))
                close_to(current,expected,2)
            if .1<progress<.9:middle+=1
        assert middle>=2
        for actual,expected in zip(positions(),end):close_to(actual,expected)
    # Reversing halfway starts at the actual visible positions, not a native
    # intermediate grid arrangement. The next frame must continue from there.
    fold_column(deferred,False);settle(.08)
    before=positions()
    fold_column(deferred,True)
    for actual,expected in zip(positions(),before):close_to(actual,expected)
    settle(.75)
    for actual,expected in zip(positions(),narrow):close_to(actual,expected)
    assert first.get_opacity()==1
    for count in (0,1):
        sparse=store.get('snapshot')
        sparse['stacks']['1'][0]['cards']=snapshot['stacks']['1'][0]['cards'][:count]
        store.put('snapshot',sparse);w.render();settle()
        deferred=column(w,2)
        fold_column(deferred,False);settle()
        fold_column(deferred,True);settle()
        assert column(w,1).get_opacity()==1
        assert len(column(w,1).drop.widgets)==count
    w.close()
print('PASS live Triage cards follow both layout endpoints continuously, stay visible and reverse without jumping')
