# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Project information using the standard GNOME About dialog."""
from html import escape
from gi.repository import Adw, Gtk
from . import localization as ui
from . import APP_ID, VERSION, SOURCE_URL, ISSUES_URL, COPYRIGHT
from .license import LicenseDialog
from .i18n import _, LANGUAGES, Message
from .links import support_url
from .releases import introduction, sections


def release_markup():
    """Adwaita uses the same small HTML subset as AppStream release notes."""
    items = ''.join('<li><em>' + escape(ui.render(title)) + '</em>: '
                    + escape(ui.render(text)) + '</li>' for title, text in sections())
    return '<p>' + escape(ui.render(introduction())) + '</p><ul>' + items + '</ul>'


def activate_link(dialog, uri):
    if uri == 'campbase:license':
        LicenseDialog().present(dialog)
        return True
    if uri == 'campbase:support':
        # Resolve at activation time so the destination follows live language changes.
        Gtk.UriLauncher.new(support_url()).launch(dialog.get_root(), None, None)
        return True
    return False


def about_dialog():
    dialog = ui.create(Adw.AboutDialog,
        title=_("Quant al Campbase"),
        application_name='Campbase', application_icon=APP_ID,
        developer_name='Cesk Freixas', version=VERSION,
        copyright=COPYRIGHT, license_type=Gtk.License.GPL_3_0,
        developers=['Cesk Freixas https://ceskfreixas.cat'],
        website=SOURCE_URL, issue_url=ISSUES_URL,
        comments=_("Una aplicació lliure de taulers kanban, especialment dissenyada per a GNOME amb GTK4 i Adwaita. Organitza els projectes amb targetes i sincronitza'ls amb Nextcloud Deck.")
                 + '\n\n' + _("Idiomes disponibles") + ': ' + ' · '.join(LANGUAGES.values()),
        release_notes=Message(release_markup), release_notes_version=VERSION)
    dialog.add_link(ui.render(_("Dona suport al Campbase")), 'campbase:support')
    dialog.add_link(ui.render(_("Mostra la llicència")), 'campbase:license')
    dialog.add_acknowledgement_section(None, [
        'GNOME https://www.gnome.org',
        'Nextcloud Deck https://github.com/nextcloud/deck',
        'Mistune https://github.com/lepture/mistune'])
    dialog.connect('activate-link', activate_link)
    return dialog
