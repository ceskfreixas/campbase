# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Small reaction selector and shared reply-backed reaction chips."""
from gi.repository import Gtk
from . import localization as ui
from .i18n import _
from .comment_reactions import EMOJIS, reaction, reaction_message
from .people import current_person
from .alerts import message
from .updates import record_own_reaction


def selector(panel, parent, rows):
    button = ui.create(Gtk.MenuButton, icon_name='face-smile-symbolic', tooltip_text=_("Reacciona al comentari"))
    button.add_css_class('flat')
    popover = Gtk.Popover()
    button.set_popover(popover)
    choices = Gtk.Box(spacing=4, margin_top=8, margin_bottom=8, margin_start=8, margin_end=8)
    titles = (_("M'agrada"), _("M'encanta"), _("Em fa riure"), _("Celebrem-ho"), _("Ho estic mirant"), _("Gràcies"))
    for emoji, title in zip(EMOJIS, titles):
        option = ui.create(Gtk.Button, label=emoji, tooltip_text=title)
        option.add_css_class('flat')
        option.connect('clicked', lambda *_unused, emoji=emoji: (popover.popdown(), react(panel, parent, emoji, rows)))
        choices.append(option)
    popover.set_child(choices)
    try:
        reaction_message(parent, EMOJIS[0])
        allowed = bool(parent.get('id')) and bool(current_person(panel.window)['uid']) and not panel.window.demo
    except ValueError:
        allowed = False
    button.set_sensitive(allowed)
    return button


def chips(panel, parent, rows):
    box = Gtk.Box(spacing=4)
    uid = current_person(panel.window)['uid']
    for emoji in EMOJIS:
        selected = [item for item in rows if reaction(item) == emoji]
        users = {item['actorId']: item.get('actorDisplayName') or item['actorId'] for item in selected}
        if not users:
            continue
        button = Gtk.ToggleButton(label=f'{emoji} {len(users)}', tooltip_text=', '.join(users.values()))
        button.add_css_class('flat')
        button.add_css_class('caption')
        button.set_active(uid in users)
        button.set_sensitive(bool(uid) and not panel.window.demo)
        button.connect('clicked', lambda *_unused, emoji=emoji: react(panel, parent, emoji, rows))
        box.append(button)
    return box


def react(panel, parent, emoji, rows):
    if panel.reacting or panel.deleting:
        return
    uid = current_person(panel.window)['uid']
    own = [item for item in rows if item.get('actorId') == uid and reaction(item) == emoji]
    panel.reacting = True
    panel.comments.set_sensitive(False)
    panel.send.set_sensitive(False)
    def change(api):
        if own:
            for item in own:
                api.delete_comment(panel.card['id'], item['id'])
                panel.window.store.comment_count(panel.board_id, panel.card['id'], delta=-1)
                panel.window.store.dismiss_notice({'key': f'local:comment:{panel.card["id"]}:{item["id"]}'})
        else:
            result = api.add_comment(panel.card['id'], reaction_message(parent, emoji), parent_id=parent['id'])
            panel.window.store.comment_count(panel.board_id, panel.card['id'], delta=1)
            record_own_reaction(panel.window.store, panel.board_id, panel.card, parent, result, emoji)
    def done(_result, error):
        panel.reacting = False
        panel.comments.set_sensitive(True)
        panel.send.set_sensitive(True)
        if error and panel.get_root() is not None:
            message(panel.get_root(), _("No s'ha pogut confirmar la reacció"),
                    error+_(" Revisa els comentaris abans de tornar-ho a provar."))
        panel.refresh()
        panel.window.update_notification_badge()
    panel.window.engine.run(change, done)
