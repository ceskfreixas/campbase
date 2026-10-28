# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Switch six languages in place while preserving editable user content."""
import tempfile,time
from unittest.mock import patch
from pathlib import Path
import gi
gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
from gi.repository import Gtk,Adw,Gdk,GLib
from campbase.__main__ import demo_snapshot
from campbase.storage import Store
from campbase.window import Window
from campbase.card_dialog import CardDialog
from campbase.project import ProjectDialog
from campbase.preferences import Preferences
from campbase import i18n
app=Adw.Application(application_id='cat.cesk.Campbase.LiveLanguageCheck');app.register(None)
css=Gtk.CssProvider();css.load_from_path(str(Path.cwd()/'campbase/style.css'));Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
def settle():
 end=time.monotonic()+.15
 while time.monotonic()<end:
  while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
  time.sleep(.005)
def window_timer_is_off(window):
 return window.timer==0

def texts(widget):
 result=[widget.get_text()] if isinstance(widget,Gtk.Label) else []
 child=widget.get_first_child()
 while child:result+=texts(child);child=child.get_next_sibling()
 return result
with tempfile.TemporaryDirectory() as directory:
 snapshot=demo_snapshot();snapshot['boards'][0]['title']='Descripció';snapshot['stacks']['1'][0]['cards'][0]['title']='Preferències'
 store=Store(directory);store.put('snapshot',snapshot);w=Window(app,store,True);w.present();settle()
 card=CardDialog(w,1,w.find_card(101));card.present(w);settle()
 card.title_entry.set_text('Preferències');card.description.set_markdown('**El text que estic editant**\n\nUna segona frase.');card.due.set_text('2027-02-03')
 buffer=card.description.buffer;buffer.place_cursor(buffer.get_iter_at_offset(5));markdown=card.description.get_markdown()
 project=ProjectDialog(w,w.snapshot['boards'][0]);project.present(w);settle();project.name.set_text('Descripció');project.description.get_buffer().set_text('Idioma')
 prefs=Preferences(w);prefs.present(w);settle()
 prefs.columns_per_row.set_selected(3);prefs.interval.set_selected(5);prefs.auto_sync.set_active(False);settle()
 for language in ['en','eu','gl','es','oc','ca']:
  prefs.language.set_selected(['auto',*i18n.LANGUAGES].index(language));settle()
  assert i18n.CURRENT_LANGUAGE==language,(language,i18n.CURRENT_LANGUAGE)
  assert prefs.get_title()==i18n._('Preferències').render()
  assert card.get_title()==i18n._('Targeta').render(),(language,card.get_title())
  assert project.get_title()==i18n._('Edita el projecte').render()
  assert project.icons.buttons['weather-clear-night-symbolic'].get_tooltip_text()==i18n._('Nit').render()
  assert card.description.get_first_child().get_first_child().get_child().get_tooltip_text()==i18n._('Negreta · Ctrl+B').render()
  assert card.title_entry.get_text()=='Preferències' and card.description.get_markdown()==markdown
  assert card.description.buffer is buffer and buffer.get_iter_at_mark(buffer.get_insert()).get_offset()==5
  assert card.due.get_text()=='2027-02-03' and not card.get_can_close()
  assert project.name.get_text()=='Descripció' and project.description_text()=='Idioma'
  assert prefs.startup_board.get_selected()==0 and prefs.interval.get_selected()==5
  assert prefs.columns_per_row.get_selected()==3 and store.settings()['columns_per_row']==3
  assert store.settings()['auto_sync'] is False and window_timer_is_off(w)
  assert store.settings()['language']==language and not store.operations()
  assert i18n._('TAULERS').render() in texts(w)
  print('PASS live',language,'open editors, cursor, drafts, controls and choices preserved',flush=True)
 with patch.dict(i18n._SYSTEM_ENVIRONMENT, {'LANG':'ca_ES.UTF-8','LANGUAGE':'ca'}):
  prefs.language.set_selected(0);settle();assert i18n.CURRENT_LANGUAGE=='ca' and store.settings()['language']=='auto'
 prefs.force_close();project.force_close();card.force_close();w.close();settle()
