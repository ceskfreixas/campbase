# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Readable release notes reachable from the About information group."""
from gi.repository import Adw, Gtk
from . import localization as ui
from .i18n import _
from .releases import RELEASE_VERSION, introduction, sections
from .widgets import label
from .dialog_widgets import dialog_form


class ReleaseNotesDialog(Adw.Dialog):
    def __init__(self):
        super().__init__(content_width=440)
        ui.widget(self, title=_("Novetats de la versió"))
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.append(Adw.HeaderBar())
        body = dialog_form()
        heading = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        heading.append(label(_("Versió {version}").format(version=RELEASE_VERSION),
                             'title-2', xalign=0, wrap=True))
        heading.append(label(introduction(), xalign=0, wrap=True))
        body.append(heading)
        for title, text in sections():
            section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            section.append(label(title, 'heading', xalign=0, wrap=True))
            section.append(label(text, xalign=0, wrap=True))
            body.append(section)
        outer.append(Gtk.ScrolledWindow(child=body, vexpand=True, propagate_natural_height=True,
                                       hscrollbar_policy=Gtk.PolicyType.NEVER))
        self.set_child(outer)
