# SPDX-License-Identifier: GPL-3.0-or-later
"""Card details bypass a blocked sync worker and reuse account-scoped previews."""
import copy
import tempfile
import threading
import time
from types import SimpleNamespace
import gi
gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
from gi.repository import Adw, GLib
from campbase.deck import Deck
from campbase.storage import Store
from campbase.window import Window
from campbase.card_dialog import CardDialog


def settle(until=None):
    end=time.monotonic()+(4 if until else .2)
    while time.monotonic()<end:
        while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
        if until and until():return
        time.sleep(.005)
    if until:assert until()


class API(Deck):
    def __init__(self):
        super().__init__(SimpleNamespace(server='https://example.invalid',username='test',password='dummy',goa_id='fixture'))
        self.card={'id':1,'stackId':10,'boardId':1,'title':'Source','description':'',
                   'dependentCards':[2],'commentsCount':1,'labels':[],'assignedUsers':[]}
        self.rows=[{'id':'1','message':'Visible comment','actorType':'users','actorId':'','actorDisplayName':'Test'}]
        self.block_comments=False;self.comments_entered=threading.Event();self.release_comments=threading.Event()
        self.reads=[];self.fetches=0
    def get_card(self,*_):
        self.reads.append('dependencies');time.sleep(.1)
        return copy.deepcopy(self.card)
    def comments(self,*args,**kwargs):
        self.reads.append('comments');self.comments_entered.set()
        if self.block_comments:self.release_comments.wait(3)
        else:time.sleep(.1)
        return copy.deepcopy(self.rows)
    def attachments(self,*_):return []
    def fetch(self,**_):
        self.fetches+=1
        raise AssertionError('No workspace reload is needed')


app=Adw.Application(application_id='cat.ceskfreixas.Campbase.DetailLoadingCheck');app.register(None)
with tempfile.TemporaryDirectory() as folder:
    store=Store(folder);store.set_setting('auto_sync',False)
    api=API()
    store.put('snapshot',{'boards':[{'id':1,'title':'Board','permissions':{'PERMISSION_EDIT':True}}],
                         'stacks':{'1':[{'id':10,'title':'Column','cards':[api.card,dict(api.card,id=2,title='Linked card',dependentCards=[],commentsCount=0)]}]}})
    window=Window(app,store,True);window.present();settle()
    window.demo=False;window.engine.api=api
    release=threading.Event();blocked=threading.Event()
    def block_sync():blocked.set();release.wait(5)
    hold=window.engine.executor.submit(block_sync)
    assert blocked.wait(1)
    try:
        editor=CardDialog(window,10,window.find_card(1));editor.present(window)
        assert editor.dependencies.rows.get_visible()
        assert editor.dependencies.rows.get_first_child().get_title()=='Linked card'
        settle(lambda:editor.comments.state.get_visible_child_name()=='comments' and not editor.dependencies.busy)
        assert not hold.done() and api.fetches==0
        assert api.reads.count('dependencies')==1 and api.reads.count('comments')==1
        editor.force_close();settle(lambda:editor.comments.reads.closed)
        api.block_comments=True;api.comments_entered.clear()
        editor=CardDialog(window,10,window.find_card(1));editor.present(window)
        assert editor.comments.state.get_visible_child_name()=='comments'
        assert editor.dependencies.rows.get_visible()
        settle(lambda:api.comments_entered.is_set())
        assert not hold.done()
        panel=editor.comments
        editor.force_close();settle(lambda:editor.comments.reads.closed)
        api.rows=[];api.release_comments.set();settle()
        assert panel.reads.closed
        assert store.view()['stacks']['1'][0]['cards'][0]['commentsCount']==1
    finally:
        release.set();api.release_comments.set()
        hold.result(timeout=2)
        window.close();settle()
print('PASS parallel card reads bypass busy sync, cached previews appear immediately and closed reads cannot alter counts')
