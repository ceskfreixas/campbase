# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Current release notes shared by the application and release exporter."""
from .i18n import _

RELEASE_VERSION = '0.1.9'


def introduction():
    return _("Novetats del Campbase {version}.").format(version=RELEASE_VERSION)


def sections():
    return [
        (_("Ara no"), _("Activa un espai plegable per a les targetes que ara no vols prioritzar, compartit amb Nextcloud.")),
        (_("En espera"), _("Pausa i reprèn targetes dins de cada columna, amb arrossegament, sincronització i Desfés.")),
        (_("Progrés de les tasques"), _("Les targetes mostren quantes tasques de la llista estan completades, al costat dels comentaris i de les assignacions.")),
        (_("Targetes i arrossegament estables"), _("Triatge adapta les targetes a l'espai disponible, amb marques d'inserció de la mida de destinació i sense reajustos tardans després de sincronitzar.")),
        (_("Transicions suaus"), _("Plega i desplega «Ara no», les arxivades i «En espera» amb moviments coordinats de les targetes i dels marges.")),
        (_("Etiquetes del flux de treball"), _("L'etiqueta «En espera» queda protegida i separada de les etiquetes habituals de les targetes.")),
        (_("Barra lateral estable"), _("La barra lateral es manté tancada quan canvia la mida de la finestra o la pantalla.")),
    ]
