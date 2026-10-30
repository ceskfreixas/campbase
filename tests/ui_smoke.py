# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Run under an isolated Xvfb display, with temporary synthetic data."""
import tempfile
import time
from pathlib import Path
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk

from campbase.__main__ import demo_snapshot
from campbase.dialogs import AccountDialog, CardDialog, PendingDialog, Preferences
from campbase.storage import Store
from campbase.window import Window
from campbase.project import ProjectDialog
from gi.repository import Gio
from campbase.widgets import Column, Card


def settle():
    deadline = time.monotonic() + .3
    while time.monotonic() < deadline:
        while GLib.MainContext.default().pending():
            GLib.MainContext.default().iteration(False)
        time.sleep(.005)


app = Adw.Application(application_id="cat.ceskfreixas.Campbase.UITest")
app.register(None)
Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).add_search_path(str(Path(__file__).resolve().parents[1]/"data/icons"))
provider = Gtk.CssProvider()
provider.load_from_path(str(Path(__file__).resolve().parents[1] / "campbase/style.css"))
Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
with tempfile.TemporaryDirectory() as path:
    store = Store(path)
    store.put("snapshot", demo_snapshot())
    store.set_setting("sidebar", True)
    window = Window(app, store, demo=True)
    window.present()
    settle()
    for width in [640, 900, 1240, 1640]:
        window.set_default_size(width, 1000)
        settle()
        triage = next(child for child in [window.board_body.get_first_child().get_next_sibling()] if isinstance(child, Column))
        flow = triage.get_first_child().get_next_sibling()
        children = []
        child = flow.get_first_child()
        while child:
            children.append(child)
            child = child.get_next_sibling()
        assert len(children) == 4
        for child in children:
            ok, bounds = child.compute_bounds(flow)
            assert ok and bounds.origin.x >= 0 and bounds.origin.x + bounds.size.width <= flow.get_width() + 1
        workflow = triage.get_next_sibling()
        child = workflow.get_first_child()
        while child:
            column = child.get_child()
            ok, bounds = column.get_last_child().compute_bounds(column)
            assert ok and bounds.origin.y + bounds.size.height <= column.get_height() + 1
            child = child.get_next_sibling()
        print("PASS adaptive triage", width, "window", window.get_width(), "flow", flow.get_width(), flush=True)
    assert "F5" in app.get_accels_for_action("win.sync")
    shown = window.toggle_sidebar.get_icon_name()
    window.split.set_show_sidebar(False)
    assert window.toggle_sidebar.get_icon_name() != shown
    window.search_button.emit("clicked")
    assert window.search.get_visible()
    window.search_button.emit("clicked")
    assert not window.search.get_visible()
    print("PASS sidebar icon, search toggle and F5", flush=True)
    project = ProjectDialog(window, window.snapshot["boards"][0])
    project.present(window)
    settle()
    project.name.set_text("Projecte editat")
    project.description.get_buffer().set_text("Descripció nova")
    record = window.assets.import_file(Gio.File.new_for_path(str(Path(__file__).resolve().parents[1]/"data/icons/cat.ceskfreixas.Campbase.svg")), icon=True)
    project.metadata["image"] = record["path"]
    project.refresh_preview()
    project.changed()
    assert not project.get_can_close()
    project.save()
    settle()
    board_id = window.snapshot["boards"][0]["id"]
    assert window.snapshot["boards"][0]["title"] == "Projecte editat"
    assert store.get("board_metadata")[str(board_id)]["description"] == "Descripció nova"
    assert store.get("board_metadata")[str(board_id)]["image"].endswith(".svg")
    assert store.operations()[0]["kind"] == "board_update"
    store.discard(store.operations()[0]["id"])
    window.render()
    print("PASS project title, local description and SVG icon", flush=True)
    for dialog in [CardDialog(window, 1), CardDialog(window, 1, window.find_card(101)),
                   Preferences(window), AccountDialog(window), PendingDialog(window)]:
        dialog.present(window)
        settle()
        dialog.close()
        settle()
        print("PASS dialog", type(dialog).__name__, flush=True)
    editor = CardDialog(window, 1)
    editor.present(window)
    settle()
    editor.title_entry.set_text("Esborrany de prova")
    editor.description.get_buffer().set_text("Contingut que es conserva sense connexió")
    assert not editor.get_can_close()
    assert editor.save()
    settle()
    assert len(store.operations()) == 1
    created = next(c for s in window.stacks() for c in s["cards"] if c["id"] < 0)
    assert created["description"] == "Contingut que es conserva sense connexió"
    window.move_card(created, 3)
    settle()
    assert window.find_card(created["id"])["stackId"] == 3
    print("PASS editor saves and moves an offline draft", flush=True)
    window.split.set_show_sidebar(False)
    settle()
    assert store.settings()["sidebar"] is False
    window.render()
    assert window.split.get_show_sidebar() is False
    window.close()
    settle()
    print("PASS sidebar visibility persists", flush=True)
