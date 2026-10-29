# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Consistent inbox wording from structured notification metadata."""
from .i18n import _
from .comment_reactions import reaction_preview


def parameters(item):
    rich = item.get('subjectRichParameters')
    return rich if isinstance(rich, dict) else {}


def notification_actor(item):
    user = parameters(item).get('user')
    return user.get('id') if isinstance(user, dict) else None


def notification_title(item):
    fallback = item.get('subject') or ''
    rich = parameters(item)
    def name(key):
        value = rich.get(key)
        return value.get('name') if isinstance(value, dict) and isinstance(value.get('name'), str) else ''
    user, card, board = name('user'), name('deck-card'), name('deck-board')
    if item.get('app') == 'spreed':
        if (item.get('object_type') or '') != 'chat':
            return fallback
        conversation = name('call')
        if user and conversation and conversation != user:
            return _("{name} t'ha enviat un missatge a «{conversation}».").format(name=user, conversation=conversation)
        if user:
            return _("{name} t'ha enviat un missatge.").format(name=user)
        return fallback
    if item.get('app') not in (None, 'deck'):
        return fallback
    emoji = reaction_preview(item.get('message'))
    if user and card:
        if emoji:
            return _("{name} ha reaccionat {emoji} al teu comentari de la targeta «{title}».").format(name=user, emoji=emoji, title=card)
        if item.get('message'):
            return _("{name} t'ha mencionat en un comentari de la targeta «{title}».").format(name=user, title=card)
        if board:
            return _("{name} t'ha assignat la targeta «{title}».").format(name=user, title=card)
        return fallback
    if user and board:
        return _("{name} ha compartit el tauler «{title}» amb tu.").format(name=user, title=board)
    if card and board:
        return _("La targeta «{title}» del tauler «{board}» ha arribat al venciment.").format(title=card, board=board)
    return fallback
