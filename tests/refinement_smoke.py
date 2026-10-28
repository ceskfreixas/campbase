# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Focused native checks for project layout, dates and visual feedback."""
import tempfile,time
from unittest.mock import patch
from pathlib import Path
import gi
gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
from gi.repository import Gtk,Adw,Gdk,GLib
from campbase.__main__ import demo_snapshot
from campbase.window import Window
from campbase.storage import Store
from campbase.project import ProjectDialog,DESCRIPTION_LIMIT
from campbase.dialogs import TextDialog, ColumnColorDialog
from campbase.date_picker import DatePicker
from campbase.widgets import Card
from campbase.card_dialog import CardDialog
from campbase.about import about_dialog
app=Adw.Application(application_id='cat.cesk.Campbase.RefinementCheck');app.register(None)
Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).add_search_path(str(Path.cwd()/'data/icons'))
css=Gtk.CssProvider();css.load_from_path(str(Path.cwd()/'campbase/style.css'))
Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
def settle(t=.2):
 end=time.monotonic()+t
 while time.monotonic()<end:
  while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
  time.sleep(.005)
def coordinates(widgets,parent):
 result=[]
 for widget in widgets:
  ok,b=widget.compute_bounds(parent);assert ok
  result.append((round(b.origin.x),round(b.origin.y),b.size.width,b.size.height))
 return result
with tempfile.TemporaryDirectory() as d:
 store=Store(d);store.put('snapshot',demo_snapshot());w=Window(app,store,True);w.set_default_size(1100,900);w.present();settle()
 for mode in ('light','dark'):
  w.set_theme(mode,False)
  p=ProjectDialog(w,w.snapshot['boards'][0]);p.present(w);settle()
  assert len(p.icons.buttons)==32
  counter=p.description_count;heading=counter.get_parent();assert heading.get_first_child().get_text()=='Descripció'
  assert heading.get_last_child() is counter and counter.get_xalign()==1
  ok,counter_bounds=counter.compute_bounds(heading);assert ok
  assert abs(counter_bounds.origin.x+counter_bounds.size.width-heading.get_width())<2
  bounds=coordinates(p.icons.buttons.values(),p.icons)
  assert len(set(y for x,y,ww,hh in bounds))==4
  assert max(x+ww for x,y,ww,hh in bounds)>=p.icons.get_width()-2
  p.description.get_buffer().set_text('à'*160)
  assert p.description_count.get_text()=='160 / 160' and p.save_button.get_sensitive()
  p.description.get_buffer().insert(p.description.get_buffer().get_end_iter(),'b')
  assert p.description_count.get_text()=='161 / 160' and not p.save_button.get_sensitive()
  p.description.get_buffer().set_text('Una frase curta.')
  assert p.save_button.get_sensitive()
  p.force_close();settle()
  t=ColumnColorDialog(w,w.stacks()[0],lambda *_:None);t.present(w);settle()
  chooser=t.color
  assert len(chooser.buttons)==16
  b=coordinates(chooser.buttons.values(),chooser)
  assert len(set(y for x,y,ww,hh in b))==2
  assert all(abs(ww-hh)<1 for x,y,ww,hh in b)
  t.close();settle()
 # The column menu initially focuses its neutral container, not an action.
 triage=w.board_body.get_first_child().get_next_sibling();menu=triage.get_first_child().get_last_child();menu.popup();settle()
 popover=menu.get_popover();assert popover.get_child().has_focus()
 assert not popover.get_child().get_first_child().has_focus()
 def menu_items(widget):
  child=widget.get_first_child()
  while child:
   if child.__gtype__.name=='GtkModelButton':yield child
   yield from menu_items(child)
   child=child.get_next_sibling()
 items=list(menu_items(popover));assert len(items)==4
 items[-1].grab_focus();assert items[-1].has_focus()
 popover.popdown();settle();menu.popup();settle()
 assert popover.get_child().has_focus() and not any(item.has_focus() for item in items)
 assert not any(item.get_state_flags() & (Gtk.StateFlags.SELECTED|Gtk.StateFlags.PRELIGHT|Gtk.StateFlags.ACTIVE) for item in items)
 controllers=popover.observe_controllers()
 keys=[controllers.get_item(i) for i in range(controllers.get_n_items())
       if isinstance(controllers.get_item(i),Gtk.EventControllerKey)
       and controllers.get_item(i).get_propagation_phase()==Gtk.PropagationPhase.CAPTURE]
 assert any(controller.emit('key-pressed',Gdk.KEY_Down,0,Gdk.ModifierType(0)) for controller in keys)
 assert items[0].has_focus()
 popover.popdown();settle()
 # Manual button and F5 action both provide feedback even for a fast request.
 w.lookup_action('sync').activate(None)
 assert w.sync_indicator.get_visible_child_name()=='spinner'
 settle(.9)
 assert w.sync_indicator.get_visible_child_name()=='icon'
 # Native due date calendar supports choosing, retaining, and clearing a date.
 picker=DatePicker();events=[];picker.connect('changed',lambda *_:events.append(picker.get_text()))
 assert picker.get_text()==''
 picker.calendar.select_day(GLib.DateTime.new_local(2027,2,3,12,0,0))
 assert picker.get_text()==''
 picker.confirm_button.emit('clicked');assert picker.get_text()=='2027-02-03'
 picker.choose('');assert picker.get_text()=='' and len(events)==2
 editor=CardDialog(w,1);editor.title_entry.set_text('Amb una data triada');editor.present(w);settle()
 editor.due.button.grab_focus();editor.due.button.popup();settle()
 assert editor.due.calendar.get_mapped()
 editor.due.calendar.select_day(GLib.DateTime.new_local(2027,2,3,12,0,0))
 editor.due.confirm_button.emit('clicked');settle()
 from datetime import date
 assert editor.due.get_subtitle()==date(2027,2,3).strftime('%x')
 assert editor.save();settle()
 from datetime import datetime
 assert datetime.fromisoformat(store.operations()[-1]['payload']['duedate']).astimezone().strftime('%Y-%m-%d %H:%M')=='2027-02-03 12:00'
 about=about_dialog();assert about.get_title()=='Quant al Campbase'
 about.present(w);settle()
 form=about.get_child().get_last_child().get_child().get_child()
 groups=[];links=[];icons=[];labels=[]
 def collect(widget):
  if isinstance(widget,Adw.PreferencesGroup):groups.append(widget.get_title())
  if isinstance(widget,Adw.ActionRow) and (widget.get_tooltip_text() or '').startswith('https://'):
   links.append(widget.get_tooltip_text())
  if isinstance(widget,Gtk.Image):icons.append(widget.get_icon_name())
  if isinstance(widget,Gtk.Label):labels.append(widget.get_text())
  child=widget.get_first_child()
  while child:collect(child);child=child.get_next_sibling()
 collect(about.get_child())
 assert groups==['Informació','Crèdits','Reconeixements','Suport']
 assert links==['https://github.com/ceskfreixas/campbase/issues',
                'https://ceskfreixas.cat','https://ceskfreixas.aixeta.cat/ca/subscriptions']
 assert 'emote-love-symbolic' in icons and '0.1.0' in labels
 assert 'Cesk Freixas' in labels and 'GPL-3.0-or-later' in labels
 from campbase.about import details_dialog
 details=details_dialog(about);settle()
 links.clear();collect(details)
 assert 'https://github.com/ceskfreixas/campbase' in links
 assert any('especialment dissenyada per a GNOME' in text for text in labels)
 details.force_close();settle()
 def external_rows(widget):
  if isinstance(widget,Adw.ActionRow) and (widget.get_tooltip_text() or '').startswith('https://'):
   yield widget
  child=widget.get_first_child()
  while child:
   yield from external_rows(child);child=child.get_next_sibling()
 for row in external_rows(about.get_child()):
  assert row.get_activatable()
  with patch('campbase.dialog_widgets.Gtk.UriLauncher.new') as launcher:
   row.emit('activated')
   launcher.assert_called_once_with(row.get_tooltip_text())
   launcher.return_value.launch.assert_called_once_with(w,None,None)
 about.force_close();settle()
 # Single-line and metadata-heavy cards stay vertically balanced.
 for extra in ({},{'duedate':'2027-02-03','labels':[{'title':'Etiqueta'}],'_pending':True}):
  c=Card(dict(w.find_card(101),**extra),w);w.board_body.append(c);settle()
  body=c.get_child();ok,b=body.compute_bounds(c);assert ok
  assert abs(b.origin.y-(c.get_height()-b.origin.y-b.size.height))<2
  w.board_body.remove(c)
 w.close();settle()
print('PASS 32 full-width icons, 16 colors, description limit, calendar, neutral menu, sync feedback and centered cards')
