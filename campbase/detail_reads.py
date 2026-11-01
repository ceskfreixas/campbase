# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded in-memory previews and cancellable reads scoped to one card view."""
from collections import OrderedDict
import copy
import json
import time
import weakref


class DetailCache:
    def __init__(self, capacity=16, lifetime=60):
        self.capacity, self.lifetime = capacity, lifetime
        self.api = lambda: None
        self.items = OrderedDict()

    def select(self, api):
        if api is None or self.api() is not api:
            self.items.clear()
            self.api = weakref.ref(api) if api is not None else lambda: None

    def get(self, api, key):
        self.select(api)
        value = self.items.get(key)
        if value is None:
            return None
        saved, data = value
        if time.monotonic()-saved >= self.lifetime:
            self.items.pop(key)
            return None
        self.items.move_to_end(key)
        return copy.deepcopy(data)

    def put(self, api, key, data):
        self.select(api)
        if api is None:
            return
        if len(json.dumps(data).encode()) > 256*1024:
            return
        self.items[key] = (time.monotonic(), copy.deepcopy(data))
        self.items.move_to_end(key)
        while len(self.items) > self.capacity:
            self.items.popitem(last=False)

    def discard(self, api, prefix):
        self.select(api)
        for key in list(self.items):
            if key[:len(prefix)] == prefix:
                self.items.pop(key)


class DetailReads:
    def __init__(self, engine):
        self.engine, self.api = engine, engine.api
        self.closed, self.generation, self.future = False, 0, None

    def bind(self):
        if (self.api is None and self.engine.api is not None and not self.closed
                and not self.engine.closed and not self.engine.account_changing):
            self.invalidate()
            self.api = self.engine.api

    def current(self):
        return (not self.closed and not self.engine.closed and not self.engine.account_changing
                and self.api is self.engine.api)

    def invalidate(self):
        self.generation += 1
        if self.future:
            self.future.cancel()
            self.future = None

    def run(self, action, done):
        self.bind()
        self.invalidate()
        generation = self.generation
        def valid():
            return self.current() and generation == self.generation
        def deliver(result, error):
            if valid():
                self.future = None
                done(result, error)
        self.future = self.engine.run_read(action, deliver, current=valid)
        return self.future

    def close(self, *_unused):
        self.closed = True
        self.invalidate()
