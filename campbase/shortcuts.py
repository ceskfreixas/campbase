# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Discoverable native keyboard shortcut reference."""
from . import localization as ui
from gi.repository import Adw, Gtk
from .i18n import _


def shortcuts_dialog():
    dialog = ui.create(Adw.Dialog, title=_("Dreceres de teclat"), content_width=560, content_height=620)
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    outer.append(Adw.HeaderBar())
    page = Adw.PreferencesPage()
    groups = [
        (_("Navegació"), [(_("Mostra o amaga els taulers"), 'F9'), (_("Cerca al tauler"), '<Control>f'), (_("Sincronitza amb Deck"), 'F5'), (_("Sincronitza amb Deck"), '<Control>r')]),
        (_("Aplicació"), [(_("Preferències"), '<Control>p'), (_("Preferències"), '<Control>comma'), (_("Dreceres de teclat"), '<Control>question'), (_("Tanca el diàleg o la cerca"), 'Escape')]),
        (_("Targetes"), [(_("Targeta nova"), '<Control>n')]),
        (_("Edició de text"), [(_("Negreta"), '<Control>b'), (_("Cursiva"), '<Control>i'), (_("Subratllat"), '<Control>u'), (_("Desfés"), '<Control>z'), (_("Refés"), '<Control><Shift>z'), (_("Copia"), '<Control>c'), (_("Retalla"), '<Control>x'), (_("Selecciona-ho tot"), '<Control>a'), (_("Enganxa text o una imatge"), '<Control>v')]),
    ]
    for title, shortcuts in groups:
        group = ui.create(Adw.PreferencesGroup, title=title)
        for name, accelerator in shortcuts:
            row = ui.create(Adw.ActionRow, title=name)
            row.add_suffix(Gtk.ShortcutLabel(accelerator=accelerator, valign=Gtk.Align.CENTER))
            group.add(row)
        page.add(group)
    outer.append(page)
    dialog.set_child(outer)
    return dialog
