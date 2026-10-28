# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Only an author's comment exposes deletion; failures preserve text and drafts."""
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
from campbase.updates import entries

def settle(until=None):
 end=time.monotonic()+(5 if until else .25)
 while time.monotonic()<end:
  while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
  if until and until():return
  time.sleep(.005)
 if until:assert until(),'Synthetic response timed out'

def descendants(widget):
 yield widget
 child=widget.get_first_child()
 while child:
  yield from descendants(child);child=child.get_next_sibling()

app=Adw.Application(application_id='cat.cesk.Campbase.CommentDeletionCheck');app.register(None)
css=Gtk.CssProvider();css.load_from_path(str(Path.cwd()/'campbase/style.css'))
Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Fixture)
threading.Thread(target=server.serve_forever,daemon=True).start()
server.board={'id':1,'title':'Prova','owner':USERS[0],'users':USERS,'acl':[], 'permissions':{'PERMISSION_EDIT':True}}
card={'id':99,'boardId':1,'stackId':10,'title':'Prova','description':'','labels':[],'assignedUsers':[]}
server.comments=[{'id':'1','actorId':'alice','actorType':'users','message':'El meu comentari'},
                 {'id':'2','actorId':'bob','actorType':'users','message':'Comentari de Robert'},
                 {'id':'3','actorId':'alice','actorType':'system','message':'Avís de sistema'}]
server.reads=[];server.writes=[];server.avatar_reads=0;server.comment_delete_error=0;server.no_activity=False;server.dismiss_error=0
try:
 with tempfile.TemporaryDirectory() as directory:
  store=Store(directory);store.set_setting('auto_sync',False)
  store.put('snapshot',{'boards':[server.board],'stacks':{'1':[{'id':10,'title':'Primera','cards':[card]}]}})
  store.put('profile',{'account':'test',**USERS[0]})
  window=Window(app,store,True);window.present();settle()
  api=Deck(SimpleNamespace(server=f'http://127.0.0.1:{server.server_port}',username='login@example.invalid',password='dummy',goa_id='test'),allow_local=True)
  window.engine.api=api;window.account=SimpleNamespace(username='login@example.invalid',goa_id='test',server=api.server)
  window.demo=False
  draft=store.enqueue('update',{'board_id':1,'stack_id':10,'card_id':99,'changes':{'title':'Esborrany'}})
  window.render();dialog=window.open_card(window.find_card(99));panel=dialog.comments
  settle(lambda:panel.state.get_visible_child_name()=='comments');settle()
  assert store.view()['stacks']['1'][0]['cards'][0]['commentsCount']==3
  buttons=[w for w in descendants(panel.comments) if isinstance(w,Gtk.Button) and w.get_tooltip_text()=='Esborra el comentari']
  assert len(buttons)==1
  own=copy.deepcopy(server.comments[0]);other=server.comments[1]
  assert panel.confirm_delete(other) is None
  prompt=panel.confirm_delete(own);settle()
  assert prompt.get_default_response()=='cancel'
  prompt.force_close();settle();assert not server.writes
  panel.entry.set_text('Esborrany de comentari conservat')
  for comment_id in ['1','2']:
   store.record_notice({'key':f'local:comment:99:{comment_id}','event':'own-comment','board_id':1,'card_id':99,'title':'Prova'})
  server.comment_delete_error=503
  panel.delete_comment(own);settle(lambda:not panel.deleting);settle()
  assert len(server.comments)==3 and len(entries(store))==2
  assert panel.entry.get_text()=='Esborrany de comentari conservat'
  error=window.get_visible_dialog();assert isinstance(error,Adw.AlertDialog);error.force_close();settle()
  server.comment_delete_error=0
  prompt=panel.confirm_delete(own);settle();prompt.emit('response','delete')
  settle(lambda:not panel.deleting and len(server.comments)==2);settle()
  assert [row['id'] for row in server.comments]==['2','3']
  assert not any(isinstance(w,Gtk.Button) and w.get_tooltip_text()=='Esborra el comentari'
                 for w in descendants(panel.comments))
  assert panel.entry.get_text()=='Esborrany de comentari conservat'
  assert [row['key'] for row in entries(store)]==['local:comment:99:2']
  assert store.operations()[0]['id']==draft
  assert store.view()['stacks']['1'][0]['cards'][0]['commentsCount']==2
  # A full page or a targeted older page is not a total comment count.
  store.comment_count(1,99,count=120)
  panel.target={'comment_id':'old'};panel.display([other],None)
  assert store.view()['stacks']['1'][0]['cards'][0]['commentsCount']==120
  panel.target={};panel.display([dict(other,id=str(index)) for index in range(50)],None)
  assert store.view()['stacks']['1'][0]['cards'][0]['commentsCount']==120
  dialog.force_close();window.close();settle()
finally:
 server.shutdown();server.server_close()
print('PASS author-only comment deletion, confirmation, failed deletion and preserved comment/card drafts')
