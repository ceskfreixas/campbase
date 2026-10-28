# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Adaptive dialog height, native menu accelerators and centered card content."""
import gi
gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
from gi.repository import Adw,Gtk,Gdk,GLib
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import tempfile,time
from campbase.storage import Store
from campbase.window import Window
from campbase.__main__ import demo_snapshot
from campbase.card_dialog import CardDialog
from campbase.dialogs import AccountDialog
from campbase.widgets import Card
from campbase import i18n,localization

app=Adw.Application(application_id='cat.cesk.Campbase.DialogLayoutCheck');app.register(None)
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
def bottom(dialog):
 box=dialog.content_box;scroller=box.get_last_child();form=scroller.get_child().get_child()
 adjustment=scroller.get_vadjustment();adjustment.set_value(adjustment.get_upper()-adjustment.get_page_size());settle()
 ok,bounds=form.get_last_child().compute_bounds(box);assert ok
 gap=box.get_height()-bounds.origin.y-bounds.size.height
 assert abs(gap-24)<2,(type(dialog).__name__,gap)
 return box.get_height()
with tempfile.TemporaryDirectory() as directory:
 store=Store(directory);store.put('snapshot',demo_snapshot());store.set_setting('auto_sync',False)
 w=Window(app,store,True);w.set_default_size(1100,900);w.present();settle()
 for width in (1100,520):
  w.set_default_size(width,900);settle()
  with patch('campbase.dialogs.available_accounts',return_value=[{'id':'test','title':'Compte de prova'}]):
   d=AccountDialog(w);d.present(w);settle()
  h=bottom(d)
  assert d.get_child().get_width()<=520
  assert d.content_box.get_width()<=w.get_width()
  assert not d.status.get_visible()
  d.set_status("S'està obrint el compte de GNOME…");settle();assert bottom(d)>h
  d.set_status('');settle();assert abs(bottom(d)-h)<2
  d.force_close();settle()
  with patch('campbase.dialogs.available_accounts',return_value=[]):
   d=AccountDialog(w);d.present(w);settle()
  assert d.status.get_visible();bottom(d);d.force_close();settle()
  d=CardDialog(w,1);d.present(w);settle();bottom(d)
  assert d.get_child().get_width()<=680
  assert d.content_box.get_width()<=w.get_width()
  # The due-time row becomes visible only after choosing a date.
  d.due.choose('2027-02-03');settle();bottom(d)
  d.force_close();settle()
 w.set_default_size(1100,900);settle()
 menu=w.main_menu;menu.popup();settle()
 assert menu.get_menu_model().get_n_items()==2
 assert any(isinstance(node,Gtk.Separator) for node in descendants(menu.get_popover()))
 shortcuts=[node.get_text() for node in descendants(menu.get_popover()) if isinstance(node,Gtk.Label)]
 assert {'Ctrl+,','Ctrl+?'}<=set(shortcuts)
 # GTK right-aligns shortcuts, leaving a larger gap beside shorter titles.
 columns=[]
 for row in descendants(menu.get_popover()):
  if row.__gtype__.name!='GtkModelButton':continue
  labels=[node for node in descendants(row) if isinstance(node,Gtk.Label)]
  if len(labels)!=2:continue
  ok,title=labels[0].compute_bounds(menu.get_popover());assert ok
  ok,shortcut=labels[1].compute_bounds(menu.get_popover());assert ok
  gap=shortcut.origin.x-title.origin.x-title.size.width
  assert gap>0
  columns.append((shortcut.origin.x+shortcut.size.width,gap))
 assert len(columns)==2 and abs(columns[0][0]-columns[1][0])<1
 i18n.configure('en',user_choice=True);localization.refresh();settle()
 shortcuts=[node.get_text() for node in descendants(menu.get_popover()) if isinstance(node,Gtk.Label)]
 assert {'Ctrl+,','Ctrl+?'}<=set(shortcuts)
 menu.popdown();i18n.configure('ca',user_choice=True);localization.refresh();settle()
 for card in [c for c in descendants(w) if isinstance(c,Card)]:
  body=card.get_child();assert body.get_valign()==Gtk.Align.CENTER
  ok,bounds=body.compute_bounds(card);assert ok
  assert abs(bounds.origin.y+bounds.size.height/2-card.get_height()/2)<2
 w.close();settle()
print('PASS account status sizing, new-card margins at two widths, native accelerators and centered card content')
