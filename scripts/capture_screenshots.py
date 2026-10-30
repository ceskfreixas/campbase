#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Capture only synthetic Campbase windows on an isolated Xvfb display."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import sys
import tempfile
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--language', choices=['en', 'ca', 'es', 'gl', 'eu', 'oc'], default='en')
parser.add_argument('--output', type=Path, default=Path('docs/catalog/screenshots'))
args = parser.parse_args()
# Deliberately reject normal desktop displays and all real-account startup paths.
if os.environ.get('DISPLAY') != ':98' or os.environ.get('CAMPBASE_SCREENSHOT_FIXTURE') != '1':
    parser.error('Use the dedicated Xvfb :98 display with CAMPBASE_SCREENSHOT_FIXTURE=1.')
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from campbase.i18n import configure
configure(args.language, user_choice=True, native=True)
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('GdkX11', '4.0')
from gi.repository import GdkX11
from gi.repository import Adw, Gdk, GLib, Gtk
from campbase.storage import Store
from campbase.window import Window
from campbase.card_dialog import CardDialog


def settle():
    until = time.monotonic() + .7
    while time.monotonic() < until:
        while GLib.MainContext.default().pending():
            GLib.MainContext.default().iteration(False)
        time.sleep(.005)


def capture(window, path):
    """Capture only this synthetic X11 surface, including its native shadow."""
    settle()
    surface = window.get_surface()
    width, height = surface.get_width(), surface.get_height()
    xlib = ctypes.CDLL('libX11.so.6')

    class XImage(ctypes.Structure):
        _fields_ = [('width', ctypes.c_int), ('height', ctypes.c_int),
                    ('xoffset', ctypes.c_int), ('format', ctypes.c_int),
                    ('data', ctypes.c_void_p), ('byte_order', ctypes.c_int),
                    ('bitmap_unit', ctypes.c_int), ('bitmap_bit_order', ctypes.c_int),
                    ('bitmap_pad', ctypes.c_int), ('depth', ctypes.c_int),
                    ('bytes_per_line', ctypes.c_int), ('bits_per_pixel', ctypes.c_int)]

    xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
    xlib.XOpenDisplay.restype = ctypes.c_void_p
    xlib.XGetImage.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
                              ctypes.c_uint, ctypes.c_uint, ctypes.c_ulong, ctypes.c_int]
    xlib.XGetImage.restype = ctypes.POINTER(XImage)
    xlib.XDestroyImage.argtypes = [ctypes.POINTER(XImage)]
    xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]
    display = xlib.XOpenDisplay(b':98')
    assert display and sys.byteorder == 'little'
    picture = None
    try:
        picture = xlib.XGetImage(display, surface.get_xid(), 0, 0, width, height,
                                ctypes.c_ulong(-1).value, 2)
        assert picture and picture.contents.depth == 32 and picture.contents.bits_per_pixel == 32
        stride = picture.contents.bytes_per_line
        pixels = ctypes.string_at(picture.contents.data, stride * height)
        texture = Gdk.MemoryTexture.new(width, height, Gdk.MemoryFormat.B8G8R8A8_PREMULTIPLIED,
                                        GLib.Bytes.new(pixels), stride)
        assert texture.save_to_png(str(path))
    finally:
        if picture:
            xlib.XDestroyImage(picture)
        xlib.XCloseDisplay(display)
    print(f'Captured {path.name}: {width} x {height}', flush=True)


copy = json.loads((root / 'docs/catalog/copy.json').read_text())[args.language]
app = Adw.Application(application_id='cat.ceskfreixas.Campbase.CatalogCapture')
app.register(None)
settings = Gtk.Settings.get_default()
settings.set_property('gtk-decoration-layout', ':close')
settings.set_property('gtk-font-name', 'Adwaita Sans 11')
Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).add_search_path(str(root / 'data/icons'))
css = Gtk.CssProvider()
css.load_from_path(str(root / 'campbase/style.css'))
Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
args.output.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='campbase-catalog-') as directory:
    store = Store(directory)
    cards = []
    for i, title in enumerate(copy['cards']):
        stack = 1 if i < 2 else 2 if i < 5 else 3 if i < 7 else 4
        cards.append({'id': 101+i, 'boardId': 1, 'stackId': stack, 'title': title,
                      'description': copy['description'] if i == 2 else '',
                      'order': i, 'labels': [], 'archived': False, 'attachmentCount': 0})
    stacks = [{'id': i, 'boardId': 1, 'title': title, 'order': i,
               'cards': [c for c in cards if c['stackId'] == i]}
              for i, title in enumerate(copy['columns'], 1)]
    store.put('snapshot', {'boards': [{'id': 1, 'title': copy['board'], 'color': '2190a4', 'archived': False}], 'stacks': {'1': stacks}})
    store.put('board_metadata', {'1': {'description': copy['subtitle'], 'icon': 'system-users-symbolic'}})
    for key, value in {'width': 1000, 'height': 700, 'columns_per_row': 3, 'sidebar': False, 'startup_sidebar': False, 'theme': 'light'}.items():
        store.set_setting(key, value)
    window = Window(app, store, demo=True)
    assert window.demo and window.account is None and window.engine.api is None
    window.present()
    settle()
    window.set_focus(None)
    capture(window, args.output / f'{args.language}-board-light.png')
    editor = CardDialog(window, 2, window.find_card(103))
    editor.present(window)
    settle()
    window.set_focus(None)
    capture(window, args.output / f'{args.language}-card-light.png')
    editor.close()
    settle()
    window.set_theme('dark', persist=False)
    window.set_focus(None)
    capture(window, args.output / f'{args.language}-board-dark.png')
    window.close()
    settle()
