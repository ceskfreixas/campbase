# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Current release notes shared by the application and release exporter."""
from .i18n import _

RELEASE_VERSION = '0.1.2'


def introduction():
    return _("Novetats del Campbase {version}.").format(version=RELEASE_VERSION)


def sections():
    return [
        (_("Adjunts a les targetes"), _("Afegeix i desa documents des de la targeta amb els selectors natius de GNOME. Els enviaments sense confirmar es revisen abans de repetir-los.")),
        (_("Recuperació de taulers"), _("Desfés l'esborrament d'un tauler o recupera'l des del menú de taulers esborrats recentment, mentre Nextcloud el conservi. També es recuperen la icona i els colors locals.")),
        (_("Gestió d'etiquetes"), _("Canvia el nom i el color de les etiquetes, o esborra-les amb confirmació. Els canvis s'apliquen a les targetes del tauler i respecten els permisos i els canvis pendents.")),
        (_("Missatges de Talk"), _("Edita i esborra els teus missatges quan el servidor ho permet, amb comprovació dels canvis recents i confirmació abans d'esborrar. Els esborranys d'edició es mantenen si hi ha un error.")),
        (_("Sincronització més lleugera"), _("Es reutilitzen les dades quan Nextcloud confirma que no han canviat. La memòria cau és limitada, es renova després d'escriure i no substitueix les comprovacions dels canvis al servidor.")),
    ]
