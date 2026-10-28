# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Readable license views with filled program data and unmodified GPL terms."""
import time
from pathlib import Path
import gi
gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
from gi.repository import Adw,Gtk,GLib
from campbase.license import LicenseDialog,license_file
from campbase import COPYRIGHT,i18n
app=Adw.Application(application_id='cat.cesk.Campbase.LicenseCheck');app.register(None)
window=Adw.ApplicationWindow(application=app,default_width=1100,default_height=900);window.present()
def settle():
 end=time.monotonic()+.15
 while time.monotonic()<end:
  while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
  time.sleep(.005)
def contents(view):
 buffer=view.get_buffer();return buffer.get_text(buffer.get_start_iter(),buffer.get_end_iter(),True)
dialog=LicenseDialog();dialog.present(window);settle()
notice,terms=contents(dialog.notice),contents(dialog.terms)
assert notice==license_file('NOTICE')
assert 'Copyright (C) 2026 Cesk Freixas' in notice
assert 'Campbase is free software' in notice and 'any later version' in ' '.join(notice.split())
assert 'https://github.com/ceskfreixas/campbase' in notice
assert terms.startswith(license_file('LICENSE').splitlines()[0])
assert terms.rstrip().endswith('END OF TERMS AND CONDITIONS')
for value in [notice,terms]:
 assert '<year>' not in value and '<name of author>' not in value and '<one line' not in value
for name,view in [('notice',dialog.notice),('terms',dialog.terms)]:
 dialog.pages.set_visible_child_name(name);settle()
 assert not view.get_editable() and view.get_wrap_mode()==Gtk.WrapMode.WORD_CHAR
 assert view.get_left_margin()==24 and view.get_right_margin()==24 and view.get_bottom_margin()==24
 assert view.get_width()>500
assert dialog.terms.get_monospace() and not dialog.notice.get_monospace()
dialog.pages.set_visible_child_name('terms');settle()
i18n.change_language('en');settle()
assert dialog.get_title()=='Campbase license'
assert dialog.pages.get_visible_child_name()=='terms' and contents(dialog.terms)==terms
assert COPYRIGHT=='© 2026 Cesk Freixas'
dialog.force_close();window.close();settle()
print('PASS filled program notice, readable license pages, exact terms and live translated controls')
