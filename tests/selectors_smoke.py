# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Native selector checks with synthetic data on an isolated display."""
import tempfile,time
from pathlib import Path
import gi
gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
from gi.repository import Gtk,Adw,Gdk,GLib,Gio
from campbase.__main__ import demo_snapshot
from campbase.window import Window
from campbase.storage import Store
from campbase.project import ProjectDialog,project_image
from campbase.dialogs import TextDialog, ColumnColorDialog
from campbase.choosers import ColorChooser,IconChooser
from campbase.widgets import Card
app=Adw.Application(application_id='cat.ceskfreixas.Campbase.SelectorsCheck');app.register(None)
Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).add_search_path(str(Path(__file__).resolve().parents[1]/"data/icons"))
css=Gtk.CssProvider();css.load_from_path(str(Path.cwd()/'campbase/style.css'))
Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
def settle():
 end=time.monotonic()+.25
 while time.monotonic()<end:
  while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
  time.sleep(.005)
with tempfile.TemporaryDirectory() as d:
 store=Store(d);store.put('snapshot',demo_snapshot());store.put('board_metadata',{'1':{'emoji':'💧','description':'Descripció que es conserva'}})
 w=Window(app,store,True);w.set_default_size(900,900);w.present();settle()
 assert isinstance(project_image(w,{'emoji':'💧'}),Gtk.Label)
 for theme in ('light','dark'):
  w.set_theme(theme,False)
  results=[]
  dialog=ColumnColorDialog(w,w.stacks()[0],lambda color:results.append(color));dialog.present(w);settle()
  form=dialog.get_child().get_last_child()
  chooser=dialog.color
  assert isinstance(chooser,ColorChooser)
  assert len(chooser.buttons)==16
  assert sum(b.get_active() for b in chooser.buttons.values())==1
  chooser.buttons['#33a56c'].set_active(True)
  assert chooser.selected_color=='#33a56c'
  assert sum(b.get_active() for b in chooser.buttons.values())==1
  assert chooser.buttons['#33a56c'].get_child().get_opacity()==1
  dialog.save_button.emit('clicked');settle()
  assert results==['#33a56c']
  project=ProjectDialog(w,w.snapshot['boards'][0]);project.present(w);settle()
  assert len(project.icons.buttons)==32
  assert project.get_can_close()
  assert project.metadata['emoji']=='💧'
  project.icons.buttons['weather-clear-night-symbolic'].set_active(True)
  assert not project.get_can_close() and 'emoji' not in project.metadata
  assert project.preview.get_first_child().get_icon_name()=='weather-clear-night-symbolic'
  project.force_close();settle()
  assert store.get('board_metadata')['1']['emoji']=='💧'
 project=ProjectDialog(w,w.snapshot['boards'][0]);project.present(w);settle()
 project.icons.buttons['weather-clear-night-symbolic'].set_active(True)
 project.save();settle()
 metadata=Store(d).get('board_metadata')['1']
 assert metadata['icon']=='weather-clear-night-symbolic' and 'emoji' not in metadata
 assert metadata['description']=='Descripció que es conserva'
 assert not store.operations()
 # Oversized source images must stay compact next to the title.
 image_path=Path(d)/'large.svg'
 image_path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="2048" height="1024"><rect width="2048" height="1024" fill="#2190a4"/></svg>')
 record=w.assets.import_file(Gio.File.new_for_path(str(image_path)),icon=True)
 project=ProjectDialog(w,w.snapshot['boards'][0]);project.present(w);settle()
 project.metadata['image']=record['path'];project.refresh_preview();settle()
 image=project.preview.get_first_child()
 assert image.get_width()<=56 and image.get_height()<=56
 board_image=project_image(w,project.metadata)
 assert board_image.measure(Gtk.Orientation.HORIZONTAL,-1).natural<=44
 assert board_image.measure(Gtk.Orientation.VERTICAL,-1).natural<=44
 project.remove_image()
 assert project.preview.get_first_child().get_icon_name()=='view-grid-symbolic'
 assert not any(button.get_active() for button in project.icons.buttons.values())
 project.save();settle()
 metadata=Store(d).get('board_metadata')['1']
 assert 'image' not in metadata and metadata['icon']==''
 assert project_image(w,metadata).get_icon_name()=='view-grid-symbolic'
 assert metadata['description']=='Descripció que es conserva'
 for blocked in (False,True):
  data=dict(w.find_card(101),title='Una targeta pendent amb un títol prou llarg per ocupar diverses línies',_pending=True,_blocked=blocked)
  card=Card(data,w)
  w.board_body.append(card);settle()
  heading=card.get_child().get_first_child();indicator=heading.get_last_child()
  assert isinstance(indicator,Gtk.Image)
  assert indicator.get_icon_name()==('dialog-warning-symbolic' if blocked else 'document-open-recent-symbolic')
  assert card.get_child().get_last_child() is heading
  assert indicator.get_pixel_size()==14
  ok,bounds=indicator.compute_bounds(heading)
  assert ok and bounds.origin.x+bounds.size.width<=heading.get_width()+1
  w.board_body.remove(card)
 w.close();settle()
print('PASS colors, Adwaita icons, cancel/save, constrained large images and clearing project identity in both themes')
