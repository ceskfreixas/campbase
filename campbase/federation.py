# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Explicit Deck federation; credentials always stay on the account's server."""
from urllib.parse import urlsplit
from .i18n import _


def cloud_id(value):
    """An email-shaped local username is valid before the final server suffix."""
    value = value.strip()
    user, separator, remote = value.rpartition('@')
    if not separator or not user or any(c.isspace() or ord(c) < 32 for c in value):
        raise ValueError('Invalid cloud ID')
    if any(c in user for c in '/?#\\') or '\\' in remote:
        raise ValueError('Invalid cloud ID')
    parsed = urlsplit(remote if '://' in remote else 'https://' + remote)
    try:
        port = parsed.port
    except ValueError:
        raise ValueError('Invalid cloud ID') from None
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or any(p in {'.', '..'} for p in parsed.path.split('/'))):
        raise ValueError('Invalid cloud ID')
    host = parsed.hostname.encode('idna').decode('ascii').lower()
    if ':' in host:
        host = '[' + host + ']'
    return user + '@' + host + (':' + str(port) if port and port != 443 else '') + parsed.path.rstrip('/')


def federation_available(api):
    """Missing admin-only configuration is unknown, not evidence of denial."""
    from .deck import NotFoundError
    capabilities = api.request('GET', '/capabilities?format=json', service='cloud')
    version = capabilities.get('capabilities', {}).get('deck', {}).get('version', '')
    try:
        major, minor = (int(part) for part in version.split('.')[:2])
    except (ValueError, TypeError):
        return False
    if (major, minor) < (1, 18):
        return False
    try:
        config = api.request('GET', '/config', ocs=True)
    except NotFoundError:
        return False
    return config.get('federationEnabled') is not False


def share_remote(api, board_id, address, permissions, before_send=None):
    from .deck import DeckError
    try:
        address = cloud_id(address)
    except (ValueError, UnicodeError):
        raise DeckError(_("Escriu l'identificador federat complet: usuari@servidor.")) from None
    if not federation_available(api):
        raise DeckError(_("Aquest servidor no té habilitada la compartició de Deck amb altres servidors."))
    options = {'share_type': 6}
    if before_send:
        options['before_send'] = before_send
    return api.share_board(board_id, address, permissions, **options)
