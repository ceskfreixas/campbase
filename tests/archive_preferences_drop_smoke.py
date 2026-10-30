# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Real preferences, local exceptions, assignment filter and archive drop routing."""
import gi
gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
from gi.repository import Adw,Gtk,Gdk,GLib
import tempfile,time
from pathlib import Path
from types import SimpleNamespace
from campbase.storage import Store
from campbase.window import Window
from campbase.widgets import Column
from campbase.preferences import Preferences
from campbase.card_dialog import CardDialog
app=Adw.Application(application_id='cat.ceskfreixas.Campbase.ArchivePreferencesCheck');app.register(None)
css=Gtk.CssProvider();css.load_from_path(str(Path.cwd()/'campbase/style.css'))
Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
def settle(until=None):
 end=time.monotonic()+(5 if until else .2)
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
def column(window,sid):return next(c for c in descendants(window) if isinstance(c,Column) and c.stack['id']==sid)
with tempfile.TemporaryDirectory() as folder:
 store=Store(folder);store.set_setting('auto_sync',False)
 owner={'uid':'alice','displayname':'Alícia'}
 cards=[{'id':99,'stackId':10,'title':'Meva','order':0,'archived':False,'assignedUsers':[{'participant':owner}], 'labels':[]},
        {'id':100,'stackId':10,'title':'Altra','order':1,'archived':True,'assignedUsers':[{'participant':{'uid':'bob'}}],'labels':[]}]
 store.put('snapshot',{'boards':[{'id':1,'title':'Prova','owner':owner,'permissions':{'PERMISSION_EDIT':True}}],
                       'stacks':{'1':[{'id':10,'title':'Primera','cards':cards},{'id':20,'title':'Segona','cards':[]}]}})
 w=Window(app,store,True);w.account=SimpleNamespace(username='login-alias',goa_id='test',server='https://example.invalid')
 store.put('profile',dict(owner,account='test'));w.set_default_size(1100,900);w.present();settle()
 w.show_archived(10,True);prefs=Preferences(w);prefs.present(w);settle()
 prefs.archives_default.set_active(True);settle();assert w.shows_archived(10) and w.shows_archived(20)
 assert store.settings()['archived_overrides']=={}
 w.show_archived(10,False)
 prefs.archives_default.set_active(False);settle();assert not w.shows_archived(10) and not w.shows_archived(20)
 prefs.archives_default.set_active(True);settle();assert w.shows_archived(10) and w.shows_archived(20)
 prefs.force_close();settle()
 menu=column(w,10).get_first_child().get_last_child()
 assert not menu.activate_action('column.inherit',None)
 w.show_archived(10,False);settle();assert not w.shows_archived(10) and w.shows_archived(20)
 w.show_archived(10,True);settle()
 assert w.mine_filter.get_parent().has_css_class('board-actions')
 assert w.mine_filter.get_icon_name()=='cat.ceskfreixas.Campbase-assigned-symbolic'
 w.mine_filter.set_active(True);settle();assert [c['id'] for c in w.filtered_cards(w.stacks()[0])]==[99]
 w.mine_filter.set_active(False);settle();assert len(w.filtered_cards(w.stacks()[0]))==2
 source=column(w,10).drop.widgets[0];destination=column(w,20)
 assert destination.archived_section and not destination.archived_section.delete_all.get_sensitive()
 w.drag_session.begin(source,source.card);settle()
 ok,b=destination.archived_section.compute_bounds(destination);assert ok
 x,y=b.origin.x+b.size.width/2,b.origin.y+b.size.height/2
 destination.drop.motion(None,x,y);settle()
 assert w.drag_session.target is destination.archived_section.drop
 assert destination.archived_section.has_css_class('archive-drop-active')
 assert destination.drop.drop(None,'campbase-card:99',x,y)
 assert not destination.drop.drop(None,'campbase-card:99',x,y) # One drop, one action.
 w.drag_session.finish();settle()
 assert w.find_card(99)['stackId']==20 and w.find_card(99)['archived']
 assert store.operations()[0]['payload']['archived'] is True
 w._undo_toast.emit('button-clicked');settle(lambda:w.find_card(99)['stackId']==10);settle()
 assert not w.find_card(99)['archived'] and not store.operations()
 # Archived cards can be restored by dropping among active cards, or kept
 # archived when moved between archive sections; both remain undoable.
 for target_archive in (False,True):
  source=next(tile for tile in column(w,10).archived_section.cards if tile.card['id']==100)
  assert source.drag is not None
  w.drag_session.begin(source,source.card);settle()
  destination=column(w,20).archived_section.drop if target_archive else column(w,20).drop
  assert destination.drop(None,'campbase-card:100',10,0)
  w.drag_session.finish();settle()
  assert w.find_card(100)['stackId']==20 and bool(w.find_card(100)['archived'])==target_archive
  w._undo_toast.emit('button-clicked');settle(lambda:w.find_card(100)['stackId']==10);settle()
  assert w.find_card(100)['archived'] and not store.operations()
 snapshot=store.get('snapshot');snapshot['stacks']['1'][0]['cards'].append(
  dict(cards[1],id=101,title='Arxivada segona',order=2))
 store.put('snapshot',snapshot);w.render();settle()
 section=column(w,10).archived_section;source=section.cards[-1]
 w.drag_session.begin(source,source.card);settle()
 assert section.drop.drop(None,'campbase-card:101',10,0)
 w.drag_session.finish();settle()
 assert [c['id'] for c in w.filtered_cards(w.stacks()[0]) if c.get('archived')]==[101,100]
 w._undo_toast.emit('button-clicked');settle(lambda:not store.operations());settle()
 source=column(w,10).drop.widgets[0];destination=column(w,10)
 w.drag_session.begin(source,source.card);settle()
 assert destination.archived_section.drop.drop(None,'campbase-card:99',10,10)
 w.drag_session.finish();settle();assert w.find_card(99)['archived']
 w._undo_toast.emit('button-clicked');settle(lambda:not w.find_card(99)['archived']);settle()
 assert not store.operations()
 stale=column(w,20).archived_section.drop;w.show_archived(20,False)
 assert not stale.accepts()
 editor=CardDialog(w,10,w.find_card(99));editor.present(w);settle()
 editor.title_entry.set_text('Canvi conservat');editor.column.set_selected(1)
 editor.archive();settle()
 assert w.find_card(99)['stackId']==20 and w.find_card(99)['archived']
 w._undo_toast.emit('button-clicked');settle(lambda:not w.find_card(99)['archived'])
 assert w.find_card(99)['stackId']==20 and w.find_card(99)['title']=='Canvi conservat'
 w.close();settle()
print('PASS global reset, column exceptions, board filter, archived drag/restore/reorder, undo and preserved edits')
