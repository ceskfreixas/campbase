# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Nextcloud identities and credentials come from GNOME Online Accounts."""
from .i18n import _, ngettext
import json
import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

from gi.repository import Gio, GLib
from .storage import CONFIG_DIR, private_dir

GOA = "org.gnome.OnlineAccounts"
ROOT = "/org/gnome/OnlineAccounts"
ACCOUNT = GOA + ".Account"


def network_failure(error):
    resolver = [Gio.ResolverError.NOT_FOUND, Gio.ResolverError.TEMPORARY_FAILURE,
                Gio.ResolverError.INTERNAL]
    connection = [Gio.IOErrorEnum.HOST_NOT_FOUND, Gio.IOErrorEnum.HOST_UNREACHABLE,
                  Gio.IOErrorEnum.NETWORK_UNREACHABLE, Gio.IOErrorEnum.CONNECTION_REFUSED,
                  Gio.IOErrorEnum.TIMED_OUT, Gio.IOErrorEnum.NOT_CONNECTED]
    return (any(error.matches(Gio.resolver_error_quark(), code) for code in resolver) or
            any(error.matches(Gio.io_error_quark(), code) for code in connection))


def normalize_server(value, allow_local=False):
    uri = urlsplit(value.strip().rstrip("/"))
    local = uri.hostname in {"localhost", "127.0.0.1", "::1"}
    if not uri.hostname or uri.username or uri.password or uri.query or uri.fragment:
        raise ValueError(_("Introdueix una adreça de Nextcloud vàlida."))
    if uri.scheme != "https" and not (allow_local and local and uri.scheme == "http"):
        raise ValueError(_("L'adreça de Nextcloud ha de començar per https://."))
    path = uri.path.split("/remote.php")[0].split("/index.php")[0]
    return urlunsplit((uri.scheme, uri.netloc, path.rstrip("/"), "", ""))


def server_from_files_uri(value):
    uri = urlsplit(value)
    scheme = {"davs": "https", "dav": "http"}.get(uri.scheme, uri.scheme)
    host = uri.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    if uri.port:
        host += f":{uri.port}"
    return normalize_server(urlunsplit((scheme, host, uri.path, "", "")))


def available_accounts():
    """Enumerate non-secret metadata using GOA's stable D-Bus API."""
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        objects = bus.call_sync(GOA, ROOT, "org.freedesktop.DBus.ObjectManager", "GetManagedObjects",
                                None, None, Gio.DBusCallFlags.NONE, 8000, None).unpack()[0]
    except GLib.Error:
        raise ValueError(_("No s'ha pogut accedir als Comptes en línia de GNOME.")) from None
    result = []
    for path, interfaces in objects.items():
        properties = interfaces.get(ACCOUNT, {})
        if properties.get("ProviderType") not in {"owncloud", "nextcloud"}:
            continue
        files = interfaces.get(GOA + ".Files", {})
        if not files.get("Uri") or GOA + ".PasswordBased" not in interfaces:
            continue
        try:
            server = server_from_files_uri(files["Uri"])
        except ValueError:
            continue
        result.append({"id": properties["Id"], "path": path, "server": server,
                       "username": properties["Identity"],
                       "title": properties.get("PresentationIdentity") or properties["Identity"],
                       "attention": properties.get("AttentionNeeded", False)})
    return result


def open_accounts_settings():
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    parameters = GLib.Variant("(sava{sv})", ("launch-panel", [GLib.Variant("(sav)", ("online-accounts", []))], {}))
    bus.call("org.gnome.Settings", "/org/gnome/Settings", "org.freedesktop.Application",
             "ActivateAction", parameters, None, Gio.DBusCallFlags.NONE, -1, None, None, None)


@dataclass
class Account:
    server: str
    username: str
    password: str = field(repr=False)
    goa_id: str = ""

    @staticmethod
    def selected_id():
        path = CONFIG_DIR / "account.json"
        return json.loads(path.read_text()).get("account_id") if path.exists() else None

    @classmethod
    def from_goa(cls, account_id):
        info = next((a for a in available_accounts() if a["id"] == account_id), None)
        if not info:
            raise ValueError(_("Aquest compte ja no és als Comptes en línia de GNOME."))
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            try:
                bus.call_sync(GOA, info["path"], ACCOUNT, "EnsureCredentials", None, None,
                              Gio.DBusCallFlags.NONE, 30000, None)
            except GLib.Error as error:
                if not network_failure(error):
                    raise
                # A transient GOA network check must not hide its stored password.
                # Deck still authenticates every HTTPS request with that credential.
            reply = bus.call_sync(GOA, info["path"], GOA + ".PasswordBased", "GetPassword",
                                  GLib.Variant("(s)", ("password",)), None,
                                  Gio.DBusCallFlags.NONE, 15000, None)
            password = reply.unpack()[0]
        except GLib.Error as error:
            if network_failure(error):
                raise ValueError(_("No s'ha pogut verificar el compte per un problema de connexió. Torna-ho a provar.")) from None
            raise ValueError(_("Cal revisar l'accés a Nextcloud a Configuració → Comptes en línia.")) from None
        if not password:
            raise ValueError(_("GNOME no ha proporcionat les credencials del compte."))
        return cls(info["server"], info["username"], password, info["id"])

    @classmethod
    def load(cls):
        accounts = available_accounts()
        path = CONFIG_DIR / "account.json"
        settings = json.loads(path.read_text()) if path.exists() else {}
        if settings.get("account_id"):
            return cls.from_goa(settings["account_id"])
        if len(accounts) == 1:
            if settings.get("server") and settings["server"] != accounts[0]["server"]:
                raise ValueError(_("Selecciona el compte de Nextcloud que vols utilitzar."))
            return cls.from_goa(accounts[0]["id"])
        return None

    def save(self):
        if not self.goa_id:
            raise ValueError(_("Selecciona un compte de Nextcloud dels Comptes en línia de GNOME."))
        directory = private_dir(CONFIG_DIR)
        temporary = directory / "account.json.tmp"
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump({"backend": "goa", "account_id": self.goa_id}, stream)
        os.replace(temporary, directory / "account.json")
