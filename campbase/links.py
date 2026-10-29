# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Web destinations derived from the current account and interface language."""
from . import i18n


def board_url(server, board_id):
    return f'{server.rstrip("/")}/index.php/apps/deck/board/{int(board_id)}'


def support_url():
    return f'https://ceskfreixas.aixeta.cat/{i18n.CURRENT_LANGUAGE}/subscriptions'
