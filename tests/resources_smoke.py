# SPDX-License-Identifier: GPL-3.0-or-later
"""Synthetic native workflows: attachments, labels, recovery and own Talk actions."""
import gi
gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
from gi.repository import Adw, Gtk, Gdk, Gio, GLib
import copy,time,tempfile
from pathlib import Path
from types import SimpleNamespace
from campbase.deck import Deck, OfflineError
from campbase.storage import Store
from campbase.window import Window
from campbase.card_dialog import CardDialog
from campbase.label_management import LabelManagerDialog,LabelEditDialog
from campbase.board_deletion import BoardDeletionDialog
from campbase.board_recovery import BoardRecoveryDialog,recovery_key
from campbase.chat import ChatDialog
from campbase.chat_actions import MessageEditDialog,confirm_delete


def settle(until=None):
    end=time.monotonic()+(8 if until else .3)
    while time.monotonic()<end:
        while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
        if until and until():return
        time.sleep(.005)
    if until:assert until(),'Synthetic resource request timed out'


def respond(window, choice):
    prompt=window.get_visible_dialog()
    assert isinstance(prompt,Adw.AlertDialog)
    prompt.emit('response',choice)
    prompt.force_close()
    settle()


class API(Deck):
    def __init__(self):
        super().__init__(SimpleNamespace(server='https://cloud.example.invalid',username='alice',password='dummy',goa_id='synthetic'))
        self.label={'id':4,'title':'Original','color':'3584e4'}
        self.board={'id':1,'title':'Synthetic board','owner':{'uid':'alice','displayname':'Alícia'},'users':[],
                    'labels':[self.label],'permissions':{'PERMISSION_READ':True,'PERMISSION_EDIT':True,'PERMISSION_MANAGE':True}}
        self.card={'id':99,'title':'Synthetic card','boardId':1,'stackId':10,'description':'','labels':[self.label],
                   'assignedUsers':[],'owner':self.board['owner'],'archived':False}
        self.snapshot={'boards':[self.board],'stacks':{'1':[{'id':10,'title':'Column','cards':[self.card]}]}}
        self.files=[];self.writes=[];self.lost_upload=False;self.lost_edit=False
        self.room={'token':'room123','displayName':'Synthetic chat','type':2}
        self.messages=[{'id':1,'actorType':'users','actorId':'bob','message':'Other message','timestamp':int(time.time())},
                       {'id':2,'actorType':'users','actorId':'alice','message':'Own message','timestamp':int(time.time())}]
    def profile(self):return {'uid':'alice','displayname':'Alícia'}
    def check_board(self,bid):return copy.deepcopy(self.board)
    def get_card(self,*args):return copy.deepcopy(self.card)
    def refresh_auth(self):pass
    def fetch(self,refresh_auth=True):
        return copy.deepcopy(self.snapshot if not self.board.get('deletedAt') else {'boards':[],'stacks':{}})
    def request(self,method,path,body=None,**kwargs):
        if method!='GET':self.writes.append((method,path,body))
        if path.startswith('/capabilities'):return {'capabilities':{'spreed':{'features':['conversation-v4','edit-messages','delete-messages','chat-get-context']}}}
        if path.endswith('/participants'):return [{'actorId':'alice','displayName':'Alícia'}]
        if path.endswith('/comments'):return []
        if '/comments?' in path:return []
        if '/attachments' in path:
            time.sleep(.05)
            if method=='GET':return copy.deepcopy(self.files)
            item={'id':len(self.files)+1,'type':'file','data':'Synthetic attachment.txt'};self.files.append(item)
            if self.lost_upload:raise OfflineError('Synthetic lost upload response')
            return item
        if '/labels/' in path:
            if method=='DELETE':self.board['labels']=[];self.card['labels']=[]
            else:self.label.update(body)
            return {}
        if path.endswith('/undo_delete'):self.board['deletedAt']=0;return self.board
        if method=='DELETE' and path=='/boards/1':self.board['deletedAt']=10;return copy.deepcopy(self.board)
        if path.startswith('/chat/'):
            if '/context?' in path:
                mid=int(path.split('/')[3]);return [copy.deepcopy(m) for m in self.messages if m['id']==mid]
            if path.endswith('/read'):return {}
            if method in ('PUT','DELETE'):
                mid=int(path.split('/')[3]);item=next(m for m in self.messages if m['id']==mid)
                item.update({'deleted':True} if method=='DELETE' else {'message':body['message']})
                if self.lost_edit:raise OfflineError('Synthetic lost edit response')
                return {'systemMessage':'message_deleted' if method=='DELETE' else 'message_edited','parent':copy.deepcopy(item)}
            return copy.deepcopy(self.messages)
        if path=='/boards/1':return copy.deepcopy(self.board)
        return {}


app=Adw.Application(application_id='cat.cesk.Campbase.ResourcesCheck');app.register(None)
provider=Gtk.CssProvider();provider.load_from_path(str(Path.cwd()/'campbase/style.css'))
Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).add_search_path(str(Path.cwd()/'data/icons'))
with tempfile.TemporaryDirectory() as directory:
    api=API();store=Store(directory);store.set_setting('auto_sync',False)
    store.put('snapshot',copy.deepcopy(api.snapshot));store.put('profile',{'uid':'alice','account':'synthetic'})
    store.put('board_metadata',{'1':{'icon':'folder-symbolic'}});store.set_setting('colors',{'10':'#ff0000'})
    window=Window(app,store,True);window.set_default_size(1100,1000);window.present();settle()
    window.engine.api=api;window.account=SimpleNamespace(server=api.server,username='alice',goa_id='synthetic');window.demo=False
    card=CardDialog(window,10,copy.deepcopy(api.card));card.present(window)
    settle(lambda:not card.attachments.worker.busy);settle()
    card.title_entry.set_text('Preserved card draft')
    local=Path(directory)/'attachment.txt';local.write_text('Synthetic content')
    panel=card.attachments;panel.upload(Gio.File.new_for_path(str(local)))
    assert not card.get_can_close()
    settle(lambda:not panel.worker.busy);settle()
    assert len(api.files)==1 and not store.get(panel.key)
    assert card.title_entry.get_text()=='Preserved card draft'
    api.lost_upload=True;panel.upload(Gio.File.new_for_path(str(local)))
    settle(lambda:not panel.worker.busy);assert store.get(panel.key)
    count=len(api.writes);panel.upload(Gio.File.new_for_path(str(local)));settle()
    assert len(api.writes)==count,'Uncertain uploads must never repeat automatically'
    prompt=window.get_visible_dialog();assert isinstance(prompt,Adw.AlertDialog)
    respond(window,'cancel')
    panel.load();settle(lambda:not panel.worker.busy)
    assert len(api.files)==2 and store.get(panel.key)
    manager=LabelManagerDialog(card.labels);manager.present(card);settle(lambda:not manager.busy)
    editor=LabelEditDialog(manager,api.label);editor.present(manager)
    editor.name.set_text('Renamed');editor.color.selected_color='#ff0000';editor.perform()
    settle(lambda:not editor.busy);settle()
    assert card.labels.labels[4]['title']=='Renamed'
    assert card.title_entry.get_text()=='Preserved card draft'
    editor=LabelEditDialog(manager,api.label);editor.present(manager)
    op=store.enqueue('update',{'board_id':1,'stack_id':10,'card_id':99,'changes':{'title':'Pending'}})
    editor.perform(delete=True);assert editor.status.get_visible() and not editor.busy
    store.discard(op);editor.confirm_delete();settle();respond(window,'cancel')
    assert api.board['labels']
    editor.perform(delete=True);settle(lambda:not editor.busy);settle()
    assert not card.labels.labels and not store.get('snapshot')['stacks']['1'][0]['cards'][0]['labels']
    manager.force_close();card.force_close();settle()
    deletion=BoardDeletionDialog(window,api.board);deletion.present(window);deletion.start()
    settle(lambda:not store.get('snapshot')['boards']);settle()
    assert window.get_visible_dialog() is None
    key=recovery_key(api,1);assert store.get(key) and not store.get('snapshot')['boards']
    recovery=BoardRecoveryDialog(window);recovery.present(window);recovery.start('missing-record')
    assert recovery.get_can_close() and recovery.form.get_sensitive()
    recovery.start(key)
    settle(lambda:recovery.get_can_close());settle()
    assert not store.get(key) and window.board_id==1
    assert store.get('board_metadata')['1']['icon']=='folder-symbolic'
    assert store.settings()['colors']['10']=='#ff0000'
    recovery.force_close();settle()
    chat=ChatDialog(window,api.room);chat.present(window)
    settle(lambda:len(chat.message_rows)==2 and not chat.worker.busy and not chat.writer.busy)
    assert len([w for w in api.writes if w[0]=='PUT' and w[1].startswith('/chat/')])==0
    editor=MessageEditDialog(chat,chat.messages[2]);editor.present(chat)
    api.lost_edit=True;editor.text.get_buffer().set_text('Edited message');editor.submit()
    settle(lambda:not editor.busy)
    assert editor.status.get_visible() and editor.text.get_editable()
    writes=len([w for w in api.writes if w[0]=='PUT' and w[1].startswith('/chat/')])
    api.lost_edit=False;editor.submit();settle(lambda:not editor.busy);settle()
    assert chat.messages[2]['message']=='Edited message'
    assert len([w for w in api.writes if w[0]=='PUT' and w[1].startswith('/chat/')])==writes
    confirm_delete(chat,chat.messages[2]);settle();respond(window,'cancel')
    assert 2 in chat.messages
    confirm_delete(chat,chat.messages[2]);settle();respond(window,'delete')
    settle(lambda:2 not in chat.messages and not chat.writer.busy)
    assert 1 in chat.messages,'Another user\'s message is preserved'
    chat.force_close();window.engine.close();window.destroy();settle()
print('PASS native attachments, lost-response guards, label permissions/drafts, durable board recovery and own Talk edit/delete')
