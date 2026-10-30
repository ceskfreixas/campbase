# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Run in a fresh process for each supported language on a dedicated display."""
import os,tempfile,time
from pathlib import Path
import gi
gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
from gi.repository import Adw,Gdk,Gtk,GLib
from campbase.i18n import _,CURRENT_LANGUAGE,LANGUAGES
from campbase.__main__ import demo_snapshot
from campbase.storage import Store
from campbase.window import Window
from campbase.dialogs import Preferences,PendingDialog,AccountDialog
from campbase.project import ProjectDialog,DESCRIPTION_LIMIT
from campbase.card_dialog import CardDialog
from campbase.labels import NewLabelDialog
from campbase.about import about_dialog
from campbase.license import LicenseDialog
from campbase.release_dialog import ReleaseNotesDialog
from campbase.shortcuts import shortcuts_dialog
from unittest.mock import patch
app=Adw.Application(application_id='cat.ceskfreixas.Campbase.LanguageTest');app.register(None)
Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).add_search_path(str(Path(__file__).resolve().parents[1]/'data/icons'))

def settle():
    end=time.monotonic()+.12
    while time.monotonic()<end:
        while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
        time.sleep(.005)

def texts(widget):
    result=[]
    if isinstance(widget,Gtk.Label):result.append(widget.get_text())
    child=widget.get_first_child()
    while child:
        result.extend(texts(child));child=child.get_next_sibling()
    return result

with tempfile.TemporaryDirectory() as directory:
    store=Store(directory);snapshot=demo_snapshot()
    snapshot['stacks']['1'][0]['title']='Project-owned heading'
    store.put('snapshot',snapshot);window=Window(app,store,True);window.present();settle()
    assert window.board_body.get_first_child().get_next_sibling().has_css_class('triage')
    editor=CardDialog(window,1)
    dialogs=[Preferences(window),PendingDialog(window),ProjectDialog(window,snapshot['boards'][0]),editor,NewLabelDialog(editor.labels),shortcuts_dialog(),about_dialog(),LicenseDialog(),ReleaseNotesDialog()]
    for dialog in dialogs:
        dialog.present(window);settle()
        labels=texts(dialog.get_child())
        assert labels
        if CURRENT_LANGUAGE!='ca':
            from campbase import i18n
            for label in labels:
                if label and label in getattr(i18n._translator,'_catalog',{}) and i18n._(label)!=label:
                    raise AssertionError((CURRENT_LANGUAGE,label))
        dialog.force_close();settle()
    with patch('campbase.dialogs.available_accounts',return_value=[]):
        account=AccountDialog(window)
        assert account.status.get_visible()
        account.set_status('');assert not account.status.get_visible()
        account.set_status(_('S\'està obrint el compte de GNOME…'));assert account.status.get_visible()
    assert '<Control>p' in app.get_accels_for_action('win.preferences')
    assert app.get_accels_for_action('win.shortcuts')
    window.close();settle()
print('PASS language',CURRENT_LANGUAGE,'dialogs, shortcuts, first-column behavior and conditional status spacing')
