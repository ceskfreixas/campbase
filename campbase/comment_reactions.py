# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Portable reactions are ordinary emoji replies mentioning the parent author."""
from .collaboration import mention_token

EMOJIS = ('👍', '❤️', '😂', '🎉', '👀', '🙏')


def reaction_message(parent, emoji):
    if emoji not in EMOJIS or parent.get('actorType', 'users') != 'users' or not parent.get('actorId'):
        raise ValueError('Unsupported reaction or author')
    return emoji+' '+mention_token(parent['actorId'])


def reaction(item):
    parent = item.get('replyTo')
    if (not isinstance(parent, dict) or not parent.get('id') or not item.get('actorId') or
            item.get('actorType', 'users') != 'users'):
        return None
    for emoji in EMOJIS:
        try:
            if item.get('message', '').strip() == reaction_message(parent, emoji):
                return emoji
        except ValueError:
            return None
    return None


def group_comments(rows):
    comments, reactions = {}, {}
    for item in rows:
        emoji = reaction(item)
        if emoji:
            parent = item['replyTo']
            key = str(parent['id'])
            comments.setdefault(key, parent)
            reactions.setdefault(key, []).append(item)
        else:
            comments[str(item.get('id'))] = item
    return sorted(comments.values(), key=lambda item: item.get('creationDateTime') or ''), reactions


def reaction_preview(message):
    """Recognize our readable reply format in a server mention notification."""
    for emoji in EMOJIS:
        if isinstance(message, str) and message.startswith(emoji+' @') and '\n' not in message:
            token = message[len(emoji)+1:]
            uid = token[7:-1] if token.startswith('@"user/') and token.endswith('"') else token[1:]
            try:
                if mention_token(uid) == token:
                    return emoji
            except ValueError:
                pass
    return None
