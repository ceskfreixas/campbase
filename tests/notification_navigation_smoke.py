# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Read-only notification navigation and mention styling against synthetic Deck."""
import gi
gi.require_version('Gtk', '4.0');gi.require_version('Adw', '1')
from gi.repository import Adw, Gdk, GLib, Gtk
import copy, http.server, tempfile, threading, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from test_collaboration import Fixture, USERS
from campbase.window import Window
from campbase.storage import Store
from campbase.deck import Deck
from campbase.card_dialog import CardDialog
from campbase.sharing import SharingDialog
from campbase.notifications import NotificationsDialog
from campbase.widgets import Card
from campbase.updates import entries


def settle(until=None):
    end=time.monotonic()+(5 if until else .25)
    while time.monotonic()<end:
        while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
        if until and until():return
        time.sleep(.005)
    if until:assert until(), 'Synthetic response timed out'


def descendants(widget):
    yield widget
    child=widget.get_first_child()
    while child:
        yield from descendants(child)
        child=child.get_next_sibling()


app=Adw.Application(application_id='cat.cesk.Campbase.NotificationNavigationCheck');app.register(None)
css=Gtk.CssProvider();css.load_from_path(str(Path.cwd()/'campbase/style.css'))
Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Fixture)
threading.Thread(target=server.serve_forever,daemon=True).start()
server.board={'id':1,'title':'Equip de prova','owner':USERS[0],'users':USERS,'acl':[],
              'permissions':{'PERMISSION_SHARE':True,'PERMISSION_EDIT':True,'PERMISSION_MANAGE':True}}
server.card={'id':99,'title':'Una targeta de prova','stackId':10,'boardId':1,'description':'Una descripció prou llarga.\n'*20,
             'labels':[],'owner':USERS[0],'assignedUsers':[],'duedate':None}
server.reads=[];server.writes=[];server.avatar_reads=0;server.board_delay=0
server.dismiss_error=0;server.no_activity=False
server.comments=[{'id':str(index),'message':f'Comentari {index}: @alice hola!','actorId':'bob','actorDisplayName':'Robert',
                  'creationDateTime':(datetime(2026,10,28,12,tzinfo=timezone.utc)+timedelta(seconds=index)).isoformat()}
                 for index in range(120,0,-1)]
try:
 with tempfile.TemporaryDirectory() as directory:
    store=Store(directory);store.set_setting('auto_sync',False)
    store.put('snapshot',{'boards':[copy.deepcopy(server.board)],'stacks':{'1':[{'id':10,'title':'Primera','cards':[copy.deepcopy(server.card)]}]}})
    window=Window(app,store,True);window.set_default_size(1100,900);window.present();settle()
    api=Deck(SimpleNamespace(server=f'http://127.0.0.1:{server.server_port}',username='alice',password='dummy',goa_id='test'),allow_local=True)
    window.engine.api=api
    participants=next(widget for widget in descendants(window) if widget.has_css_class('board-participants'))
    icons=list(descendants(participants))
    photos=[widget for widget in icons if isinstance(widget,Adw.Avatar)]
    assert len(photos)==3 and all(photo.get_tooltip_text() for photo in photos)
    assert not any(isinstance(widget,Gtk.Label) and widget.get_text()=='·' for widget in icons)
    details=next(widget for widget in descendants(window) if widget.has_css_class('board-details'))
    assert sum(isinstance(widget,Gtk.Label) and widget.get_text()=='·' for widget in descendants(details))==1
    assert 'Responsable' in photos[0].get_tooltip_text()

    # Pending indicators share the title center with avatars and wrapped titles.
    for blocked in [False,True]:
        for title in ['Títol curt', 'Un títol molt més llarg que ocuparà diverses línies en aquesta targeta']:
            card={**server.card,'title':title,'_pending':True,'_blocked':blocked,'assignedUsers':[{'participant':USERS[0]}]}
            tile=Card(card,window);tile.set_size_request(300,-1)
            bounded=Adw.Clamp(child=tile,maximum_size=300,tightening_threshold=300)
            window.board_body.append(bounded);settle()
            heading=tile.get_child().get_first_child();title_widget=heading.get_first_child();indicator=title_widget.get_next_sibling()
            title_widget.set_max_width_chars(24);tile.set_halign(Gtk.Align.START);settle()
            if title != 'Títol curt':
                assert title_widget.get_layout().get_line_count()>1
            ok,title_bounds=title_widget.compute_bounds(tile);assert ok
            ok,icon_bounds=indicator.compute_bounds(tile);assert ok
            assert abs(title_bounds.origin.y+title_bounds.size.height/2-icon_bounds.origin.y-icon_bounds.size.height/2)<1
            window.board_body.remove(bounded)

    window.demo=False
    window.query='a filter that hides this card'
    window.open_update({'event':'self-mentioned','key':'local:comment:99:6','board_id':1,'card_id':99})
    dialog=window.get_visible_dialog();assert isinstance(dialog,CardDialog)
    settle(lambda:dialog.comments.target_widget is not None);settle()
    assert not window.query and any('offset=100' in path for path in server.reads)
    target=dialog.comments.target_widget
    assert 'Comentari 6:' in target.get_last_child().get_text()
    assert 'foreground' in target.get_last_child().get_attributes().to_string()
    ok,bounds=target.compute_bounds(dialog.scroller);assert ok
    assert 0 <= bounds.origin.y < dialog.scroller.get_height()
    assert bounds.origin.y+bounds.size.height <= dialog.scroller.get_height()
    dialog.comments.entry.set_text('Sí, @alice.');settle()
    assert 'foreground' in dialog.comments.entry.get_attributes().to_string()
    assert dialog.comments.entry.get_text()=='Sí, @alice.'
    for scheme in [Adw.ColorScheme.FORCE_LIGHT,Adw.ColorScheme.FORCE_DARK]:
        Adw.StyleManager.get_default().set_color_scheme(scheme);settle()
        found,color=dialog.comments.entry.get_style_context().lookup_color('accent_color');assert found
        assert 'foreground' in dialog.comments.entry.get_attributes().to_string()
    dialog.force_close();settle()

    for section in ['assignees','due','labels','column','description']:
        window.open_update({'board_id':1,'card_id':99,'section':section})
        dialog=window.get_visible_dialog();assert isinstance(dialog,CardDialog);settle()
        assert dialog._focused_target is dialog.sections[section]
        ok,bounds=dialog._focused_target.compute_bounds(dialog.scroller);assert ok
        assert 0 <= bounds.origin.y < dialog.scroller.get_height()
        dialog.force_close();settle()
    window.open_update({'board_id':1,'section':'members'})
    share=window.get_visible_dialog();assert isinstance(share,SharingDialog)
    settle(lambda:not share.busy);settle()
    assert share.member_group.has_css_class('notification-target')
    share.force_close();settle()

    window.demo=True
    store.put('updates',{'notifications':[{'notification_id':1,'app':'deck','object_type':'card','object_id':'99',
        'subject':'Mention','message':'@alice hola!','subjectRichParameters':{
            'user':{'id':'bob','name':'Robert'},'deck-card':{'id':'99','name':'Targeta de prova'},
            'deck-board':{'id':'1','name':'Equip'}}}]})
    inbox=NotificationsDialog(window);inbox.present(window);settle()
    row=inbox.list.get_first_child()
    assert row.has_css_class('notification-row')
    body=next(widget for widget in descendants(row) if widget.has_css_class('notification-body'))
    assert 'foreground' in body.get_attributes().to_string()
    assert entries(store)[0]['section']=='comments'
    assert not server.writes
    inbox.force_close();settle()
    # Opening an uncached invitation refreshes through reads and keeps drafts.
    window.demo=False
    incoming={**server.board,'id':2,'title':'Un tauler acabat de compartir'}
    api.fetch=Mock(return_value={'boards':[incoming], 'stacks':{'2':[]}})
    api.check_board=Mock(return_value=incoming)
    store.enqueue('create',{'board_id':1,'stack_id':10,'title':'Esborrany sense enviar'})
    window.open_update({'board_id':2,'section':'members'})
    settle(lambda:isinstance(window.get_visible_dialog(),SharingDialog));settle()
    assert window.board_id==2 and store.operations()[0]['payload']['title']=='Esborrany sense enviar'
    assert not server.writes
    window.get_visible_dialog().force_close();window.close();settle()
finally:
 server.shutdown();server.server_close()
print('PASS mention colors, participant avatars, card icon centers and precise read-only notification destinations')
