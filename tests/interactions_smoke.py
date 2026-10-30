# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Synthetic native interaction checks on an isolated Xvfb display."""
import tempfile,time
from pathlib import Path
import gi
gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
from gi.repository import Gtk,Adw,Gdk,GLib
from campbase.__main__ import demo_snapshot
from campbase.storage import Store
from campbase.window import Window
from campbase.widgets import Column
from campbase.card_dialog import CardDialog
from campbase.comments import CommentsPanel
from campbase.about import about_dialog

app=Adw.Application(application_id='cat.ceskfreixas.Campbase.InteractionsCheck');app.register(None)
Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).add_search_path(str(Path.cwd()/'data/icons'))
provider=Gtk.CssProvider();provider.load_from_path(str(Path.cwd()/'campbase/style.css'))
Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
def settle(duration=.2):
 end=time.monotonic()+duration
 while time.monotonic()<end:
  while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
  time.sleep(.005)
def columns(window):
 result=[]
 def visit(widget):
  if isinstance(widget,Column):result.append(widget)
  child=widget.get_first_child()
  while child:visit(child);child=child.get_next_sibling()
 visit(window.board_body)
 return result
with tempfile.TemporaryDirectory() as directory:
 store=Store(directory);store.put('snapshot',demo_snapshot())
 window=Window(app,store,True);window.set_default_size(1240,1000);window.present();settle()
 triage,preparation,implementation,done=columns(window)
 source=triage.drop.widgets[0]
 window.drag_session.begin(source,source.card);settle()
 assert source.has_css_class('drag-source')
 target=preparation.drop.widgets[0];ok,bounds=target.compute_bounds(preparation)
 assert ok
 preparation.drop.motion(None,bounds.origin.x+20,bounds.origin.y+2);settle()
 assert preparation.has_css_class('drop-active') and preparation.drop.placeholder.get_mapped()
 assert preparation.drop.before==target.card['id']
 preparation.drop.motion(None,20,preparation.get_height()-2);settle()
 assert preparation.drop.before is None
 assert preparation.drop.placeholder.get_parent() is preparation.drop.cards_box
 window.render();assert window._render_after_drag and window.board_body.get_first_child() is not None
 preparation.drop.drop(None,'campbase-card:'+str(source.card['id']),20,preparation.get_height()-2)
 window.drag_session.finish();settle()
 assert window.find_card(source.card['id'])['stackId']==2
 assert store.operations()[0]['kind']=='move'
 assert not window.drag_session.target and not window.drag_session.scroll_handlers
 # A cancelled drag changes no data and clears every cue.
 triage,preparation,implementation,done=columns(window)
 source=triage.drop.widgets[0];window.drag_session.begin(source,source.card)
 implementation.drop.motion(None,20,10)
 window.drag_session.finish()
 assert not implementation.has_css_class('drop-active') and not source.has_css_class('drag-source')
 assert len(store.operations())==1
 # Wrapped triage cards use horizontal midpoints and the next row's first card.
 last=triage.drop.widgets[-1];ok,bounds=last.compute_bounds(triage)
 window.drag_session.begin(preparation.drop.widgets[0],preparation.drop.widgets[0].card)
 assert triage.drop.position(bounds.origin.x+1,bounds.origin.y+3)[0]==last.card['id']
 assert triage.drop.position(bounds.origin.x+bounds.size.width-1,bounds.origin.y+bounds.size.height/2)[0] is None
 window.drag_session.finish()
 print('PASS drag insertion, feedback, cancellation, deferred refresh and wrapped triage',flush=True)
 # Empty destinations have feedback; approaching the edges never scrolls.
 original=store.get('snapshot')
 import copy
 extended=copy.deepcopy(original)
 extended['stacks']['1'][3]['cards']=[]
 template=extended['stacks']['1'][2]['cards'][0]
 extended['stacks']['1'][2]['cards'] += [dict(template,id=200+i,order=10+i,title='Targeta de prova '+str(i)) for i in range(30)]
 store.put('snapshot',extended);window.set_default_size(900,600);window.render();settle(.4)
 triage,preparation,implementation,done=columns(window)
 source=triage.drop.widgets[0];window.drag_session.begin(source,source.card)
 done.drop.motion(None,20,20);settle()
 assert done.drop.placeholder.get_mapped()
 assert done.drop.placeholder.get_child().get_first_child().get_text()=='Deixa anar aquí'
 assert done.drop.drop(None,'campbase-card:'+str(source.card['id']),20,20)
 window.drag_session.finish();settle()
 assert window.find_card(source.card['id'])['stackId']==4
 triage,preparation,implementation,done=columns(window)
 source=triage.drop.widgets[0]
 window.scroll.get_vadjustment().set_value(0);settle()
 window.drag_session.begin(source,source.card)
 ok,bounds=implementation.compute_bounds(window.scroll);assert ok
 implementation.drop.motion(None,20,window.scroll.get_height()-8-bounds.origin.y)
 settle(.3)
 assert window.scroll.get_vadjustment().get_value()==0
 window.drag_session.finish();assert not window.drag_session.scroll_handlers
 adjustment=window.scroll.get_vadjustment();adjustment.set_value(300);settle();position=adjustment.get_value()
 assert position>0
 window.drag_session.begin(source,source.card)
 adjustment.set_value(position+100);settle()
 assert adjustment.get_value()==position
 window.drag_session.finish();adjustment.set_value(position+50);settle()
 assert adjustment.get_value()>position
 store.put('snapshot',original);window.render();window.set_default_size(1240,1000)
 window.scroll.get_vadjustment().set_value(0);settle()
 print('PASS empty-column drop and fixed viewport throughout dragging',flush=True)
 # Both the normal paste action and the contextual image action use the same path.
 editor=CardDialog(window,1);editor.present(window);settle()
 texture=Gdk.MemoryTexture.new(4,4,Gdk.MemoryFormat.R8G8B8A8,GLib.Bytes.new(bytes([40,120,90,255])*16),16)
 clipboard=editor.description.view.get_clipboard();clipboard.set_content(Gdk.ContentProvider.new_for_value(texture));settle()
 assert editor.description.paste_image_action.get_enabled()
 assert editor.description.key_pressed(None,Gdk.KEY_v,0,Gdk.ModifierType.CONTROL_MASK)
 settle(.5)
 assert len(editor.description.local_images())==1
 assert editor.description.view.activate_action('campbase.paste-image',None)
 settle(.5)
 assert len(editor.description.local_images())==2
 assert editor.description.get_markdown().count('bivac-image://')==2
 # A different application normally offers serialized PNG rather than a GObject.
 clipboard.set_content(Gdk.ContentProvider.new_for_bytes('image/png',texture.save_to_png_bytes()))
 editor.description.buffer.set_text('Text substituït')
 editor.description.buffer.select_range(editor.description.buffer.get_start_iter(),editor.description.buffer.get_end_iter())
 settle()
 assert editor.description.key_pressed(None,Gdk.KEY_v,0,Gdk.ModifierType.CONTROL_MASK)
 settle(.5)
 assert len(editor.description.local_images())==1
 assert 'Text substituït' not in editor.description.get_markdown()
 editor.description.undo();assert editor.description.get_markdown()=='Text substituït'
 editor.force_close();settle()
 print('PASS clipboard paste and contextual paste preserve private embedded images',flush=True)
 # No network or real comments are used in these state checks.
 panel=CommentsPanel(window,{'id':101})
 assert panel.state.get_visible_child_name()=='loading'
 panel.display([],None);assert panel.state.get_visible_child_name()=='empty'
 panel.display(None,'Connexió interrompuda');assert panel.state.get_visible_child_name()=='error'
 panel.display([{'actorDisplayName':'Persona de prova','message':'Comentari de prova'}],None)
 assert panel.state.get_visible_child_name()=='comments'
 assert panel.comments.get_first_child().get_last_child().get_text()=='Comentari de prova'
 about=about_dialog();about.present(window);settle()
 assert isinstance(about,Adw.Dialog)
 assert about.get_title()=='Quant al Campbase'
 assert about.get_title()=='Quant al Campbase'
 about.close();window.close();settle()
 print('PASS explicit comment states and native about/credits/GPL information',flush=True)
