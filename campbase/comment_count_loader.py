# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Bounded background reads never hold the serialized card-writing worker."""
import time
import threading
from concurrent.futures import ThreadPoolExecutor


class CommentCountLoader:
    def __init__(self, window):
        self.window = window
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='campbase-counts')
        self.pending = set()
        self.failed = {}
        self.lock = threading.Lock()
        self.closed = False
        self.last_refresh = None
        self.visible_ids = frozenset()

    def refresh(self, snapshot, board_id):
        api = self.window.engine.api
        if self.closed or self.window.demo or api is None or self.window.engine.account_changing:
            return
        now = time.time()
        stacks = snapshot.get('stacks', {}).get(str(board_id), [])
        cards = [card for stack in stacks for card in stack.get('cards') or []
                 if isinstance(card.get('commentsCount'), int) and card['commentsCount'] > 0]
        signature = (id(api), board_id, self.window.query, self.window.only_mine, int(now//60),
                     tuple((card['id'], card['commentsCount']) for card in cards))
        if signature == self.last_refresh:
            return
        self.last_refresh = signature
        visible = {card['id'] for stack in stacks for card in self.window.filtered_cards(stack)}
        self.visible_ids = frozenset(visible)
        cards = [card for card in cards if card['id'] in visible]
        if not cards:
            return
        records = self.window.store.get('comment_counts', {})
        for card in cards:
            total = card['commentsCount']
            version = (total, None)
            cached = records.get(str(card['id']), {})
            if cached.get('total') == total and now-cached.get('checked', 0) < 300:
                continue
            key = (api.server, api.username, card['id'])
            with self.lock:
                failed_version, retry = self.failed.get(key, (None, 0))
                if key in self.pending or failed_version == version and now < retry:
                    continue
                if len(self.pending) >= 2:
                    break
                self.pending.add(key)
            self.executor.submit(self.read, api, board_id, card['id'], version, key)

    def read(self, api, board_id, card_id, version, key):
        try:
            result = api.comment_summary(card_id, version[0], keep_reading=lambda:
                not self.closed and api is self.window.engine.api and board_id == self.window.board_id
                and card_id in self.visible_ids)
        except Exception:
            result = None
        self.window.engine.dispatch(self.finished, api, board_id, card_id, version, key, result)

    def finished(self, api, board_id, card_id, version, key, result):
        with self.lock:
            self.pending.discard(key)
            self.last_refresh = None
            if result is None:
                self.failed[key] = (version, time.time()+60)
        if self.closed or api is not self.window.engine.api or self.window.engine.account_changing:
            return False
        if result is not None:
            self.window.store.comment_summary(board_id, card_id, version[0], result, version[1])
        self.window.engine.notify()
        return False

    def close(self):
        self.closed = True
        self.executor.shutdown(wait=False, cancel_futures=True)
