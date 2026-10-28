# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Synthetic GOA failures distinguish network checks from revoked access."""
import unittest
from unittest.mock import Mock, patch
from gi.repository import Gio, GLib
from campbase.account import Account
from campbase.i18n import _


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.info = {'id': 'test', 'path': '/org/gnome/OnlineAccounts/Accounts/test',
                     'server': 'https://example.invalid', 'username': 'fixture'}
        self.bus = Mock()
        self.addCleanup(patch.stopall)
        patch('campbase.account.available_accounts', return_value=[self.info]).start()
        patch('campbase.account.Gio.bus_get_sync', return_value=self.bus).start()

    def test_temporary_dns_check_uses_goas_stored_credential(self):
        dns = GLib.Error.new_literal(Gio.resolver_error_quark(), 'Temporary DNS failure',
                                    Gio.ResolverError.INTERNAL)
        self.bus.call_sync.side_effect = [dns, GLib.Variant('(s)', ('test-only',))]
        account = Account.from_goa('test')
        self.assertEqual(account.password, 'test-only')
        self.assertNotIn('test-only', repr(account))
        self.assertEqual([call.args[3] for call in self.bus.call_sync.call_args_list],
                         ['EnsureCredentials', 'GetPassword'])

    def test_revoked_access_does_not_fall_back_to_a_cached_password(self):
        denied = GLib.Error.new_literal(GLib.quark_from_string('goa-error-quark'),
                                       'Access revoked', 0)
        self.bus.call_sync.side_effect = denied
        with self.assertRaises(ValueError) as caught:
            Account.from_goa('test')
        self.assertEqual(str(caught.exception),
                         _("Cal revisar l'accés a Nextcloud a Configuració → Comptes en línia."))
        self.assertEqual(self.bus.call_sync.call_count, 1)

    def test_network_error_without_a_stored_password_is_not_an_auth_warning(self):
        timeout = GLib.Error.new_literal(Gio.io_error_quark(), 'Timed out', Gio.IOErrorEnum.TIMED_OUT)
        self.bus.call_sync.side_effect = timeout
        with self.assertRaises(ValueError) as caught:
            Account.from_goa('test')
        self.assertEqual(str(caught.exception),
                         _("No s'ha pogut verificar el compte per un problema de connexió. Torna-ho a provar."))

    def test_a_failure_reading_the_password_is_not_ignored(self):
        denied = GLib.Error.new_literal(Gio.io_error_quark(), 'Denied', Gio.IOErrorEnum.PERMISSION_DENIED)
        self.bus.call_sync.side_effect = [GLib.Variant('(i)', (600,)), denied]
        with self.assertRaises(ValueError):
            Account.from_goa('test')
