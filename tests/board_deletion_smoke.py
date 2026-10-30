# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Owner-only sidebar deletion against a synthetic Nextcloud account."""
import gi
gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
from gi.repository import Adw,Gtk,Gdk,GLib
import copy,http.server,tempfile,threading,time
from pathlib import Path
from types import SimpleNamespace
from test_collaboration import Fixture,USERS
from campbase.storage import Store
from campbase.window import Window
from campbase.deck import Deck
from campbase.board_deletion import BoardDeletionDialog
from gui_helpers import present,wait_presented

def settle(until=None):
 end=time.monotonic()+(5 if until else .2)
 while time.monotonic()<end:
  while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
  if until and until():return
  time.sleep(.005)
 if until:assert until(),'Synthetic deletion timed out'

def children(widget):
 child=widget.get_first_child()
 while child:
  yield child;child=child.get_next_sibling()

app=Adw.Application(application_id='cat.ceskfreixas.Campbase.BoardDeletionCheck');app.register(None)
css=Gtk.CssProvider();css.load_from_path(str(Path.cwd()/'campbase/style.css'))
Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Fixture)
threading.Thread(target=server.serve_forever,daemon=True).start()
server.board={'id':1,'title':'Tauler propi','owner':USERS[0],'users':[USERS[0]],'permissions':{'PERMISSION_MANAGE':True},'acl':[]}
server.reads=[];server.writes=[];server.board_delete_error=0;server.reject_board_delete=False;server.avatar_reads=0
try:
 with tempfile.TemporaryDirectory() as directory:
  store=Store(directory);store.set_setting('auto_sync',False);store.set_setting('startup_sidebar',True)
  shared={'id':2,'title':'Compartit','owner':USERS[1],'permissions':{'PERMISSION_MANAGE':True}}
  store.put('snapshot',{'boards':[copy.deepcopy(server.board),shared], 'stacks':{'1':[{'id':10,'title':'Columna','cards':[]}],'2':[{'id':20,'title':'Conservada','cards':[]}]}})
  store.put('profile',dict(USERS[0],account='test'))
  window=Window(app,store,True);window.set_default_size(1100,900);window.present();settle()
  api=Deck(SimpleNamespace(server=f'http://127.0.0.1:{server.server_port}',username='login@example.invalid',password='dummy',goa_id='test'),allow_local=True)
  window.engine.api=api;window.account=SimpleNamespace(username='login@example.invalid',goa_id='test',server=api.server);window.render();settle()
  own,other=[window.board_list.get_row_at_index(i).get_child() for i in range(2)]
  assert any(isinstance(w,Gtk.Button) and w.get_tooltip_text()=='Esborra el tauler' for w in children(own))
  assert not any(isinstance(w,Gtk.Button) for w in children(other))
  trash=own.get_last_child();trash.grab_focus();settle();assert trash.has_focus()
  assert trash.has_css_class('destructive-action')
  trash.emit('clicked');settle();dialog=window.get_visible_dialog()
  assert isinstance(dialog,BoardDeletionDialog) and dialog.action.get_sensitive()
  wait_presented(dialog)
  assert dialog.cancel_button.has_focus() and dialog.get_default_widget() is dialog.cancel_button
  dialog.cancel_button.emit('clicked');settle(lambda:window.get_visible_dialog() is None)
  assert not server.writes
  operation=store.enqueue('update',{'board_id':1,'stack_id':10,'card_id':99,'changes':{'title':'Keep'}})
  dialog=BoardDeletionDialog(window,server.board);present(dialog,window)
  assert not dialog.action.get_sensitive() and dialog.status.get_visible()
  dialog.start();assert not dialog.started and not server.writes
  dialog.force_close();store.discard(operation);settle()
  window.demo=False
  server.board_delete_error=403
  dialog=BoardDeletionDialog(window,server.board);present(dialog,window);dialog.start()
  settle(lambda:not dialog.get_mapped());settle()
  assert len(store.view()['boards'])==2 and not server.board.get('deletedAt')
  window.get_visible_dialog().force_close();settle()
  server.board_delete_error=0
  draft=store.enqueue('update',{'board_id':2,'stack_id':20,'card_id':200,'changes':{'title':'Unrelated draft'}})
  dialog=BoardDeletionDialog(window,server.board);present(dialog,window);dialog.start()
  settle(lambda:not dialog.get_mapped());settle()
  assert server.board['deletedAt'] and [b['id'] for b in store.view()['boards']]==[2]
  assert [o['id'] for o in store.operations()]==[draft] and window.board_id==2
  window.close();settle()
finally:
 server.shutdown();server.server_close()
print('PASS owner-only sidebar trash, cancel, pending guard, server denial and confirmed scoped deletion')
