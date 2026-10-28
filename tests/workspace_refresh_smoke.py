# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Keep the visible card stable across asynchronous workspace reconstruction."""
import copy,tempfile,time
from pathlib import Path
import gi
gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
from gi.repository import Adw,Gtk,Gdk,GLib
from campbase.storage import Store
from campbase.window import Window

app=Adw.Application(application_id='cat.cesk.Campbase.RefreshPositionCheck');app.register(None)
css=Gtk.CssProvider();css.load_from_path(str(Path.cwd()/'campbase/style.css'))
Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
def settle():
 end=time.monotonic()+.25
 while time.monotonic()<end:
  while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
  time.sleep(.005)
def descendants(widget):
 yield widget
 child=widget.get_first_child()
 while child:
  yield from descendants(child);child=child.get_next_sibling()
def tiles(window):return [node for node in descendants(window.board_body) if node.has_css_class('active-tile')]
def offset(window,card_id):
 tile=next(tile for tile in tiles(window) if tile.card['id']==card_id)
 ok,b=tile.compute_bounds(window.board_body);assert ok
 return b.origin.y-window.scroll.get_vadjustment().get_value()
with tempfile.TemporaryDirectory() as directory:
 store=Store(directory);store.set_setting('auto_sync',False);store.set_setting('triage',False)
 store.set_setting('columns_per_row',1)
 cards=[{'id':i,'stackId':10,'title':f'Targeta {i}','order':i,'archived':False} for i in range(1,81)]
 snapshot={'boards':[{'id':1,'title':'Prova'},{'id':2,'title':'Altre tauler'}],
           'stacks':{'1':[{'id':10,'title':'Columna','cards':cards}],
                     '2':[{'id':20,'title':'Altra','cards':[dict(c,id=c['id']+100,stackId=20) for c in cards]}]}}
 store.put('snapshot',snapshot);w=Window(app,store,True);w.set_default_size(1000,700);w.present();settle()
 adjustment=w.scroll.get_vadjustment();adjustment.set_value(1200);settle()
 anchor=min(tiles(w),key=lambda tile:abs(offset(w,tile.card['id'])))
 anchor.card_widget.grab_focus();settle();original=offset(w,anchor.card['id'])
 assert adjustment.get_value()>900
 for round_number in range(3):
  updated=copy.deepcopy(snapshot)
  updated['stacks']['1'][0]['cards'].insert(0,dict(cards[0],id=900+round_number,title='Nova abans de la vista',order=0))
  for order,card in enumerate(updated['stacks']['1'][0]['cards']):card['order']=order
  store.put('snapshot',updated)
  w.engine.notify();w.engine.notify();settle()
  assert abs(offset(w,anchor.card['id'])-original)<2,(original,offset(w,anchor.card['id']))
  assert adjustment.get_value()>900
 store.put('snapshot',snapshot);w.engine.notify();settle()
 assert abs(offset(w,anchor.card['id'])-original)<2
 # Intentional board navigation starts at the top rather than restoring another board.
 w.board_list.select_row(w.board_list.get_row_at_index(1));settle()
 assert w.board_id==2 and adjustment.get_value()==0
 adjustment.set_value(900);settle();w.retranslate();settle()
 assert abs(adjustment.get_value()-900)<2
 updated=copy.deepcopy(snapshot);updated['stacks']['2'][0]['cards']=updated['stacks']['2'][0]['cards'][:2]
 store.put('snapshot',updated);w.engine.notify();settle()
 assert adjustment.get_value()==max(0,adjustment.get_upper()-adjustment.get_page_size())
 w.close();settle()
print('PASS repeated refreshes, inserted cards, focused cards, board navigation and language refresh position')
