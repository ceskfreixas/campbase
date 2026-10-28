# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""A native optional due date with a calendar popover."""
from . import localization as ui
from .i18n import _, ngettext
from datetime import date, datetime
from .due_dates import local_due
from gi.repository import Adw, GLib, GObject, Gtk


class DatePicker(Adw.ActionRow):
    __gsignals__ = {"changed": (GObject.SignalFlags.RUN_FIRST, None, ())}

    def __init__(self, value=""):
        super().__init__(title=_("Data límit"))
        ui.widget(self, title=_("Data límit"))
        self.value = ""
        self._original = None
        self._setting = False
        self.time_row = ui.create(Adw.ActionRow, title=_("Hora límit"), subtitle=_("Hora local"), visible=False)
        time_box = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
        self.hour = Gtk.SpinButton.new_with_range(0, 23, 1)
        self.minute = Gtk.SpinButton.new_with_range(0, 59, 1)
        self.hour.set_value(12)
        for spin, title in [(self.hour, _("Hora")), (self.minute, _("Minut"))]:
            spin.set_numeric(True)
            spin.set_wrap(True)
            spin.set_width_chars(2)
            ui.accessible(spin, [Gtk.AccessibleProperty.LABEL], [title])
            spin.connect('value-changed', self.time_changed)
            spin.connect('output', lambda control: (control.set_text(f'{control.get_value_as_int():02d}'), True)[1])
        time_box.append(self.hour)
        time_box.append(Gtk.Label(label=":"))
        time_box.append(self.minute)
        self.time_row.add_suffix(time_box)
        self.button = ui.create(Gtk.MenuButton, icon_name="x-office-calendar-symbolic",
                                      tooltip_text=_("Tria la data límit"), valign=Gtk.Align.CENTER)
        self.add_suffix(self.button)
        self.set_activatable_widget(self.button)
        self.popover = Gtk.Popover()
        self.button.set_popover(self.popover)
        self.popover.connect("map", lambda *_unused: self.calendar.select_day(GLib.DateTime.new_local(*date.fromisoformat(self.value).timetuple()[:3], 12, 0, 0)) if self.value else None)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                       margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        self.calendar = Gtk.Calendar(show_week_numbers=False)
        box.append(self.calendar)
        actions = Gtk.Box(spacing=8, homogeneous=True)
        today = ui.create(Gtk.Button, label=_("Avui"))
        today.connect("clicked", lambda *_unused: self.choose(date.today().isoformat()))
        actions.append(today)
        self.clear_button = ui.create(Gtk.Button, label=_("Treu la data"))
        self.clear_button.connect("clicked", lambda *_unused: self.choose(""))
        actions.append(self.clear_button)
        box.append(actions)
        self.confirm_button = ui.create(Gtk.Button, label=_("Tria la data"))
        self.confirm_button.add_css_class("suggested-action")
        self.confirm_button.connect("clicked", lambda *_unused: self.choose(self.calendar.get_date().format("%Y-%m-%d")))
        box.append(self.confirm_button)
        self.popover.set_child(box)
        ui.text(self, 'text', value)

        ui.on_change(self.retranslate)

    def retranslate(self):
        try:
            selected = date.fromisoformat(self.value) if self.value else None
        except ValueError:
            selected = None
        ui.text(self, 'subtitle', selected.strftime('%x') if selected else _("Tria una data vàlida") if self.value else _("Sense data límit"))
        day = self.calendar.get_date()
        parent = self.calendar.get_parent()
        parent.remove(self.calendar)
        self.calendar = Gtk.Calendar(show_week_numbers=False)
        self.calendar.select_day(day)
        parent.prepend(self.calendar)

    def get_text(self):
        return self.value

    def get_due(self):
        if not self.value:
            return None
        if self._original:
            return self._original
        selected = date.fromisoformat(self.value)
        return datetime(selected.year, selected.month, selected.day, self.hour.get_value_as_int(),
                        self.minute.get_value_as_int()).astimezone().isoformat()

    def time_changed(self, *_unused):
        if not self._setting:
            self._original = None
            self.emit('changed')

    def set_text(self, value):
        self._setting = True
        self._original = value if value and 'T' in value else None
        try:
            parsed = local_due(value) if self._original else None
        except ValueError:
            parsed = None
        self.hour.set_value(parsed.hour if parsed else self.hour.get_value_as_int())
        self.minute.set_value(parsed.minute if parsed else self.minute.get_value_as_int())
        value = parsed.date().isoformat() if parsed else (value or "")[:10]
        self._setting = False
        try:
            selected = date.fromisoformat(value) if value else None
        except ValueError:
            selected = None
        changed = value != self.value
        self.value = value
        ui.text(self, 'subtitle', selected.strftime("%x") if selected else _("Tria una data vàlida") if value else _("Sense data límit"))
        self.clear_button.set_sensitive(bool(value))
        self.time_row.set_visible(bool(value))
        if selected:
            self.calendar.select_day(GLib.DateTime.new_local(selected.year, selected.month, selected.day, 12, 0, 0))
        else:
            self.calendar.select_day(GLib.DateTime.new_now_local())
        if changed:
            self.emit("changed")

    def choose(self, value):
        ui.text(self, 'text', value)
        self.popover.popdown()
