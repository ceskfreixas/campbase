# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Current release notes shared by the application and release exporter."""
from .i18n import _

RELEASE_VERSION = '0.1.6'


def introduction():
    return _("Novetats del Campbase {version}.").format(version=RELEASE_VERSION)


def sections():
    return [
        (_("Paperera del tauler"), _("Recupera targetes i columnes des dels elements esborrats de cada tauler.")),
        (_("Arxivament en bloc"), _("Arxiva totes les targetes d'una columna des del seu menú, amb confirmació i sincronització conjunta.")),
        (_("Interfície més compacta"), _("Unifiquem el marge interior de les targetes i escurcem les etiquetes dels menús.")),
    ]
