# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""A bounded worker belonging to one visible Talk dialog and one account."""
from concurrent.futures import ThreadPoolExecutor
from gi.repository import GLib
from .deck import DeckError
from .i18n import _, saved_error


class DialogWorker:
    def __init__(self, dialog, window, name='campbase-talk'):
        self.dialog, self.window = dialog, window
        self.api = window.engine.api
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=name)
        self.closed = False
        self.jobs = 0
        dialog.connect('closed', self.close)

    def active(self):
        return not self.closed and self.api is self.window.engine.api

    @property
    def busy(self):
        return self.jobs > 0

    def run(self, action, done, *, queue=False):
        if (self.busy and not queue) or not self.active():
            return False
        self.jobs += 1
        def deliver(result, error):
            self.jobs -= 1
            if self.active():
                done(result, error)
            return GLib.SOURCE_REMOVE
        def task():
            if not self.active():
                return
            try:
                result, error = action(), None
            except DeckError as exc:
                result, error = None, saved_error(str(exc))
            except Exception:
                result, error = None, _("No s'ha pogut completar l'operació.")
            GLib.idle_add(deliver, result, error)
        self.executor.submit(task)
        return True

    def close(self, *_unused):
        self.closed = True
        self.executor.shutdown(wait=False, cancel_futures=True)
