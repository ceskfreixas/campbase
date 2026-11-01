# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Current release notes shared by the application and release exporter."""
from .i18n import _

RELEASE_VERSION = '0.1.8'


def introduction():
    return _("Novetats del Campbase {version}.").format(version=RELEASE_VERSION)


def sections():
    return [
        (_("Dependències de targetes"), _("Enllaça, consulta i treu les targetes dependents quan el servidor Deck ho admeti.")),
        (_("Llistes de tasques"), _("Escriu llistes amb caselles que pots marcar i desmarcar, amb continuació automàtica i Desfés/Refés.")),
        (_("Càrrega dels detalls"), _("Els comentaris i les dependències es carreguen en paral·lel i mostren dades recents mentre s'actualitzen.")),
        (_("Barra d'edició ordenada"), _("Les eines de format, les llistes, les insercions i Desfés/Refés s'agrupen amb separadors.")),
        (_("Navegació i compte"), _("En tancar una targeta, conserva la posició del tauler i el focus. Les preferències mostren el correu electrònic del compte.")),
        (_("Suport al projecte"), _("El botó Sponsor de GitHub enllaça amb les subscripcions del projecte a l'Aixeta.")),
    ]
