# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Native collaboration flows use only an isolated synthetic HTTP account."""
import gi
gi.require_version('Gtk', '4.0');gi.require_version('Adw', '1')
from gi.repository import Adw, Gdk, GLib, Gtk
import copy, tempfile, time, threading, http.server
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime
from test_collaboration import Fixture, USERS
from campbase.window import Window
from campbase.storage import Store
from campbase.deck import Deck
from campbase.sharing import SharingDialog
from campbase.notifications import NotificationsDialog
from campbase.card_dialog import CardDialog
from campbase.preferences import Preferences
from campbase.collaboration import assignment_ids, remember_creator
from campbase.people import author_text
from campbase import i18n
from campbase.updates import collect_updates, entries

app=Adw.Application(application_id='cat.cesk.Campbase.CollaborationCheck');app.register(None)
css=Gtk.CssProvider();css.load_from_path(str(Path.cwd()/'campbase/style.css'))
Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

def settle(until=None, duration=.15):
    end=time.monotonic()+(5 if until else duration)
    while time.monotonic()<end:
        while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
        if until and until():return
        time.sleep(.005)
    if until:assert until(), 'Timed out waiting for synthetic response'

def descendants(widget):
    yield widget
    child=widget.get_first_child()
    while child:
        yield from descendants(child)
        child=child.get_next_sibling()

server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Fixture)
threading.Thread(target=server.serve_forever,daemon=True).start()
server.board={'id':1,'title':'Comunitat de prova','owner':USERS[0],'users':[USERS[0]],'acl':[],
              'permissions':{'PERMISSION_READ':True,'PERMISSION_EDIT':True,'PERMISSION_MANAGE':True,'PERMISSION_SHARE':True}}
server.card={'id':99,'title':'Targeta de prova','description':'Descripció','stackId':10,'order':0,
             'labels':[],'owner':USERS[0],'assignedUsers':[],'duedate':None}
server.reads=[];server.writes=[];server.avatar_reads=0;server.comments=[];server.dismiss_error=0;server.reject_assignment=False;server.shift_time=False;server.no_activity=False
try:
 with tempfile.TemporaryDirectory() as directory:
    store=Store(directory)
    snapshot={'boards':[copy.deepcopy(server.board)], 'stacks':{'1':[{'id':10,'title':'Primera columna','cards':[copy.deepcopy(server.card)]},
                                                                  {'id':20,'title':'Segona columna amb un nom llarg','cards':[]},
                                                                  {'id':30,'title':'Fet','cards':[]}]}}
    store.put('snapshot',snapshot);store.set_setting('auto_sync',False);store.set_setting('columns_per_row',2)
    window=Window(app,store,True);window.set_default_size(1100,900);window.present();settle()
    api=Deck(SimpleNamespace(server=f'http://127.0.0.1:{server.server_port}',username='login@example.invalid',password='dummy',goa_id='test'),allow_local=True)
    window.engine.api=api
    window.account=SimpleNamespace(username='login@example.invalid',goa_id='test',server=api.server)
    collect_updates(api,store)
    assert store.get('profile')['uid']=='alice'
    window.render();settle()
    # Both sidebar representations use the same local project identity.
    for metadata, expected in [({'icon':'weather-clear-night-symbolic'}, 'weather-clear-night-symbolic'),
                               ({'icon':''}, 'view-grid-symbolic')]:
        store.put('board_metadata', {'1': metadata});window.render();settle()
        picture=window.board_list.get_row_at_index(0).get_child().get_first_child()
        assert picture.get_icon_name()==expected and picture.get_pixel_size()==20
    record=window.assets.import_bytes(Path('data/icons/cat.cesk.Campbase.svg').read_bytes(), 'Projecte.svg', icon=True)
    store.put('board_metadata', {'1': {'image':record['path']}});window.render();settle()
    picture=window.board_list.get_row_at_index(0).get_child().get_first_child()
    assert picture.get_gicon() and picture.get_icon_name() is None and picture.get_pixel_size()==20
    store.put('board_metadata', {});window.render();settle()
    identity=next(w for w in descendants(window) if w.has_css_class('board-identity'))
    actions=next(w for w in descendants(window) if w.has_css_class('board-actions'))
    details=next(w for w in descendants(window) if w.has_css_class('board-details'))
    assert actions.get_parent() is details.get_parent()
    ok,a=actions.compute_bounds(window);ok,b=details.compute_bounds(window)
    assert a.origin.y+a.size.height < b.origin.y
    ok,left=identity.compute_bounds(window);ok,right=actions.get_parent().compute_bounds(window)
    if hasattr(Adw,'WrapBox'):
        assert abs(left.origin.y+left.size.height/2-right.origin.y-right.size.height/2)<2
    else:
        # Adwaita 1.5 uses the documented vertical header fallback.
        assert left.origin.y+left.size.height <= right.origin.y
    prefs=Preferences(window);prefs.present(window);settle()
    rows=[w for w in descendants(prefs) if isinstance(w,Adw.ActionRow)]
    assert any(r.get_title()=='Alícia' and r.get_subtitle()=="Nom d'usuari: alice" for r in rows)
    assert any(isinstance(w,Adw.Avatar) for w in descendants(prefs))
    prefs.force_close();settle()
    assert 'Alícia' in author_text(window,'board',server.board)
    assert 'no consta' in author_text(window,'stack',{'id':20})
    remember_creator(store,'stack',20,USERS[1]);window.render();settle()
    assert 'Robert' in author_text(window,'stack',{'id':20})
    headers=[w for w in descendants(window) if w.has_css_class('column-header')]
    assert len(headers)==3 and all(isinstance(w,Gtk.Box) for w in headers)
    assert all(header.get_tooltip_text() is None for header in headers)
    for header in headers:
        color,title,count,menu=list(c for c in [header.get_first_child(),header.get_first_child().get_next_sibling(),header.get_last_child().get_prev_sibling(),header.get_last_child()])
        assert title.get_hexpand() and not color.get_hexpand() and not count.get_hexpand()
        assert color.get_width()<30 and count.get_width()<55 and menu.get_width()<55
    actions=next(w for w in descendants(window) if w.has_css_class('board-actions'))
    action=actions.get_first_child()
    while action:
        if isinstance(action,Gtk.Button):
            assert action.get_label() is None and action.get_tooltip_text()
        action=action.get_next_sibling()
    window.demo=False
    server.board_delay=.8
    share=SharingDialog(window,window.snapshot['boards'][0]);share.present(window);settle()
    loading_height=share.content_box.get_height()
    settle(lambda:not share.busy);settle()
    assert share.content_box.get_height()<loading_height
    server.board_delay=0
    window.demo=True
    content=share.content_box;ok,bounds=share.form.get_last_child().compute_bounds(content);assert ok
    assert abs(content.get_height()-bounds.origin.y-bounds.size.height-24)<2
    share.scroller.get_vadjustment().set_value(0);settle()
    ok,top=share.form.get_first_child().compute_bounds(content);assert ok
    assert abs(top.origin.y-content.get_first_child().get_height()-24)<2
    share.search.set_text('Robert');share.search_users();settle(lambda:not share.busy)
    settle()
    content=share.content_box;form=share.form
    scroll=content.get_last_child();adjustment=scroll.get_vadjustment()
    adjustment.set_value(adjustment.get_upper()-adjustment.get_page_size());settle()
    ok,bounds=form.get_last_child().compute_bounds(content);assert ok
    assert abs(content.get_height()-bounds.origin.y-bounds.size.height-24)<2
    line=share.results.get_first_child();assert line
    line.get_last_child().emit('clicked');settle(lambda:not share.busy)
    assert len(share.board['acl'])==1 and any(u['uid']=='bob' for u in window.snapshot['boards'][0]['users'])
    assert server.writes[-1][2]['participant']=='bob'
    member=share.rows[-1]
    for expanded in [True, False]:
        member.set_expanded(expanded);settle(duration=.5)
        content=share.content_box;scroll=content.get_last_child();adjustment=scroll.get_vadjustment()
        adjustment.set_value(adjustment.get_upper()-adjustment.get_page_size());settle()
        ok,bounds=share.form.get_last_child().compute_bounds(content);assert ok
        assert abs(content.get_height()-bounds.origin.y-bounds.size.height-24)<2
    share.set_status('Prova de connexió');settle()
    content=share.content_box;ok,bounds=share.form.get_last_child().compute_bounds(content);assert ok
    assert abs(content.get_height()-bounds.origin.y-bounds.size.height-24)<2
    share.force_close();settle()
    original_board = window.snapshot['boards'][0]
    solo_user = {'uid': 'alice', 'displayname': 'Alícia Miró'}
    window.snapshot['boards'][0] = {**original_board, 'owner': solo_user, 'users': [solo_user], 'acl': []}
    solo = CardDialog(window, 10);solo.present(window);settle()
    width = solo.assignees.get_width()
    solo.assignees.menu.popup();settle()
    name = solo.assignees.buttons['alice'].get_child().get_last_child()
    assert name.get_layout().get_line_count() == 1
    assert solo.assignees.popover.get_width() > solo.assignees.menu.get_width()
    assert solo.assignees.get_width() == width
    solo.assignees.buttons['alice'].set_active(True);settle()
    assert solo.assignees.get_width() == width
    solo.assignees.buttons['alice'].set_active(False);settle()
    assert solo.assignees.get_width() == width
    solo.force_close();settle()
    window.snapshot['boards'][0] = original_board
    card=window.find_card(99)
    editor=CardDialog(window,10,card);editor.present(window);settle()
    assert not editor.title_entry.has_css_class('title-3')
    assert not editor.due.time_row.get_visible()
    assert editor.assignees.get_parent() is editor.title_entry.get_parent().get_parent()
    editor.assignees.menu.popup();settle()
    assert editor.assignees.popover.get_mapped()
    editor.assignees.popover.popdown()
    editor.assignees.buttons['bob'].set_active(True)
    editor.due.choose('2027-02-03');editor.due.hour.set_value(22);editor.due.minute.set_value(5)
    assert editor.due.time_row.get_visible() and editor.due.minute.get_text()=='05'
    assert datetime.fromisoformat(editor.due.get_due()).astimezone().strftime('%Y-%m-%d %H:%M')=='2027-02-03 22:05'
    assert not editor.get_can_close()
    editor.comments.display([{'actorId':'bob','actorDisplayName':'Robert','message':'@"user/alice" mira-ho',
                             'creationDateTime':'2026-10-28T13:45:00Z','mentions':[{'mentionId':'alice','mentionDisplayName':'Alícia'}]}],None)
    labels=[w.get_text() for w in descendants(editor.comments) if isinstance(w,Gtk.Label)]
    assert 'Robert' in labels and any('@bob' in t and ':' in t for t in labels) and '@Alícia mira-ho' in labels
    assert any(isinstance(w,Adw.Avatar) for w in descendants(editor.comments))
    adjustment=editor.scroller.get_vadjustment()
    adjustment.set_value(adjustment.get_upper()-adjustment.get_page_size());settle()
    editor.comments.entry.grab_focus()
    editor.comments.entry.set_text('Hola, @');editor.comments.entry.set_position(-1);settle()
    completion=editor.comments.completion
    assert completion.popover and completion.popover.get_visible()
    pointed,rectangle=completion.popover.get_pointing_to();assert pointed
    strong,_weak=editor.comments.entry.get_delegate().compute_cursor_extents(editor.comments.entry.get_position())
    ok,point=editor.comments.entry.get_delegate().compute_point(editor.comments.entry,strong.get_top_left());assert ok
    assert abs(rectangle.x-point.x)<2
    assert completion.popover.get_position()==Gtk.PositionType.RIGHT
    assert not editor.comments.entry.get_selection_bounds()
    editor.comments.entry.set_text('Hola, @bo');editor.comments.entry.set_position(-1);settle()
    assert [user['uid'] for user in completion.matches] == ['bob']
    assert completion.key_pressed(None, Gdk.KEY_Return, 0, Gdk.ModifierType(0))
    assert editor.comments.entry.get_text() == 'Hola, @bob '
    assert not editor.comments.entry.get_selection_bounds()
    assert not completion.popover.get_visible()
    editor.comments.entry.set_text('Hola @bo');editor.comments.entry.set_position(-1)
    editor.comments.insert_mention('bob')
    assert editor.comments.entry.get_text()=='Hola @bob '
    for language in ['en','eu','gl','es','oc','ca']:
        i18n.change_language(language);settle()
        assert editor.title_entry.get_text()=='Targeta de prova'
        assert editor.comments.entry.get_text()=='Hola @bob '
        assert editor.due.hour.get_value_as_int()==22 and editor.due.minute.get_value_as_int()==5
    editor.comments.entry.set_text('@alice un comentari propi')
    editor.comments.submit()
    settle(lambda: editor.comments.send.get_sensitive() and not editor.comments.entry.get_text())
    assert any(row.get('event') == 'self-mentioned' for row in entries(store))
    editor.save();settle()
    pending=store.operations()[-1]
    assert assignment_ids(pending['payload']['changes']['assignedUsers'])=={'bob'}
    assert datetime.fromisoformat(pending['payload']['changes']['duedate']).astimezone().hour==22
    assert assignment_ids(window.find_card(99)['assignedUsers'])=={'bob'}
    from campbase.widgets import Card
    tile=next(w for w in descendants(window) if isinstance(w,Card) and w.card['id']==99)
    title=next(w for w in descendants(tile) if isinstance(w,Gtk.Label) and w.has_css_class('card-title'))
    user_avatar=next(w for w in descendants(tile.get_parent()) if isinstance(w,Adw.Avatar))
    assert user_avatar.get_parent().get_parent() is tile.get_parent()
    ok,t=title.compute_bounds(tile);ok,a=user_avatar.compute_bounds(tile)
    assert abs(t.origin.y+t.size.height/2-a.origin.y-a.size.height/2)<2
    assert not any('/assignUser' in path for _,path,_ in server.writes)
    notice=NotificationsDialog(window);notice.present(window);settle()
    assert len(entries(store))==3
    notice.activate(next(row for row in entries(store) if row.get('notice_id')))
    settle(lambda:any(method=='DELETE' and '/notifications/1?' in path for method,path,_ in server.writes))
    settle()
    assert next(row for row in entries(store) if row.get('notice_id'))['read']
    inbox=NotificationsDialog(window);inbox.present(window);settle()
    assert any(widget.has_css_class('notification-body') for widget in descendants(inbox))
    local = next(row for row in entries(store) if row.get('event') == 'self-mentioned')
    inbox.erase([local]);settle(lambda:not inbox.busy);settle()
    assert not any(row.get('event') == 'self-mentioned' for row in entries(store))
    inbox.erase(entries(store));settle(lambda:not inbox.busy);settle()
    assert not entries(store) and not inbox.clear_button.get_sensitive()
    assert not window.notification_count.get_visible()
    for error in [None, 'Prova de connexió']:
        inbox.display(error);settle()
        box=inbox.get_child();scroll=box.get_last_child();adjustment=scroll.get_vadjustment()
        adjustment.set_value(adjustment.get_upper()-adjustment.get_page_size());settle()
        ok,bounds=inbox.form.get_last_child().compute_bounds(box);assert ok
        assert abs(box.get_height()-bounds.origin.y-bounds.size.height-24)<2
    empty_height = inbox.get_child().get_height()
    inbox.working('Càrrega de prova');settle()
    assert inbox.get_child().get_height() < empty_height
    box=inbox.get_child();ok,bounds=inbox.form.get_last_child().compute_bounds(box);assert ok
    assert abs(box.get_height()-bounds.origin.y-bounds.size.height-24)<2
    inbox.finished(None,None);settle()
    store.record_notice({'key': 'local:new', 'event': 'own-comment', 'title': 'Nova prova'})
    window.update_notification_badge();settle()
    assert window.notification_count.get_visible()
    assert window.notification_count.get_width()==window.notification_count.get_height()
    inbox.force_close();settle()

    server.board['permissions']['PERMISSION_EDIT']=False
    store.cache_board(server.board);window.render();settle()
    readonly=CardDialog(window,10,window.find_card(99));readonly.window.demo=False
    # Demo fixtures intentionally allow edits, test real permission evaluation.
    readonly.force_close()
    window.demo=False
    picture=window.avatar_loader.widget(USERS[1],32)
    settle(lambda:picture.get_custom_image() is not None)
    reads=server.avatar_reads
    picture2=window.avatar_loader.widget(USERS[1],24)
    assert picture2.get_custom_image() and server.avatar_reads==reads
    readonly=CardDialog(window,10,window.find_card(99));readonly.present(window);settle()
    assert not readonly.title_entry.get_sensitive() and not readonly.assignees.get_sensitive()
    assert readonly.comments.entry.get_sensitive()
    readonly.force_close();window.demo=True
    window.close();settle()
finally:
 server.shutdown();server.server_close()
print('PASS native sharing, canonical username, authors, headers, mentions, comment metadata, assignees, due time, inbox and live six-language drafts')
