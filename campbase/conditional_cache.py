# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded per-account ETag cache. Mutations invalidate in-flight insertions."""
from collections import OrderedDict
import copy
import threading


class ConditionalCache:
    def __init__(self, max_bytes=16*1024*1024, max_entries=64):
        self.lock = threading.Lock()
        self.rows = OrderedDict()
        self.generation = 0
        self.max_bytes, self.max_entries = max_bytes, max_entries
        self.size = 0

    def get(self, key):
        with self.lock:
            row = self.rows.get(key)
            if row:
                self.rows.move_to_end(key)
            return self.generation, copy.deepcopy(row)

    def version(self):
        with self.lock:
            return self.generation

    def put(self, key, etag, data, size, generation):
        with self.lock:
            if generation != self.generation:
                return
            previous = self.rows.pop(key, None)
            if previous:
                self.size -= previous[2]
            if not etag or size > self.max_bytes:
                return
            self.rows[key] = (etag, copy.deepcopy(data), size)
            self.size += size
            while self.size > self.max_bytes or len(self.rows) > self.max_entries:
                _, old = self.rows.popitem(last=False)
                self.size -= old[2]

    def invalidate(self):
        with self.lock:
            self.rows.clear()
            self.size = 0
            self.generation += 1
