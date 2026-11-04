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


def settle():
    end=time.monotonic()+.5
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
    first=column(w,1);deferred=column(w,2)
    assert deferred.get_parent() is first.get_parent()
    assert abs(first.get_height()-deferred.get_height())<=1,(first.get_height(),deferred.get_height())
    assert abs(deferred.drop.widgets[0].get_width()-column(w,3).drop.widgets[0].get_width())<=1,(
        deferred.drop.widgets[0].get_width(),column(w,3).drop.widgets[0].get_width())
    assert deferred.not_now_scrollbar.get_width()<=6
    height=first.get_parent().get_height()
    adjustment=deferred.not_now_scroll.get_vadjustment()
    assert adjustment.get_upper()>adjustment.get_page_size()*2
    adjustment.set_value(adjustment.get_upper()-adjustment.get_page_size());settle()
    offset=adjustment.get_value()
    w.render();settle();deferred=column(w,2)
    adjustment=deferred.not_now_scroll.get_vadjustment()
    assert abs(adjustment.get_value()-offset)<1
    fold_column(deferred,False);settle();fold_column(deferred,True);settle()
    assert abs(adjustment.get_value()-offset)<1
    last=deferred.drop.widgets[-1]
    _,bounds=last.compute_bounds(deferred.not_now_scroll)
    assert bounds.origin.y>=0 and bounds.origin.y+bounds.size.height<=deferred.not_now_scroll.get_height()+1
    # A card at the bottom remains draggable back to the active workflow.
    w.drag_session.begin(last,last.card);settle()
    target=column(w,3)
    assert target.drop.drop(None,'campbase-card:'+str(last.card['id']),10,10)
    w.drag_session.finish();settle()
    assert w.find_card(last.card['id'])['stackId']==3
    w._undo_toast.emit('button-clicked');settle()
    assert w.find_card(last.card['id'])['stackId']==2 and not store.operations()
    snapshot['stacks']['1'][1]['cards'] += [dict(sample,id=3000+i,title=f'More {i}',order=40+i) for i in range(40)]
    store.put('snapshot',snapshot);w.render();settle()
    assert column(w,1).get_parent().get_height()==height
    deferred=column(w,2);fold_column(deferred,False);settle();fold_column(deferred,True);settle()
    assert abs(column(w,1).get_height()-deferred.get_height())<=1
    # At phone-like widths the expanded column wraps below Triage and stays bounded.
    w.set_default_size(480,1000);settle()
    # The responsive breakpoint rebuilds the board asynchronously. Wait for
    # the newly allocated reference column rather than inspecting its first frame.
    deadline=time.monotonic()+2
    while time.monotonic()<deadline:
        deferred=column(w,2)
        if abs(deferred.drop.widgets[0].get_width()-column(w,3).drop.widgets[0].get_width())<=1:break
        settle()
    deferred=column(w,2);first=column(w,1)
    assert deferred.get_width()<=w.board_body.get_width()
    assert abs(first.get_height()-deferred.get_height())<=1,(first.get_height(),deferred.get_height())
    assert deferred.not_now_scroll.get_vadjustment().get_upper()>deferred.not_now_scroll.get_vadjustment().get_page_size()
    assert abs(deferred.drop.widgets[0].get_width()-column(w,3).drop.widgets[0].get_width())<=1,(
        deferred.drop.widgets[0].get_width(),column(w,3).drop.widgets[0].get_width())
    # Width follows the actual lower cards, including a fixed grid and no Triage row.
    w.set_default_size(1200,1000);store.set_setting('columns_per_row',3);w.render();settle()
    assert abs(column(w,2).drop.widgets[0].get_width()-column(w,3).drop.widgets[0].get_width())<=1
    store.set_setting('triage',False);w.render();settle();settle()
    assert abs(column(w,2).drop.widgets[0].get_width()-column(w,3).drop.widgets[0].get_width())<=1,(
        column(w,2).drop.widgets[0].get_width(),column(w,3).drop.widgets[0].get_width())
    # Empty panes keep the same width; hiding the scrollbar does not move the cards.
    empty=store.get('snapshot');empty['stacks']['1'][1]['cards']=[]
    empty['stacks']['1'][2]['cards']=[]
    store.put('snapshot',empty);w.render();settle();settle()
    assert not column(w,2).not_now_scrollbar.get_visible()
    assert abs(column(w,2).body.get_width()-column(w,3).drop.cards_box.get_width())<=1
    # Resize an empty deferred column continuously beside three fixed columns,
    # matching the real configuration rather than rebuilding after each resize.
    empty['stacks']['1'][2]['cards']=[dict(sample,id=4000,stackId=3,title='Visible reference card')]
    empty['stacks']['1'].append({'id':5,'title':'Another column','order':5,'cards':[]})
    store.put('snapshot',empty);store.set_setting('triage',True);w.render();settle()
    for width in (1240,1020,1500,980,1880,1100,740,1320):
        w.set_default_size(width,1000);settle()
        actual=column(w,2).body.get_width();expected=column(w,3).drop.cards_box.get_width()
        assert abs(actual-expected)<=1,(width,actual,expected)
        _,deferred_bounds=column(w,2).compute_bounds(w.board_body)
        _,reference_bounds=column(w,3).compute_bounds(w.board_body)
        assert abs(deferred_bounds.size.width-reference_bounds.size.width)<=1,(
            width,deferred_bounds.size.width,reference_bounds.size.width)
    deferred=column(w,2);fold_column(deferred,False);settle()
    _,bounds=deferred.compute_bounds(w.board_body)
    assert bounds.size.width<=54,bounds.size.width
    w.close();settle()
print('PASS bounded deferred height, internal scrolling, bottom-card drag/undo, growth and narrow layout')
