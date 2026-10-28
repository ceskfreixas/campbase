# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Shared native notices."""
from . import localization as ui
from .i18n import _, ngettext
from gi.repository import Adw

def message(parent, title, body):
    dialog = ui.create(Adw.AlertDialog, heading=title, body=body)
    ui.response(dialog, "close", _("D'acord"))
    dialog.set_default_response("close")
    dialog.present(parent)
