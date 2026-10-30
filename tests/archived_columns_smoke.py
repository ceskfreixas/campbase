# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Column archive visibility and explicit deletion use only synthetic cards."""
import gi
gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
from gi.repository import Adw,Gtk,Gdk,GLib
import copy,http.server,tempfile,threading,time
from pathlib import Path
from types import SimpleNamespace
from test_sync import Fixture
from campbase.storage import Store
from campbase.window import Window
from campbase.deck import Deck
from campbase.dialogs import ColumnColorDialog,TextDialog
from campbase.card_dialog import CardDialog
from campbase.card_deletion import CardDeletionDialog
from campbase.choosers import ColorChooser
from campbase.widgets import Column,Card
from campbase.archived_cards import ArchivedCards

def settle(until=None):
 end=time.monotonic()+(5 if until else .25)
 while time.monotonic()<end:
  while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
  if until and until():return
  time.sleep(.005)
 if until:assert until(),'Synthetic operation timed out'

def descendants(widget):
 yield widget
 child=widget.get_first_child()
 while child:
  yield from descendants(child);child=child.get_next_sibling()

app=Adw.Application(application_id='cat.ceskfreixas.Campbase.ArchiveCheck');app.register(None)
css=Gtk.CssProvider();css.load_from_path(str(Path.cwd()/'campbase/style.css'))
Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Fixture)
threading.Thread(target=server.serve_forever,daemon=True).start()
server.board={'id':1,'title':'Equip de prova','owner':{'uid':'test','displayname':'Test'},'labels':[],
              'permissions':{'PERMISSION_EDIT':True,'PERMISSION_MANAGE':True}}
server.cards={index:{'id':index,'stackId':10 if index<190 else 20,'boardId':1,'title':f'Targeta {index}',
                     'description':'','labels':[],'assignedUsers':[],'archived':index not in [99,199],
                     'deletedAt':0} for index in [99,100,101,199,200]}
server.reads=[];server.writes=[];server.delete_errors={};server.reject_delete=False
try:
 with tempfile.TemporaryDirectory() as directory:
  store=Store(directory);store.set_setting('auto_sync',False)
  store.put('snapshot',{'boards':[copy.deepcopy(server.board)],'stacks':{'1':[
      {'id':sid,'title':title,'cards':[copy.deepcopy(c) for c in server.cards.values() if c['stackId']==sid]}
      for sid,title in [(10,'Primera'),(20,'Segona')]]}})
  window=Window(app,store,True);window.set_default_size(1100,900);window.present();settle()
  api=Deck(SimpleNamespace(server=f'http://127.0.0.1:{server.server_port}',username='test',password='dummy'),allow_local=True)
  window.engine.api=api
  assert not hasattr(window,'archive_toggle')
  assert [c['id'] for c in window.filtered_cards(window.stacks()[0])]==[99]
  window.show_archived(10,True);settle()
  assert [c['id'] for c in window.filtered_cards(window.stacks()[0])]==[99,100,101]
  assert [c['id'] for c in window.filtered_cards(window.stacks()[1])]==[199]
  assert Store(directory).settings()['archived_overrides']=={'10':True}
  archived=next(w for w in descendants(window) if isinstance(w,Card) and w.card['id']==100)
  assert archived.has_css_class('card-archived') and archived.drag is None
  section=next(w for w in descendants(window) if isinstance(w,ArchivedCards))
  assert isinstance(section.get_first_child(),Gtk.Separator)
  assert len(section.cards)==2 and all(tile.delete_button is not None for tile in section.cards)
  for tile in section.cards:
   actions=tile.restore_button.get_parent()
   assert actions.get_first_child() is tile.restore_button and actions.get_last_child() is tile.delete_button
   assert tile.restore_button.get_tooltip_text()=='Restaura la targeta'
   assert tile.delete_button.has_css_class('destructive-action')
   assert not tile.restore_button.has_css_class('destructive-action')
  column=next(w for w in descendants(window) if isinstance(w,Column) and w.stack['id']==10)
  assert [w.card['id'] for w in column.drop.widgets]==[99]
  menu=column.get_first_child().get_last_child();menu.popup();settle()
  actions=[w.get_text() for w in descendants(menu.get_popover()) if isinstance(w,Gtk.Label)]
  assert 'Canvia el nom' in actions and 'Canvia el color' in actions and 'Amaga les arxivades' in actions
  assert 'Esborra les targetes arxivades' not in actions
  assert not any(isinstance(w,Gtk.CheckButton) for w in descendants(menu.get_popover()))
  assert menu.get_popover().get_child().has_focus()
  assert not any(w.get_state_flags() & Gtk.StateFlags.SELECTED for w in descendants(menu.get_popover()))
  menu.get_popover().popdown();settle()
  stack=window.stacks()[0]
  rename=window.edit_column(stack);settle()
  assert isinstance(rename,TextDialog) and not any(isinstance(w,ColorChooser) for w in descendants(rename))
  rename.entry.set_text('No es desarà');rename.force_close();settle()
  colors=window.edit_column_color(stack);settle()
  assert isinstance(colors,ColumnColorDialog) and not any(isinstance(w,Gtk.Entry) for w in descendants(colors))
  colors.color.buttons['#e01b24'].set_active(True);colors.force_close();settle()
  assert not store.settings().get('colors')
  colors=window.edit_column_color(stack);settle(lambda:colors.get_mapped());settle()
  colors.color.buttons['#e01b24'].set_active(True)
  colors.save_button.emit('clicked');settle(lambda:window.get_visible_dialog() is None);settle()
  assert store.settings()['colors']['10']=='#e01b24' and not server.writes
  # Restoring uses the same offline-safe archive queue as the card editor.
  section=next(w for w in descendants(window) if isinstance(w,ArchivedCards))
  section.cards[0].restore_button.emit('clicked');settle()
  operation=store.operations()[0]
  assert operation['kind']=='archive' and operation['payload']['card_id']==100
  assert operation['payload']['changes']=={'archived':False} and operation['payload']['base']=={'archived':True}
  assert not window.find_card(100)['archived']
  assert window.get_visible_dialog() is None
  assert not server.writes
  column=next(w for w in descendants(window) if isinstance(w,Column) and w.stack['id']==10)
  assert [w.card['id'] for w in column.drop.widgets]==[99,100]
  store.discard(operation['id']);window.render();settle()
  cancel=window.delete_archived_cards(stack);settle();assert not cancel.started
  cancel.force_close();settle();assert not server.writes
  operation=store.enqueue('update',{'board_id':1,'card_id':100,'stack_id':10,'changes':{'title':'Draft'}})
  blocked=window.delete_archived_cards(stack);settle();assert not blocked.action.get_sensitive()
  blocked.start();assert not blocked.started and not server.writes
  blocked.force_close();store.discard(operation);settle()
  draft=store.enqueue('update',{'board_id':1,'card_id':199,'stack_id':20,'changes':{'title':'Esborrany conservat'}})
  window.demo=False
  batch=window.delete_archived_cards(stack);settle();batch.action.emit('clicked')
  settle(lambda:not batch.get_mapped());settle()
  assert server.cards[100]['deletedAt'] and server.cards[101]['deletedAt']
  assert not server.cards[99]['deletedAt'] and not server.cards[200]['deletedAt']
  assert [operation['id'] for operation in store.operations()]==[draft]
  assert [c['id'] for c in window.filtered_cards(window.stacks()[0])]==[99]
  window.show_archived(20,True);settle()
  dialog=window.open_card(window.find_card(200));settle()
  assert isinstance(dialog,CardDialog)
  button=next(w for w in descendants(dialog) if isinstance(w,Gtk.Button) and w.get_label()=='Esborra la targeta')
  button.emit('clicked');settle()
  single=window.get_visible_dialog();assert isinstance(single,CardDeletionDialog) and len(single.cards)==1
  single.action.emit('clicked');settle(lambda:server.cards[200]['deletedAt']>0)
  settle(lambda:window.get_visible_dialog() is None);settle()
  assert window.get_visible_dialog() is None
  assert store.operations()[0]['payload']['changes']['title']=='Esborrany conservat'
  assert len(server.writes)==3 and all(body.get('delete') for _,body in server.writes)
  window.close();settle()
finally:
 server.shutdown();server.server_close()
print('PASS separate column actions, per-column archives, safe individual/bulk deletion and preserved unrelated drafts')
