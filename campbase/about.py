# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Project information, credits and support, using native Adwaita groups."""
from . import localization as ui
from gi.repository import Adw, Gtk
from . import APP_ID, VERSION, SOURCE_URL, ISSUES_URL, COPYRIGHT
from .license import LicenseDialog
from .release_dialog import ReleaseNotesDialog
from .i18n import _, LANGUAGES
from .widgets import label
from .dialog_widgets import dialog_form, external_row


def license_dialog(parent):
    LicenseDialog().present(parent)


def details_dialog(parent):
    dialog = ui.create(Adw.Dialog, title=_("Detalls"), content_width=440)
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    outer.append(Adw.HeaderBar())
    form = dialog_form()
    form.append(label(_("Una aplicació lliure de taulers kanban, especialment dissenyada per a GNOME amb GTK4 i Adwaita. Organitza els projectes amb targetes i sincronitza'ls amb Nextcloud Deck."),
                      xalign=0, wrap=True))
    info = Adw.PreferencesGroup()
    info.add(ui.create(Adw.ActionRow, title=_("Idiomes disponibles"), subtitle=' · '.join(LANGUAGES.values()), subtitle_lines=0))
    info.add(external_row(_("Codi font"), SOURCE_URL))
    form.append(info)
    outer.append(Gtk.ScrolledWindow(child=form, propagate_natural_height=True,
                                    max_content_height=540, hscrollbar_policy=Gtk.PolicyType.NEVER))
    dialog.set_child(outer)
    dialog.present(parent)
    return dialog


def about_dialog():
    dialog = ui.create(Adw.Dialog, title=_("Quant al Campbase"), content_width=360, content_height=680)
    dialog.add_css_class('about')
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    outer.append(Adw.HeaderBar())
    form = dialog_form()
    hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    hero.append(Gtk.Image(icon_name=APP_ID, pixel_size=80))
    hero.append(label('Campbase','title-1'))
    hero.append(label(COPYRIGHT,'caption'))
    version = ui.create(Gtk.Button, label=VERSION, halign=Gtk.Align.CENTER,
                        tooltip_text=_("Copia la versió"))
    version.add_css_class('app-version')
    ui.accessible(version, [Gtk.AccessibleProperty.LABEL],
                  [_("Versió {version}").format(version=VERSION)])
    version.connect('clicked', lambda button: button.get_clipboard().set(VERSION))
    hero.append(version)
    form.append(hero)
    info = ui.create(Adw.PreferencesGroup, title=_("Informació"))
    details = ui.create(Adw.ActionRow, title=_("Detalls"), activatable=True)
    details.add_suffix(Gtk.Image(icon_name='go-next-symbolic'))
    details.connect('activated', lambda *_unused: details_dialog(dialog))
    info.add(details)
    release_row = ui.create(Adw.ActionRow, title=_("Novetats de la versió"),
                            subtitle=_("Versió {version}").format(version=VERSION), activatable=True)
    release_row.add_suffix(Gtk.Image(icon_name='go-next-symbolic'))
    release_row.connect('activated', lambda *_unused: ReleaseNotesDialog().present(dialog))
    info.add(release_row)
    license_row = ui.create(Adw.ActionRow, title=_("Llicència"),subtitle='GPL-3.0-or-later')
    button = ui.create(Gtk.Button, label=_("Mostra la llicència"),valign=Gtk.Align.CENTER)
    button.connect('clicked',lambda *_unused:license_dialog(dialog))
    license_row.add_suffix(button);license_row.set_activatable_widget(button);info.add(license_row)
    info.add(external_row(_("Errors i suggeriments"), ISSUES_URL))
    form.append(info)
    credits = ui.create(Adw.PreferencesGroup, title=_("Crèdits"))
    person = external_row('Cesk Freixas', 'https://ceskfreixas.cat',
                          subtitle=_("Desenvolupament") + ' · ceskfreixas.cat')
    credits.add(person);form.append(credits)
    acknowledgements = ui.create(Adw.PreferencesGroup, title=_("Reconeixements"))
    for title,subtitle in [('GNOME',_("GTK4, Adwaita, PyGObject i Comptes en línia")),
                            ('Nextcloud Deck',_("Servidor i sincronització")),
                            ('Mistune',_("Interpretació de Markdown · BSD-3-Clause")),
                            ('Adwaita',_("Icones simbòliques del sistema"))]:
        acknowledgements.add(ui.create(Adw.ActionRow, title=title,subtitle=subtitle))
    form.append(acknowledgements)
    support = ui.create(Adw.PreferencesGroup, title=_("Suport"))
    support_row = external_row(_("Dona suport al Campbase"),
                               'https://ceskfreixas.aixeta.cat/ca/subscriptions',
                               subtitle='ceskfreixas.aixeta.cat')
    heart = Gtk.Image(icon_name='emote-love-symbolic',pixel_size=24)
    heart.add_css_class('support-heart');support_row.add_prefix(heart)
    support.add(support_row)
    form.append(support)
    scroll = Gtk.ScrolledWindow(child=form,vexpand=True,hscrollbar_policy=Gtk.PolicyType.NEVER)
    scroll.add_css_class('main-page')
    outer.append(scroll)
    dialog.set_child(outer)
    return dialog
