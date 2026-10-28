# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Synthetic startup preferences, timer scheduling and manual synchronization."""
import tempfile,time
from pathlib import Path
from unittest.mock import Mock,patch
import gi
gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
from gi.repository import Gtk,Adw,Gdk,GLib
from campbase.__main__ import demo_snapshot
from campbase.storage import Store
from campbase.window import Window
from campbase.dialogs import Preferences
from campbase.account import Account

app=Adw.Application(application_id='cat.cesk.Campbase.PreferencesCheck');app.register(None)
provider=Gtk.CssProvider();provider.load_from_path(str(Path.cwd()/'campbase/style.css'))
Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
def settle():
 end=time.monotonic()+.15
 while time.monotonic()<end:
  while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
  time.sleep(.005)
def open_window(store):
 window=Window(app,store,True);window.set_default_size(1100,850);window.present();settle();return window
def descendants(widget):
 yield widget
 child=widget.get_first_child()
 while child:
  yield from descendants(child);child=child.get_next_sibling()
def timer_seconds(window):
 source=GLib.MainContext.default().find_source_by_id(window.timer)
 assert source is not None
 return (source.get_ready_time()-GLib.get_monotonic_time())/1000000
with tempfile.TemporaryDirectory() as directory:
 store=Store(directory);snapshot=demo_snapshot()
 snapshot['boards'].append({'id':2,'title':'Un altre projecte','color':'3584E4','archived':False})
 snapshot['stacks']['2']=[]
 store.put('snapshot',snapshot);store.set_setting('board_id',1);store.set_setting('sidebar',True)
 window=open_window(store)
 assert window.board_id==1 and window.split.get_show_sidebar()
 assert store.settings()['startup_sidebar'] is True
 preferences=Preferences(window);preferences.present(window);settle()
 groups={node.get_title():node for node in descendants(preferences) if isinstance(node,Adw.PreferencesGroup)}
 rows=lambda group:{node.get_title() for node in descendants(group) if isinstance(node,Adw.PreferencesRow)}
 assert rows(groups['Aparença'])=={'Tema'}
 assert rows(groups['Vista del tauler'])=={'Primera columna en una fila superior','Màxim de columnes per fila','Mostra les targetes arxivades per defecte'}
 preferences.startup_board.set_selected(2)
 preferences.startup_sidebar.set_active(False)
 assert window.board_id==1 and window.split.get_show_sidebar()
 assert store.settings()['startup_board_id']==2
 preferences.auto_sync.set_active(False)
 assert not window.timer and not preferences.interval.get_sensitive()
 with patch.object(window.engine,'sync') as sync:
  window.demo=False;window.engine.api=Mock()
  window.periodic_sync();sync.assert_not_called()
  window.lookup_action('sync').activate(None);sync.assert_called_once_with()
  window.demo=True
 preferences.auto_sync.set_active(True)
 assert window.timer and preferences.interval.get_sensitive()
 preferences.interval.set_selected(5)
 assert store.settings()['sync_interval']==600 and 598<timer_seconds(window)<602
 preferences.force_close();window.close();settle()
 # The chosen startup state is independent of the previous window's sidebar.
 window=open_window(store)
 assert window.board_id==2 and not window.split.get_show_sidebar()
 assert 598<timer_seconds(window)<602
 window.split.set_show_sidebar(True)
 assert store.settings()['startup_sidebar'] is False
 preferences=Preferences(window);preferences.present(window);settle()
 preferences.startup_board.set_selected(0)
 preferences.force_close();window.board_list.select_row(window.board_list.get_row_at_index(0));settle()
 assert window.board_id==1
 window.close();settle()
 window=open_window(store);assert window.board_id==1 and not window.split.get_show_sidebar()
 window.close();settle()
 # A deleted startup board falls back to the last available board.
 store.set_setting('startup_board_id',999)
 window=open_window(store);assert window.board_id==1
 window.close();settle()
 # First data arriving after an empty cache still honors the startup choice.
 store.set_setting('startup_board_id',2);store.put('snapshot',{'boards':[],'stacks':{}})
 window=open_window(store);assert window.board_id is None
 store.put('snapshot',snapshot);window.render();settle();assert window.board_id==2
 window.close();settle()
 # F5 retries a failed account load, even with automatic synchronization off.
 store.set_setting('auto_sync',False)
 window=open_window(store);window.demo=False;window.engine.api=None
 account=Account('https://example.invalid','fixture','test-only','test')
 with patch('campbase.window.Account.load',side_effect=[ValueError('Temporary network failure'),account]) as load, patch.object(Account,'save'), patch.object(window.engine,'sync') as sync:
  window.lookup_action('sync').activate(None)
  for _ in range(20):
   settle()
   if not window.account_loading:break
  assert not window.account_loading and window.engine.api is None
  sync.assert_not_called()
  window.lookup_action('sync').activate(None)
  for _ in range(20):
   settle()
   if not window.account_loading:break
  assert not window.account_loading and window.engine.api is not None
  assert load.call_count==2
  sync.assert_called_once_with(automatic=False)
 window.close();settle()
print('PASS startup board, independent sidebar preference, persisted intervals, automatic toggle and manual F5')
