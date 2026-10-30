# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Current release notes shared by the application and release exporter."""
from .i18n import _

RELEASE_VERSION = '0.1.3'


def introduction():
    return _("Novetats del Campbase {version}.").format(version=RELEASE_VERSION)


def sections():
    return [
        (_("Fitxa de l'aplicació"), _("La presentació del Campbase s'ha actualitzat amb descripcions i captures en sis idiomes.")),
        (_('Estabilitat dels diàlegs'), _("S'ha millorat el tancament dels diàlegs d'etiquetes i d'esborrament de taulers, i la compatibilitat del disseny adaptable amb versions anteriors d'Adwaita.")),
        (_("Identificador de l'aplicació"), _("El Campbase utilitza l'identificador cat.ceskfreixas.Campbase, vinculat al domini ceskfreixas.cat, per preparar la distribució pública.")),
    ]
