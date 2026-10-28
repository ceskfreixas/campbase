# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Readable program notice and license conditions; the bundled GPL is unmodified."""
from pathlib import Path
from gi.repository import Adw, Gtk
from . import localization as ui
from . import COPYRIGHT
from .i18n import _
from .widgets import label
from .dialog_widgets import dialog_form


def license_file(name):
    source = Path(__file__).resolve().parents[1] / name
    installed = Path(__file__).resolve().parents[2] / 'licenses/cat.cesk.Campbase' / name
    return (source if source.exists() else installed).read_text()


class LicenseDialog(Adw.Dialog):
    def __init__(self):
        super().__init__(title=_("Llicència del Campbase"), content_width=760, content_height=700)
        ui.widget(self, title=_("Llicència del Campbase"))
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.append(Adw.HeaderBar())
        introduction = dialog_form(spacing=6, margin_bottom=16)
        introduction.append(label('Campbase', 'title-2', xalign=0))
        introduction.append(label(COPYRIGHT, 'dim-label', xalign=0))
        introduction.append(label(_("GNU GPL, versió 3 o posterior"), 'heading', xalign=0, wrap=True))
        introduction.append(label(_("Pots utilitzar, estudiar, modificar i redistribuir el Campbase d'acord amb aquesta llicència."), xalign=0, wrap=True))
        license_link = ui.create(Gtk.LinkButton, uri='https://www.gnu.org/licenses/gpl-3.0.html',
                                  label=_("Llicència al web"), halign=Gtk.Align.START)
        license_link.add_css_class('license-web-link')
        introduction.append(license_link)
        outer.append(introduction)
        self.pages = Gtk.Stack(vexpand=True)
        switcher = Gtk.StackSwitcher(stack=self.pages, halign=Gtk.Align.CENTER,
                                      margin_start=24, margin_end=24, margin_bottom=12)
        outer.append(switcher)
        notice_page, self.notice = self.text_page(license_file('NOTICE'), monospace=False)
        ui.stack_title(self.pages, notice_page, 'notice', _("Avís del Campbase"))
        # The appendix is an application tutorial with example placeholders,
        # not additional conditions. The complete original file stays bundled.
        terms = license_file('LICENSE').split('How to Apply These Terms to Your New Programs', 1)[0].rstrip()+'\n'
        terms_page, self.terms = self.text_page(terms, monospace=True)
        ui.stack_title(self.pages, terms_page, 'terms', _("Condicions de la llicència"))
        outer.append(self.pages)
        self.set_child(outer)

    @staticmethod
    def text_page(contents, monospace):
        view = Gtk.TextView(editable=False, cursor_visible=False, accepts_tab=False,
                            monospace=monospace, wrap_mode=Gtk.WrapMode.WORD_CHAR,
                            left_margin=24, right_margin=24, top_margin=16, bottom_margin=24,
                            pixels_above_lines=2, pixels_below_lines=2)
        view.get_buffer().set_text(contents)
        return Gtk.ScrolledWindow(child=view, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER), view
