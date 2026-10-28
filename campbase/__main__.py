# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
import argparse
import sys
import tempfile
from pathlib import Path

from .i18n import configure, saved_preference, _
configure('auto' if '--demo' in sys.argv else saved_preference(), native=True)

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from . import APP_ID
from .storage import Store
from .window import Window


def demo_snapshot():
    cards = [(_("Triatge"), [_("Una idea per al projecte"), _("Disseny de la portada"), _("Revisió dels textos"), _("Proposta de col·laboració")]),
             (_("En preparació"), [_("Preparar la primera versió"), _("Documentació de la comunitat")]),
             (_("Per implementar"), [_("Sincronització amb Deck"), _("Disseny de la icona")]), (_("Fet"), [_("Triar el nom: Campbase")])]
    stacks = []
    card_id = 100
    for stack_id, (title, names) in enumerate(cards, 1):
        rows = []
        for order, name in enumerate(names):
            card_id += 1
            rows.append({"id": card_id, "stackId": stack_id, "boardId": 1, "title": name,
                         "description": _("Un espai compartit per concretar la idea i fer-la avançar."),
                         "order": order, "labels": [], "archived": False})
        stacks.append({"id": stack_id, "title": title, "order": stack_id, "cards": rows})
    return {"boards": [{"id": 1, "title": _("El nostre campament"), "color": "3584e4", "archived": False}], "stacks": {"1": stacks}}


class Application(Adw.Application):
    def __init__(self, demo=False, quit_after=0):
        super().__init__(application_id=APP_ID + (".Demo" if demo else ""),
                         flags=Gio.ApplicationFlags.NON_UNIQUE if demo else Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.demo = demo
        self.quit_after = quit_after
        self.window = None
        self.temporary = tempfile.TemporaryDirectory(prefix="campbase-demo-") if demo else None

    def do_activate(self):
        if not self.window:
            provider = Gtk.CssProvider()
            provider.load_from_path(str(Path(__file__).with_name("style.css")))
            Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            local_icons = Path(__file__).resolve().parents[1] / "data/icons"
            if local_icons.exists():
                Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).add_search_path(str(local_icons))
            store = Store(self.temporary.name if self.temporary else None)
            if self.demo:
                store.put("snapshot", demo_snapshot())
                store.set_setting("sidebar", True)
            self.window = Window(self, store, demo=self.demo)
            if self.quit_after:
                GLib.timeout_add_seconds(self.quit_after, self.quit)
        self.window.present()


def main():
    parser = argparse.ArgumentParser(description=_("Campbase · Taulers kanban per a GNOME"))
    parser.add_argument("--demo", action="store_true", help=_("Obre un tauler de demostració sense dades reals ni connexió"))
    parser.add_argument("--quit-after", type=int, default=0, help=argparse.SUPPRESS)
    args = parser.parse_args()
    GLib.set_application_name("Campbase")
    GLib.set_prgname("campbase")
    Gtk.Window.set_default_icon_name(APP_ID)
    return Application(args.demo, args.quit_after).run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
