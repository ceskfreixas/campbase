# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Accessible native choices for column colors and Adwaita project icons."""
from . import localization as ui
from .i18n import _, ngettext
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from .widgets import PALETTE


PROJECT_ICONS = {
    "view-grid-symbolic": _("Tauler"),
    "folder-symbolic": _("Carpeta"),
    "folder-documents-symbolic": _("Documents"),
    "user-home-symbolic": _("Casa"),
    "emblem-favorite-symbolic": _("Preferit"),
    "starred-symbolic": _("Estrella"),
    "weather-clear-night-symbolic": _("Nit"),
    "weather-clear-symbolic": _("Sol"),
    "network-workgroup-symbolic": _("Comunitat"),
    "system-users-symbolic": _("Equip"),
    "applications-graphics-symbolic": _("Disseny"),
    "applications-engineering-symbolic": _("Construcció"),
    "applications-system-symbolic": _("Eines"),
    "applications-science-symbolic": _("Ciència"),
    "applications-internet-symbolic": _("Internet"),
    "camera-photo-symbolic": _("Fotografia"),
    "audio-headphones-symbolic": _("Àudio"),
    "media-playback-start-symbolic": _("Vídeo"),
    "mail-unread-symbolic": _("Correu"),
    "appointment-new-symbolic": _("Calendari"),
    "document-edit-symbolic": _("Textos"),
    "dialog-information-symbolic": _("Informació"),
    "dialog-question-symbolic": _("Idees"),
    "emblem-important-symbolic": _("Important"),
    "folder-pictures-symbolic": _("Imatges"),
    "folder-music-symbolic": _("Música"),
    "folder-videos-symbolic": _("Pel·lícules"),
    "folder-download-symbolic": _("Baixades"),
    "face-smile-symbolic": _("Benestar"),
    "audio-input-microphone-symbolic": _("Veu"),
    "computer-symbolic": _("Informàtica"),
    "phone-symbolic": _("Telèfon"),
    "mark-location-symbolic": _("Llocs"),
    "user-bookmarks-symbolic": _("Referències"),
    "printer-symbolic": _("Impressió"),
    "preferences-system-symbolic": _("Configuració"),
}


class ColorChooser(Gtk.FlowBox):
    def __init__(self, current):
        super().__init__(selection_mode=Gtk.SelectionMode.NONE, column_spacing=8, homogeneous=True,
                         row_spacing=12, min_children_per_line=8, max_children_per_line=8,
                         halign=Gtk.Align.FILL, hexpand=True)
        self.add_css_class("color-choices")
        self.selected_color = current
        self.buttons = {}
        group = None
        for name, color in PALETTE.items():
            button = ui.create(Gtk.ToggleButton, tooltip_text=name, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER, width_request=32, height_request=32)
            ui.accessible(button, [Gtk.AccessibleProperty.LABEL], [name])
            button.add_css_class("color-swatch")
            button.add_css_class("swatch-"+color[1:])
            if group:
                button.set_group(group)
            else:
                group = button
            check = Gtk.Image(icon_name="object-select-symbolic", opacity=0)
            button.set_child(check)
            button.connect("toggled", self.toggled, color, check)
            button.set_active(color == current)
            self.buttons[color] = button
            self.insert(button, -1)

    def toggled(self, button, color, check):
        check.set_opacity(1 if button.get_active() else 0)
        if button.get_active():
            self.selected_color = color


class IconChooser(Gtk.FlowBox):
    def __init__(self, current, callback):
        super().__init__(selection_mode=Gtk.SelectionMode.NONE, column_spacing=6, homogeneous=True,
                         row_spacing=6, min_children_per_line=8, max_children_per_line=8,
                         halign=Gtk.Align.FILL, hexpand=True)
        self.add_css_class("icon-choices")
        self.buttons = {}
        theme = Gtk.IconTheme.get_for_display(self.get_display())
        group = None
        for icon, name in PROJECT_ICONS.items():
            if len(self.buttons) == 32:
                break
            if not theme.has_icon(icon):
                continue
            button = ui.create(Gtk.ToggleButton, tooltip_text=name)
            ui.accessible(button, [Gtk.AccessibleProperty.LABEL], [name])
            button.add_css_class("project-icon-choice")
            button.set_child(Gtk.Image(icon_name=icon, pixel_size=22))
            if group:
                button.set_group(group)
            else:
                group = button
            button.set_active(icon == current)
            button.connect("toggled", lambda item, value=icon: callback(value) if item.get_active() else None)
            self.buttons[icon] = button
            self.insert(button, -1)

    def clear_selection(self):
        for button in self.buttons.values():
            button.set_active(False)
