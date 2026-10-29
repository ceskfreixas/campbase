# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Native Talk dialogs against synthetic users only, including ambiguous sends."""
import copy,time,tempfile
from types import SimpleNamespace
import gi
gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
from gi.repository import Adw,Gtk,GLib,Gdk
from pathlib import Path
from campbase import i18n
from campbase.storage import Store
from campbase.window import Window
from campbase.deck import OfflineError
from campbase.collaboration import CollaborationAPI
from campbase.chat import ChatDialog
from campbase.conversations import ConversationsDialog
from campbase.sharing import SharingDialog
from urllib.parse import urlsplit,parse_qs

class API(CollaborationAPI):
    server='https://cloud.example';goa_id='test';username='alice'
    def __init__(self):
        self.writes=[];self.reject=False
        self.board={'id':1,'title':'Equip','owner':{'uid':'alice','displayname':'Alícia'},'users':[{'uid':'bob','displayname':'Robert'}],
                    'acl':[],'permissions':{'PERMISSION_SHARE':True,'PERMISSION_MANAGE':True}}
        self.room={'token':'room123','type':2,'displayName':'Equip','description':self.server+'/index.php/apps/deck/board/1'}
        self.messages=[{'id':1,'actorType':'users','actorId':'bob','actorDisplayName':'Robert','timestamp':1793270000,'message':'Hola'}]
    def profile(self):return {'uid':'alice','displayname':'Alícia'}
    def check_board(self,_id):return copy.deepcopy(self.board)
    def request(self,method,path,body=None,**kwargs):
        if method!='GET':self.writes.append((method,path,body))
        if path.startswith('/capabilities'):time.sleep(getattr(self,'load_delay',0));return {'capabilities':{'deck':{'version':'1.18.6'},'spreed':{'features':['conversation-v4','room-description']}}}
        if path=='/config':return {'federationEnabled':True}
        if method=='POST' and path.endswith('/acl'):raise OfflineError('Synthetic interrupted invitation')
        if path.startswith('/room?'):return [self.room]
        if path.startswith('/room/room123?'):return self.room
        if path.endswith('/participants'):return [{'actorType':'users','actorId':'alice','displayName':'Alícia'},{'actorType':'users','actorId':'bob','displayName':'Robert'}]
        if path.endswith('/read'):return {}
        if path.startswith('/chat/'):
            if method=='POST':
                if not self.reject:self.messages.append({'id':len(self.messages)+1,'actorType':'users','actorId':'alice','actorDisplayName':'Alícia','timestamp':1793270001,'message':body['message'],'referenceId':body['referenceId']})
                raise OfflineError('Synthetic interrupted response')
            after=int(parse_qs(urlsplit(path).query).get('lastKnownMessageId',['0'])[0])
            return [copy.deepcopy(m) for m in self.messages if m['id']>after]
        return {}

app=Adw.Application(application_id='cat.cesk.Campbase.TalkCheck');app.register(None)
theme=Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
icon_root=Path('/app/share/icons') if Path('/app/share/campbase/campbase/talk.py').exists() else Path.cwd()/'data/icons'
theme.add_search_path(str(icon_root))
assert theme.has_icon('cat.cesk.Campbase-conversations-symbolic')
def settle(until=lambda:True):
    limit=time.monotonic()+6
    while time.monotonic()<limit:
        while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
        if until():return
        time.sleep(.01)
    assert until(),'Synthetic Talk operation timed out'

with tempfile.TemporaryDirectory() as directory:
    store=Store(directory);store.set_setting('auto_sync',False)
    api=API();store.put('snapshot',{'boards':[api.board],'stacks':{'1':[]}})
    window=Window(app,store,True);window.present();settle()
    window.engine.api=api;window.account=SimpleNamespace(server=api.server,username='alice',goa_id='test');window.demo=False
    api.load_delay=.2
    inbox=ConversationsDialog(window,api.board);inbox.present(window)
    assert inbox.loading.get_visible() and inbox.spinner.get_spinning()
    assert not inbox.refresh_button.get_sensitive() and not inbox.groups.get_visible()
    settle(lambda:len(inbox.rows)>0)
    assert not inbox.loading.get_visible() and not inbox.spinner.get_spinning()
    assert inbox.refresh_button.get_sensitive()
    api.load_delay=0
    inbox.loaded(None,'Synthetic connection error')
    assert not inbox.loading.get_visible() and inbox.refresh_button.get_sensitive()
    inbox.set_status('')
    def layout():
        end=time.monotonic()+.25
        while time.monotonic()<end:
            while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
            time.sleep(.005)
    layout();short_height=inbox.content_box.get_height()
    assert inbox.get_follows_content_size() and not inbox.status.get_visible()
    visible=[inbox.groups,inbox.people,inbox.inbox]
    last=next(group for group in reversed(visible) if group.get_visible())
    ok,bounds=last.compute_bounds(inbox.content_box);assert ok
    assert abs(inbox.content_box.get_height()-bounds.origin.y-bounds.size.height-24)<2
    many=[api.room]+[{'token':'synthetic'+str(i),'type':2,'displayName':'Synthetic group '+str(i)} for i in range(20)]
    inbox.loaded((api.board,api.profile(),many),None);layout()
    assert inbox.content_box.get_height()>short_height
    adjustment=inbox.scroller.get_vadjustment()
    assert adjustment.get_upper()>adjustment.get_page_size()
    adjustment.set_value(adjustment.get_upper()-adjustment.get_page_size());layout()
    ok,bounds=inbox.inbox.compute_bounds(inbox.content_box);assert ok
    assert abs(inbox.content_box.get_height()-bounds.origin.y-bounds.size.height-24)<2
    inbox.loaded((api.board,api.profile(),[api.room]),None);layout()
    assert inbox.content_box.get_height()==short_height
    assert not api.writes,'Opening conversations must never invite anyone'
    chat=ChatDialog(window,api.room);chat.present(inbox)
    assert chat.get_title()=='Equip'
    settle(lambda:chat.after==1 and not chat.worker.busy)
    first_row=chat.message_rows[1]
    assert 'Robert' in chat.participant_label.get_text()
    settle(lambda:not chat.writer.busy)
    acknowledgements=len([w for w in api.writes if w[1].endswith('/read')])
    for _ in range(2):
        chat.refresh();settle(lambda:not chat.worker.busy and not chat.writer.busy)
    assert len([w for w in api.writes if w[1].endswith('/read')])==acknowledgements
    chat.entry.set_text('Esborrany')
    for language in ('en','es','gl','eu','oc','ca'):
        i18n.change_language(language);settle()
        assert chat.entry.get_text()=='Esborrany'
    # Sending must not wait for a background poll to finish.
    assert chat.worker.run(lambda:time.sleep(.4),lambda *_:None)
    chat.send();settle(lambda:len(api.messages)==2)
    assert chat.worker.busy,'The independent send should finish before the slow reader'
    settle(lambda:not chat.worker.busy);chat.refresh()
    settle(lambda:not chat.pending and not chat.worker.busy)
    assert chat.entry.get_text()=='' and len([w for w in api.writes if w[1]=='/chat/room123'])==1
    assert chat.message_rows[1] is first_row,'Unchanged chat rows must not be rebuilt'
    api.reject=True
    chat.entry.set_text('No s’ha enviat');chat.send();settle(lambda:chat.review_button.get_visible())
    settle(lambda:not chat.worker.busy)
    chat.refresh();settle(lambda:not chat.worker.busy)
    assert chat.pending and not chat.send_button.get_sensitive()
    pending=chat.pending;chat.force_close();settle()
    assert chat.worker.closed and chat.writer.closed and chat.timer==0
    reopened=ChatDialog(window,api.room);reopened.present(inbox)
    settle(lambda:reopened.after==2 and not reopened.worker.busy)
    assert reopened.pending==pending and reopened.entry.get_text()=='No s’ha enviat'
    assert not reopened.send_button.get_sensitive()
    reopened.add_messages([{'id':100,'systemMessage':'message_deleted','parent':{'id':1,'messageType':'comment_deleted'}}])
    assert 1 not in reopened.messages and 1 not in reopened.message_rows
    reopened.add_messages([{'id':i,'message':'Synthetic history','timestamp':1793270000} for i in range(1000,1600)])
    assert len(reopened.messages)==len(reopened.message_rows)==500
    reopened.force_close();inbox.force_close();settle()
    sharing=SharingDialog(window,api.board);sharing.present(window);settle(lambda:not sharing.busy)
    assert sharing.remote_group.get_sensitive() and sharing.remote.get_text()==''
    sharing.remote.set_text('bob@remote.example');sharing.invite_remote();settle(lambda:not sharing.busy)
    assert store.get(sharing.invitation_key('bob@remote.example')) is True
    invites=len([w for w in api.writes if w[1].endswith('/acl')])
    sharing.invite_remote();settle()
    assert len([w for w in api.writes if w[1].endswith('/acl')])==invites==1
    sharing.force_close();settle()
    window.query='keep filter'
    window.open_update({'app':'spreed','object_type':'chat','object_id':'room123/1'})
    settle(lambda:isinstance(window.get_visible_dialog(),ChatDialog))
    notification_chat=window.get_visible_dialog()
    assert notification_chat.room['token']=='room123' and window.query=='keep filter'
    notification_chat.force_close();window.engine.close();window.destroy();settle()
print('PASS native Talk: explicit invitations, live six-language drafts, lost-response confirmation, durable uncertain delivery and dialog cancellation')
