# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Wait for actual native dialog presentation instead of animation guesses."""
import time
from gi.repository import GLib


def wait_until(condition, timeout=8):
    deadline = time.monotonic() + timeout
    context = GLib.MainContext.default()
    while time.monotonic() < deadline:
        while context.pending() and time.monotonic() < deadline:
            context.iteration(False)
        if condition():
            return
        time.sleep(.005)
    raise AssertionError('The native dialog did not reach the expected state')


def wait_presented(dialog):
    child = dialog.get_child()
    wait_until(lambda: dialog.get_mapped() and child.get_width() > 0 and child.get_height() > 0)
    frames = []
    def drawn(*_):
        frames.append(True)
        return len(frames) < 2
    callback = dialog.add_tick_callback(drawn)
    try:
        wait_until(lambda: len(frames) >= 2)
    finally:
        if len(frames) < 2:
            dialog.remove_tick_callback(callback)


def present(dialog, parent):
    dialog.present(parent)
    wait_presented(dialog)
