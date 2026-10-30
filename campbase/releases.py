# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Current release notes shared by the application and release exporter."""
from .i18n import _

RELEASE_VERSION = '0.1.4'


def introduction():
    return _("Novetats del Campbase {version}.").format(version=RELEASE_VERSION)


def sections():
    return [
        (_('Estats buits i desplegables'), _("Els comentaris i els taulers esborrats mostren estats buits més compactes, i el desplegable de mencions s'adapta als resultats.")),
    ]
