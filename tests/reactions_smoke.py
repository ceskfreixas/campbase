# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Shared emoji replies, own-reaction removal and direct notification navigation."""
import copy, http.server, tempfile, threading, time
from types import SimpleNamespace
import gi
gi.require_version('Gtk', '4.0');gi.require_version('Adw', '1')
from gi.repository import Adw, Gtk, GLib
from test_collaboration import Fixture, USERS
from campbase.storage import Store
from campbase.window import Window
from campbase.deck import Deck, OfflineError
from campbase.comment_reactions import group_comments
from campbase.reaction_widgets import react

app=Adw.Application(application_id='cat.cesk.Campbase.ReactionCheck');app.register(None)
def settle(until=lambda:True):
    end=time.monotonic()+5
    while time.monotonic()<end:
        while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
        if until():
            time.sleep(.02)
            while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
            return
        time.sleep(.005)
    assert until(), 'Synthetic response timed out'

server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Fixture)
threading.Thread(target=server.serve_forever,daemon=True).start()
server.board={'id':1,'title':'Equip','owner':USERS[0],'users':USERS,'acl':[]}
server.card={'id':99,'boardId':1,'stackId':10,'title':'Prova','description':'','commentsCount':2}
server.comments=[{'id':'1','actorId':'bob','actorDisplayName':'Robert','actorType':'users','message':'Proposta'},
                 {'id':'2','actorId':'alice','actorDisplayName':'Alícia','actorType':'users','message':'Resposta'}]
server.reads=[];server.writes=[];server.avatar_reads=0;server.comment_delete_error=0
try:
    with tempfile.TemporaryDirectory() as directory:
        store=Store(directory);store.set_setting('auto_sync',False)
        store.put('snapshot',{'boards':[server.board],'stacks':{'1':[{'id':10,'title':'Columna','cards':[server.card]}]}})
        store.put('profile',{'account':'test',**USERS[0]})
        window=Window(app,store,True);window.present();settle()
        api=Deck(SimpleNamespace(server=f'http://127.0.0.1:{server.server_port}',username='test',password='dummy',goa_id='test'),allow_local=True)
        window.engine.api=api;window.account=SimpleNamespace(username='test',goa_id='test',server=api.server);window.demo=False
        dialog=window.open_card(window.find_card(99));panel=dialog.comments
        settle(lambda:panel.state.get_visible_child_name()=='comments')
        own_controls=panel.comments.get_last_child().get_first_child().get_last_child()
        assert isinstance(own_controls.get_first_child(),Gtk.Button)
        assert isinstance(own_controls.get_last_child(),Gtk.MenuButton)
        panel.entry.set_text('Esborrany conservat')
        parent=copy.deepcopy(server.comments[0])
        react(panel,parent,'👍',[])
        settle(lambda:not panel.reacting and panel.state.get_visible_child_name()=='comments')
        assert len(server.comments)==3
        reply=server.comments[-1]
        assert reply['message']=='👍 @bob' and reply['replyTo']['id']=='1'
        assert len(group_comments(server.comments)[0])==2
        assert store.view()['stacks']['1'][0]['cards'][0]['commentsCount']==3
        target={'section':'comments','comment_id':str(reply['id'])}
        panel.target=target;panel.display(server.comments,None)
        assert panel.target_widget is panel.comments.get_first_child()
        react(panel,parent,'👍',[reply])
        settle(lambda:not panel.reacting and len(server.comments)==2 and panel.state.get_visible_child_name()=='comments')
        assert all(item['message'] in ('Proposta','Resposta') for item in server.comments)
        # A lost POST reply is read back; it is never blindly repeated.
        request=api.request
        def lose_response(method,path,*args,**kwargs):
            result=request(method,path,*args,**kwargs)
            if method=='POST':raise OfflineError('Synthetic lost response')
            return result
        api.request=lose_response;panel.target={}
        react(panel,parent,'❤️',[])
        settle(lambda:not panel.reacting and len(server.comments)==3)
        api.request=request
        settle(lambda:panel.state.get_visible_child_name()=='comments')
        assert panel.entry.get_text()=='Esborrany conservat'
        assert sum(method=='POST' for method,_,_ in server.writes)==2
        assert len(group_comments(server.comments)[0])==2
        visible=window.get_visible_dialog()
        if visible is not dialog:visible.force_close()
        dialog.force_close();window.close()
finally:
    server.shutdown();server.server_close()
print('PASS grouped emoji replies, mentions, own toggle, notification target and lost-response recovery')
