# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Hover actions, local archive visibility and footer identity with synthetic data."""
import gi
gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
from gi.repository import Adw,Gtk,Gdk,GLib
import tempfile,time
from unittest.mock import patch
from pathlib import Path
from campbase.storage import Store
from campbase.window import Window
from campbase.widgets import Column
from campbase.active_cards import ActiveCard
from campbase.card_dialog import CardDialog
from campbase.collaboration import remember_creator
app=Adw.Application(application_id='cat.cesk.Campbase.CardControlsCheck');app.register(None)
css=Gtk.CssProvider();css.load_from_path(str(Path.cwd()/'campbase/style.css'))
Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
def settle():
 end=time.monotonic()+.3
 while time.monotonic()<end:
  while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
  time.sleep(.005)
def descendants(widget):
 yield widget
 child=widget.get_first_child()
 while child:
  yield from descendants(child);child=child.get_next_sibling()
with tempfile.TemporaryDirectory() as folder:
 store=Store(folder);store.set_setting('auto_sync',False);store.set_setting('columns_per_row',1)
 owner={'uid':'alice','displayname':'Alícia Miró'}
 stacks=[{'id':sid,'title':f'Columna {sid}','cards':[
  {'id':sid*100+i,'stackId':sid,'boardId':1,'title':f'Targeta {i}','description':'Text curt','labels':[],
   'archived':i>18,'owner':owner,'order':i,'commentsCount':12 if i==1 else 0,
   'assignedUsers':[{'participant':owner}] if i in (1,19) else []} for i in range(1,21)]} for sid in (10,20,30)]
 store.put('snapshot',{'boards':[{'id':1,'title':'Tauler de prova','owner':owner}], 'stacks':{'1':stacks}})
 remember_creator(store,'card',2001,owner)
 w=Window(app,store,True);w.set_default_size(1000,700);w.present();settle()
 column=next(c for c in descendants(w) if isinstance(c,Column) and c.stack['id']==20)
 with patch.object(store,'settings',wraps=store.settings) as settings:
  w.matching_cards(column.stack)
  assert settings.call_count==1
 menu=column.get_first_child().get_last_child();first_card=column.drop.widgets[0]
 assert isinstance(first_card,ActiveCard)
 controls=first_card.drag_handle.get_parent()
 assert controls.get_first_child() is first_card.archive_button and controls.get_last_child() is first_card.drag_handle
 assert first_card.assignee_avatars.get_parent() is first_card
 ok,avatar_bounds=first_card.assignee_avatars.compute_bounds(first_card);assert ok
 assert abs(first_card.get_width()-avatar_bounds.origin.x-avatar_bounds.size.width-14)<2
 assert first_card.drag and first_card.handle_drag and first_card.handle_drag.widget is first_card
 badge=next(node for node in descendants(first_card) if node.has_css_class('card-comment-count'))
 assert badge.get_tooltip_text()=='12 comentaris' and badge.get_last_child().get_text()=='12'
 heading=first_card.card_widget.get_child().get_first_child();title=heading.get_first_child()
 assert badge.get_parent() is heading and first_card.card_widget.get_child().get_first_child() is heading
 ok,t=title.compute_bounds(first_card);assert ok
 ok,c=badge.compute_bounds(first_card);assert ok
 def ink_center(text):
  ok,b=text.compute_bounds(first_card);assert ok
  _,y=text.get_layout_offsets();ink,_=text.get_layout().get_pixel_extents()
  return b.origin.y+y+ink.y+ink.height/2
 target_center=ink_center(title)
 assert abs(target_center-ink_center(badge.get_last_child()))<=1
 ok,p=badge.get_first_child().compute_bounds(first_card);assert ok
 assert abs(target_center-p.origin.y-p.size.height/2)<=1
 adjustment=w.scroll.get_vadjustment();ok,bounds=column.compute_bounds(w.board_body);assert ok
 adjustment.set_value(bounds.origin.y-80);settle();position=adjustment.get_value();assert position>200
 for visible in (True,False,True):
  menu.popup();settle();assert menu.activate_action('column.archives',None);settle()
  assert w.shows_archived(20)==visible
  assert abs(adjustment.get_value()-position)<1,(position,adjustment.get_value())
  assert column.drop.widgets[0] is first_card and column.get_first_child().get_last_child() is menu
 archived=next(tile for tile in column.archived_section.cards if tile.card['id']==2019)
 assert archived.assignee_avatars.get_parent() is archived
 assert archived.restore_button.get_parent() is archived.delete_button.get_parent()
 # The reported title fits the available card width without an avoidable wrap.
 sample=ActiveCard(dict(first_card.card,title='Aixeta: codi obert i codi obert i',assignedUsers=[],_pending=True),w,min_width=0)
 sample.set_size_request(365,-1);sample.set_halign(Gtk.Align.START);w.board_body.append(sample);settle()
 heading=sample.card_widget.get_child().get_first_child();title=heading.get_first_child();clock=title.get_next_sibling()
 assert title.get_layout().get_line_count()==1
 ok,t=title.compute_bounds(sample);assert ok
 ok,c=clock.compute_bounds(sample);assert ok
 assert abs(t.origin.y+t.size.height/2-c.origin.y-c.size.height/2)<1
 w.board_body.remove(sample);settle()
 # Archiving is queued, opens no editor, and preserves its identity and stack.
 first_card.archive_button.emit('clicked');settle()
 op=store.operations()[0]
 assert op['kind']=='archive' and op['payload']['changes']=={'archived':True}
 assert op['payload']['card_id']==2001 and op['payload']['stack_id']==20
 assert w.find_card(2001)['archived'] and w.get_visible_dialog() is None
 editor=CardDialog(w,20,w.find_card(2001));editor.present(w);settle()
 assert w.find_card(2001)['commentsCount']==12
 footer=editor.form.get_last_child()
 assert footer.get_last_child() is editor.author_avatar
 assert editor.author_avatar.get_tooltip_text()=='Autor: Alícia Miró (@alice)'
 assert not any(isinstance(node,Gtk.Label) and node.get_text().startswith(('Propietari:','Creat per')) for node in descendants(editor))
 editor.force_close();settle()
 editor=CardDialog(w,20,w.find_card(2002));editor.present(w);settle()
 assert editor.author_avatar.get_tooltip_text()=='Responsable: Alícia Miró (@alice)'
 editor.force_close();settle()
 # When content shrinks below the viewport, GTK clamps only to the new end.
 adjustment.set_value(adjustment.get_upper()-adjustment.get_page_size());settle()
 before=adjustment.get_value();w.show_archived(30,True);settle()
 assert abs(adjustment.get_value()-before)<1
 adjustment.set_value(adjustment.get_upper()-adjustment.get_page_size());settle();before=adjustment.get_value()
 w.show_archived(30,False);settle()
 assert abs(adjustment.get_value()-min(before,adjustment.get_upper()-adjustment.get_page_size()))<1
 w.close();settle()
print('PASS stable archive toggle scroll, direct archive queue, drag controls and footer creator avatar')
