# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Synthetic native label editing and content-sized dialog checks."""
import tempfile,time
from pathlib import Path
import gi
gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
from gi.repository import Gtk,Adw,Gdk,GLib
from campbase.__main__ import demo_snapshot
from campbase.window import Window
from campbase.storage import Store
from campbase.card_dialog import CardDialog
from campbase.labels import NewLabelDialog
from campbase.project import ProjectDialog
from campbase.dialogs import PendingDialog

app=Adw.Application(application_id='cat.cesk.Campbase.LabelCheck');app.register(None)
provider=Gtk.CssProvider();provider.load_from_path(str(Path.cwd()/'campbase/style.css'))
Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
def settle():
 end=time.monotonic()+.2
 while time.monotonic()<end:
  while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
  time.sleep(.005)
def bottom_margin(dialog):
 box=getattr(dialog,'content_box',dialog.get_child());scroll=box.get_last_child();form=scroll.get_child().get_child()
 adjustment=scroll.get_vadjustment();adjustment.set_value(adjustment.get_upper()-adjustment.get_page_size());settle()
 ok,b=form.get_last_child().compute_bounds(box);assert ok
 assert abs(box.get_height()-b.origin.y-b.size.height-24)<2
with tempfile.TemporaryDirectory() as directory:
 store=Store(directory);snapshot=demo_snapshot()
 labels=[{'id':1,'title':'Urgent','color':'E01B24','boardId':1},{'id':2,'title':'Disseny','color':'3584E4','boardId':1}]
 snapshot['boards'][0]['labels']=labels
 snapshot['stacks']['1'][0]['cards'][0]['labels']=[labels[0]]
 store.put('snapshot',snapshot)
 window=Window(app,store,True);window.set_default_size(1100,900);window.present();settle()
 for dialog in [ProjectDialog(window,snapshot['boards'][0])]:
  dialog.present(window);settle();bottom_margin(dialog);dialog.force_close();settle()
 pending=PendingDialog(window);pending.present(window);settle()
 assert isinstance(pending.get_child().get_last_child().get_child().get_child(),Adw.StatusPage)
 assert pending.get_child().get_height()<window.get_height()
 pending.force_close();settle()
 card=window.find_card(101)
 editor=CardDialog(window,1,card);editor.present(window);settle()
 assert not any(isinstance(child,Gtk.StackSwitcher) for child in [editor.content_box.get_first_child(),editor.content_box.get_last_child()])
 section=editor.comments.get_parent();footer=section.get_next_sibling();actions=footer.get_first_child()
 assert section.get_parent() is editor.form
 assert actions.get_first_child().get_label()=='Arxiva la targeta'
 assert not isinstance(editor.comments.state.get_visible_child(),Gtk.ScrolledWindow)
 bottom_margin(editor)
 assert editor.get_can_close() and editor.labels.buttons[1].get_active()
 editor.labels.buttons[2].set_active(True)
 assert not editor.get_can_close()
 editor.force_close();settle()
 assert not store.operations() and window.find_card(101)['labels']==[labels[0]]
 editor=CardDialog(window,1,card);editor.present(window);settle()
 editor.labels.buttons[1].set_active(False);editor.labels.buttons[2].set_active(True)
 assert editor.save();settle()
 assert store.operations()[0]['payload']['changes']['labels']==[labels[1]]
 assert window.find_card(101)['labels']==[labels[1]]
 pending=PendingDialog(window);pending.present(window);settle();bottom_margin(pending);pending.force_close();settle()
 editor=CardDialog(window,1);editor.present(window);settle()
 editor.title_entry.set_text('Targeta amb una etiqueta nova')
 new=NewLabelDialog(editor.labels);new.present(window);settle()
 new.name.set_text('Comunitat');new.color.buttons['#33a56c'].set_active(True)
 new.create();settle()
 assert editor.labels.selected_labels()[0]['title']=='Comunitat'
 assert editor.labels.selected_labels()[0]['color']=='33a56c'
 assert len(store.get('snapshot')['boards'][0]['labels'])==3
 assert editor.save();settle()
 draft=store.operations()[-1]
 assert draft['kind']=='create' and draft['payload']['labels'][0]['title']=='Comunitat'
 assert window.find_card(-draft['id'])['labels'][0]['title']=='Comunitat'
 window.close();settle()
print('PASS label assignment, removal, cancel, creation, offline drafts and 24px dialog bottom margins')
