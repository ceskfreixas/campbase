# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Fixed row capacity adapts widths without changing the chosen column count."""
import tempfile,time,gc
from pathlib import Path
import gi
gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
from gi.repository import Gtk,Adw,Gdk,GLib
from campbase.__main__ import demo_snapshot
from campbase.window import Window
from campbase.storage import Store
from campbase.preferences import Preferences
from campbase.widgets import Column
app=Adw.Application(application_id='cat.ceskfreixas.Campbase.ColumnLayoutCheck');app.register(None)
provider=Gtk.CssProvider();provider.load_from_path(str(Path.cwd()/'campbase/style.css'))
Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
def settle():
 end=time.monotonic()+.2
 while time.monotonic()<end:
  while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
  time.sleep(.005)
with tempfile.TemporaryDirectory() as directory:
 store=Store(directory);snapshot=demo_snapshot()
 for i in range(5,9):snapshot['stacks']['1'].append({'id':i,'title':'Columna '+str(i),'order':i,'cards':[]})
 store.put('snapshot',snapshot);window=Window(app,store,True);window.set_default_size(1100,900);window.present();settle()
 prefs=Preferences(window);prefs.present(window);settle();prefs.columns_per_row.set_selected(3);settle();prefs.force_close();del prefs;gc.collect();settle()
 assert store.settings()['columns_per_row']==3
 for upper in [True,False]:
  store.set_setting('triage',upper);window.render();settle()
  for width in [1100,720]:
   window.set_default_size(width,900);settle()
   first=window.board_body.get_first_child().get_next_sibling()
   assert isinstance(first,Column)==upper
   grid=first.get_next_sibling() if upper else first
   assert isinstance(grid,Gtk.Grid)
   assert isinstance(grid.get_child_at(2,0),Column)
   assert grid.get_child_at(3,0) is None
   expected=7 if upper else 8
   for i in range(expected):
    column=grid.get_child_at(i%3,i//3);assert isinstance(column,Column)
    ok,b=column.compute_bounds(grid);assert ok
    assert b.origin.x>=0 and b.origin.x+b.size.width<=grid.get_width()+1
   assert abs(grid.get_child_at(0,0).get_width()-grid.get_child_at(2,0).get_width())<=1
   print('PASS 3 columns at width',width,'actual',window.get_width(),'separate first row',upper,flush=True)
 # Moving a card between fixed-grid rows uses the same durable outbox.
 source=grid.get_child_at(0,0).drop.widgets[0];target=grid.get_child_at(1,2)
 window.drag_session.begin(source,source.card);target.drop.motion(None,20,20)
 assert target.drop.drop(None,'campbase-card:'+str(source.card['id']),20,20)
 window.drag_session.finish();settle()
 assert window.find_card(source.card['id'])['stackId']==target.stack['id']
 assert store.operations()[0]['kind']=='move'
 # Changing back to automatic restores the responsive arrangement.
 store.set_setting('columns_per_row',0);window.render();settle()
 assert isinstance(window.board_body.get_first_child().get_next_sibling(),Gtk.FlowBox)
 window.close();settle()
