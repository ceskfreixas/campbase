# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Small native identity widgets and durable, evidence-based authorship."""
from datetime import datetime
import gi
gi.require_version('Adw', '1')
gi.require_version('Gtk', '4.0')
from gi.repository import Adw, Gtk, Pango, GObject
from . import localization as ui
from .i18n import _
from .collaboration import person, members, assignment_users, remember_creator
from .widgets import label


def timestamp(value):
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone().strftime('%x · %H:%M')
    except (ValueError, AttributeError):
        return ''


def current_person(window):
    account = window.account
    profile = window.store.get('profile', {})
    if account and profile.get('account') == account.goa_id:
        return person(profile)
    return person(account.username if account else '')



def creator(window, kind, obj):
    record = window.store.get('creators', {}).get(f'{kind}:{obj["id"]}')
    if record:
        return person(record)
    # Deck exposes a card's owner, not a column creator. Never substitute the
    # connected account for missing server provenance.
    return person('')


def author_text(window, kind, obj):
    user = creator(window, kind, obj)
    if user['uid']:
        return _("Creat per {name} (@{username})").format(name=user['displayname'], username=user['uid'])
    owner = person(obj.get('owner')) if kind in {'board', 'card'} else person('')
    if owner['uid']:
        return _("Propietari: {name} (@{username})").format(name=owner['displayname'], username=owner['uid'])
    return _("L'autoria no consta a Deck.")


def card_author_text(window, card):
    user = creator(window, 'card', card)
    if user['uid']:
        return _("Autor: {name} (@{username})").format(name=user['displayname'], username=user['uid'])
    user = person(card.get('owner'))
    if user['uid']:
        return _("Responsable: {name} (@{username})").format(name=user['displayname'], username=user['uid'])
    return _("L'autoria no consta a Deck.")


def avatar(window, user, size=32):
    if window is not None:
        return window.avatar_loader.widget(user, size)
    user = person(user)
    return Adw.Avatar(size=size, text=user['displayname'], show_initials=True)


def identity(user, size=32, window=None):
    user = person(user)
    box = Gtk.Box(spacing=10, valign=Gtk.Align.CENTER, hexpand=True)
    box.append(avatar(window, user, size))
    names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
    names.append(label(user['displayname'], xalign=0, ellipsize=Pango.EllipsizeMode.END))
    names.append(label('@'+user['uid'], 'dim-label', xalign=0, ellipsize=Pango.EllipsizeMode.END))
    box.append(names)
    return box


class AssigneeSelector(Gtk.Box):
    __gsignals__ = {'changed': (GObject.SignalFlags.RUN_FIRST, None, ())}

    def __init__(self, window, board, card=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.append(label(_("Assigna a"), 'heading', xalign=0))
        self.set_hexpand(False)
        self.users = {user['uid']: user for user in members(board)}
        for user in assignment_users((card or {}).get('assignedUsers')):
            self.users[user['uid']] = user
        self.original = (card or {}).get('assignedUsers') or []
        self.buttons = {}
        selected = {user['uid'] for user in assignment_users(self.original)}
        self.menu = ui.create(Gtk.MenuButton, tooltip_text=_("Tria les persones assignades"))
        self.menu.set_always_show_arrow(True)
        self.menu.set_hexpand(True)
        self.menu.set_halign(Gtk.Align.FILL)
        self.summary = label('', xalign=0, ellipsize=Pango.EllipsizeMode.END, width_chars=14, max_width_chars=14)
        self.menu.set_child(self.summary)
        self.popover = Gtk.Popover()
        self.menu.set_popover(self.popover)
        choices = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                          margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        for uid, user in self.users.items():
            button = Gtk.CheckButton(tooltip_text='@'+uid)
            line = Gtk.Box(spacing=8)
            line.append(avatar(window, user, 24))
            line.append(label(user['displayname'], xalign=0, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, max_width_chars=32))
            button.set_child(line)
            button.set_active(uid in selected)
            self.buttons[uid] = button
            button.connect('toggled', self.toggled)
            choices.append(button)
        if not self.users:
            choices.append(label(_("Comparteix el tauler per assignar targetes als seus membres."), 'dim-label', wrap=True, max_width_chars=28))
        self.popover.set_child(Gtk.ScrolledWindow(child=choices,
            min_content_width=260, max_content_width=360, propagate_natural_width=True,
            max_content_height=300, propagate_natural_height=True,
            hscrollbar_policy=Gtk.PolicyType.NEVER))
        self.append(self.menu)
        self.refresh_summary()
        ui.on_change(self.refresh_summary)

    def refresh_summary(self):
        names = [self.users[uid]['displayname'] for uid, button in self.buttons.items() if button.get_active()]
        text = names[0] if len(names) == 1 else _("{count} persones").format(count=len(names)) if names else _("Sense assignar")
        ui.text(self.summary, 'text', text)
        ui.text(self.menu, 'tooltip_text', ', '.join(names) if names else _("Tria les persones assignades"))

    def toggled(self, *_unused):
        self.refresh_summary()
        self.emit('changed')

    def selected_users(self):
        # Preserve group/team assignments which this user picker does not edit.
        return [item for item in self.original if item.get('type', 0) != 0] + [
            {'type': 0, 'participant': self.users[uid]} for uid, button in self.buttons.items() if button.get_active()]
