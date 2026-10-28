# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Private local cache and durable outbox. No passwords are stored here."""
from .i18n import _, ngettext, canonical_message
import copy
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


def private_dir(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    return path


DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "campbase"
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "campbase"


class Store:
    def __init__(self, directory=None):
        self.directory = private_dir(directory or DATA_DIR)
        self.path = self.directory / "cache.sqlite3"
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL,
                    payload TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
                    error TEXT NOT NULL DEFAULT '', created TEXT DEFAULT CURRENT_TIMESTAMP);
            """)
            db.execute("UPDATE outbox SET state='blocked',error=? WHERE state='sending'",
                       (_("L'enviament es va interrompre. Revisa Deck abans de tornar a crear aquesta targeta."),))
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, key, default=None):
        with self.connect() as db:
            row = db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, key, value):
        with self.connect() as db:
            self._put(db, key, value)

    def record_creator(self, key, value):
        # Local creations and background activity may arrive concurrently.
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT value FROM state WHERE key='creators'").fetchone()
            records = json.loads(row[0]) if row else {}
            records[key] = value
            self._put(db, 'creators', records)

    def remove_card(self, board_id, card_id):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT value FROM state WHERE key='snapshot'").fetchone()
            if row:
                snapshot = json.loads(row[0])
                for stack in snapshot.get('stacks', {}).get(str(board_id), []):
                    stack['cards'] = [card for card in stack.get('cards') or [] if card['id'] != card_id]
                self._put(db, 'snapshot', snapshot)
            for row in db.execute('SELECT id,payload FROM outbox').fetchall():
                if json.loads(row['payload']).get('card_id') == card_id:
                    db.execute("UPDATE outbox SET state='blocked',error=? WHERE id=?",
                               (_("La targeta s'ha esborrat de Deck. Els canvis locals s'han conservat."), row['id']))

    def remove_board(self, board_id):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT value FROM state WHERE key='snapshot'").fetchone()
            stack_ids = set()
            if row:
                snapshot = json.loads(row[0])
                stack_ids = {str(stack['id']) for stack in snapshot.get('stacks', {}).get(str(board_id), [])}
                snapshot['boards'] = [board for board in snapshot.get('boards', []) if board['id'] != board_id]
                snapshot.get('stacks', {}).pop(str(board_id), None)
                self._put(db, 'snapshot', snapshot)
            row = db.execute("SELECT value FROM state WHERE key='board_metadata'").fetchone()
            if row:
                metadata = json.loads(row[0]);metadata.pop(str(board_id), None)
                self._put(db, 'board_metadata', metadata)
            row = db.execute("SELECT value FROM state WHERE key='settings'").fetchone()
            if row:
                settings = json.loads(row[0])
                for key in ('board_id', 'startup_board_id'):
                    if settings.get(key) == board_id:
                        settings[key] = None
                settings['colors'] = {key: value for key, value in settings.get('colors', {}).items() if key not in stack_ids}
                settings['archived_columns'] = [key for key in settings.get('archived_columns', []) if key not in stack_ids]
                settings['archived_overrides'] = {key: value for key, value in settings.get('archived_overrides', {}).items()
                                                 if key not in stack_ids}
                self._put(db, 'settings', settings)
            for row in db.execute('SELECT id,payload FROM outbox').fetchall():
                if json.loads(row['payload']).get('board_id') == board_id:
                    db.execute("UPDATE outbox SET state='blocked',error=? WHERE id=?",
                               (_("El tauler s'ha esborrat de Deck. Els canvis locals s'han conservat."), row['id']))

    @staticmethod
    def _put(db, key, value):
        db.execute("INSERT OR REPLACE INTO state VALUES (?,?)", (key, json.dumps(value)))

    def settings(self):
        return self.get("settings", {"sidebar": False, "theme": "system", "width": 1240, "height": 850})

    def set_setting(self, key, value):
        with self.connect() as db:
            row = db.execute("SELECT value FROM state WHERE key='settings'").fetchone()
            settings = json.loads(row[0]) if row else self.settings()
            settings[key] = value
            self._put(db, "settings", settings)

    def set_archived_default(self, visible):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT value FROM state WHERE key='settings'").fetchone()
            settings = json.loads(row[0]) if row else self.settings()
            settings.update(show_archived_default=bool(visible), archived_overrides={})
            settings.pop('archived_columns', None)
            self._put(db, 'settings', settings)

    def cache_board(self, board):
        with self.connect() as db:
            row = db.execute("SELECT value FROM state WHERE key='snapshot'").fetchone()
            if row:
                snapshot = json.loads(row[0])
                snapshot['boards'] = [board if item['id'] == board['id'] else item for item in snapshot['boards']]
                self._put(db, 'snapshot', snapshot)

    def cache_label(self, board_id, label):
        with self.connect() as db:
            row = db.execute("SELECT value FROM state WHERE key='snapshot'").fetchone()
            if not row:
                return
            snapshot = json.loads(row[0])
            for board in snapshot["boards"]:
                if board["id"] == board_id:
                    labels = {item["id"]: item for item in board.get("labels") or []}
                    labels[label["id"]] = label
                    board["labels"] = list(labels.values())
            self._put(db, "snapshot", snapshot)

    def operations(self):
        with self.connect() as db:
            return self._operations(db)

    @staticmethod
    def _operations(db):
        rows = db.execute("SELECT * FROM outbox ORDER BY id").fetchall()
        return [dict(row) | {"payload": json.loads(row["payload"])} for row in rows]

    def enqueue(self, kind, payload, undo=None):
        with self.connect() as db:
            op_id = db.execute("INSERT INTO outbox(kind,payload) VALUES (?,?)", (kind, json.dumps(payload))).lastrowid
            if undo:
                self._put(db, 'undo_action', dict(undo, operation_id=op_id, kind=kind,
                    board_id=payload['board_id'], card_id=payload['card_id'], payload=payload, attempted=False))
            return op_id

    def mark_undo_attempted(self, op_id):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT value FROM state WHERE key='undo_action'").fetchone()
            action = json.loads(row[0]) if row else None
            if action and action['operation_id'] == op_id:
                action['attempted'] = True
                self._put(db, 'undo_action', action)

    def checkpoint_move(self, op_id, fields):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT payload FROM outbox WHERE id=? AND kind='move'", (op_id,)).fetchone()
            if row is None:
                return None
            payload = json.loads(row[0]) | fields
            db.execute('UPDATE outbox SET payload=? WHERE id=?', (json.dumps(payload), op_id))
            row = db.execute("SELECT value FROM state WHERE key='undo_action'").fetchone()
            action = json.loads(row[0]) if row else None
            if action and action['operation_id'] == op_id:
                action['payload'] = payload
                self._put(db, 'undo_action', action)
            return payload

    def block(self, op_id, error):
        with self.connect() as db:
            db.execute("UPDATE outbox SET state='blocked',error=? WHERE id=?", (canonical_message(str(error)), op_id))

    def begin_send(self, op_id):
        with self.connect() as db:
            db.execute("UPDATE outbox SET state='sending' WHERE id=?", (op_id,))

    def discard(self, op_id):
        # Dependent edits to an unsent card must not remain orphaned.
        with self.connect() as db:
            db.execute("DELETE FROM outbox WHERE id=?", (op_id,))
            rows = db.execute("SELECT id,payload FROM outbox").fetchall()
            for row in rows:
                if json.loads(row["payload"]).get("card_id") == -op_id:
                    db.execute("DELETE FROM outbox WHERE id=?", (row["id"],))

    def retry(self, op_id, force=False):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM outbox WHERE id=?", (op_id,)).fetchone()
            if row:
                payload = json.loads(row[0])
                payload["force"] = force
                db.execute("UPDATE outbox SET state='pending',error='',payload=? WHERE id=?", (json.dumps(payload), op_id))

    def record_image_upload(self, op_id, token, url):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM outbox WHERE id=?", (op_id,)).fetchone()
            if row:
                payload = json.loads(row[0])
                payload.setdefault("uploaded_images", {})[token] = url
                db.execute("UPDATE outbox SET payload=? WHERE id=?", (json.dumps(payload), op_id))
                # Later offline edits used the local URI as their base. Rebase
                # that representation after upload, without changing the text.
                for later in db.execute("SELECT id,payload FROM outbox WHERE id>?", (op_id,)).fetchall():
                    dependent = json.loads(later["payload"])
                    if dependent.get("card_id") != payload.get("card_id"):
                        continue
                    for field in ("changes", "base"):
                        description = dependent.get(field, {}).get("description")
                        if isinstance(description, str):
                            dependent[field]["description"] = description.replace("bivac-image://"+token, url)
                    db.execute("UPDATE outbox SET payload=? WHERE id=?", (json.dumps(dependent), later["id"]))

    @staticmethod
    def _record_notice(db, notice):
        row = db.execute("SELECT value FROM state WHERE key='local_notices'").fetchone()
        notices = json.loads(row[0]) if row else []
        if not any(item['key'] == notice['key'] for item in notices):
            Store._put(db, 'local_notices', [*notices, notice][-300:])

    def record_notice(self, notice):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._record_notice(db, notice)

    def dismiss_notice(self, notice):
        """Hide one confirmed removal atomically across all inbox sources."""
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT value FROM state WHERE key='updates_hidden'").fetchone()
            hidden = json.loads(row[0]) if row else []
            self._put(db, 'updates_hidden', [*dict.fromkeys([*hidden, notice['key']])][-2000:])
            row = db.execute("SELECT value FROM state WHERE key='local_notices'").fetchone()
            if row:
                self._put(db, 'local_notices', [item for item in json.loads(row[0]) if item['key'] != notice['key']])
            if notice.get('notice_id'):
                row = db.execute("SELECT value FROM state WHERE key='updates'").fetchone()
                if row:
                    state = json.loads(row[0])
                    state['notifications'] = [item for item in state.get('notifications', [])
                                              if item.get('notification_id') != notice['notice_id']]
                    self._put(db, 'updates', state)

    def complete(self, operation, card, stage_followups=False, notice=None):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT value FROM state WHERE key='undo_action'").fetchone()
            action = json.loads(row[0]) if row else None
            if action and (action['operation_id'] == operation['id'] or
                           operation['kind'] == 'create' and action['card_id'] == -operation['id']):
                action['card_id'] = card['id']
                self._put(db, 'undo_action', action)
            if notice:
                self._record_notice(db, notice)
            row = db.execute("SELECT value FROM state WHERE key='snapshot'").fetchone()
            snapshot = json.loads(row[0]) if row else {"boards": [], "stacks": {}}
            board_id = operation["payload"]["board_id"]
            if operation["kind"] == "board_update":
                snapshot["boards"] = [card if b["id"] == board_id else b for b in snapshot["boards"]]
                self._put(db, "snapshot", snapshot)
                db.execute("DELETE FROM outbox WHERE id=?", (operation["id"],))
                return
            stacks = snapshot["stacks"].get(str(board_id), [])
            for stack in stacks:
                stack["cards"] = [c for c in stack.get("cards", []) if c["id"] != card["id"]]
            for stack in stacks:
                if stack["id"] == card["stackId"]:
                    stack.setdefault("cards", []).append(card)
                    if operation['kind'] == 'move' and operation['payload'].get('archive_order_done'):
                        orders = {entry['id']: entry for entry in operation['payload'].get('archive_order') or []}
                        for peer in stack['cards']:
                            entry = orders.get(peer['id'])
                            if entry and peer.get('archived') and peer.get('order') == entry['base']:
                                peer['order'] = entry['order']
            self._put(db, "snapshot", snapshot)
            if operation["kind"] == "create":
                rows = db.execute("SELECT id,payload FROM outbox WHERE id>?", (operation["id"],)).fetchall()
                for row in rows:
                    payload = json.loads(row["payload"])
                    if payload.get("card_id") == -operation["id"]:
                        payload["card_id"] = card["id"]
                        db.execute("UPDATE outbox SET payload=? WHERE id=?", (json.dumps(payload), row["id"]))
            if stage_followups:
                payload = operation["payload"]
                changes, base = {}, {}
                if payload.get("images"):
                    changes["description"] = payload.get("description", "")
                    base["description"] = card.get("description") or ""
                if payload.get("assignedUsers"):
                    changes["assignedUsers"] = payload["assignedUsers"]
                    base["assignedUsers"] = card.get("assignedUsers") or []
                if payload.get("labels"):
                    changes["labels"] = payload["labels"]
                    base["labels"] = card.get("labels") or []
                updated = {"board_id": board_id, "card_id": card["id"], "stack_id": card["stackId"],
                           "changes": changes, "base": base, "images": payload.get("images", [])}
                db.execute("UPDATE outbox SET kind='update',payload=?,state='pending' WHERE id=?", (json.dumps(updated), operation["id"]))
            else:
                db.execute("DELETE FROM outbox WHERE id=?", (operation["id"],))

    def view(self):
        from .comment_counts import decorate
        with self.connect() as db:
            db.execute('BEGIN')
            state = {row['key']: row['value'] for row in db.execute(
                "SELECT key,value FROM state WHERE key IN ('snapshot','comment_counts')")}
            operations = self._operations(db)
        snapshot = json.loads(state.get('snapshot', '{"boards":[],"stacks":{}}'))
        return decorate(self.project(snapshot, operations), json.loads(state.get('comment_counts', '{}')))

    def comment_count(self, board_id, card_id, *, count=None, delta=0, text_count=None, reaction_delta=0):
        """Refresh just a confirmed comment count without replacing card drafts."""
        from .comment_counts import change_count
        change_count(self, board_id, card_id, count=count, delta=delta,
                     text_count=text_count, reaction_delta=reaction_delta)

    def comment_summary(self, board_id, card_id, total, text, revision):
        from .comment_counts import confirm_summary
        return confirm_summary(self, board_id, card_id, total, text, revision)

    @staticmethod
    def project(snapshot, operations):
        snapshot = copy.deepcopy(snapshot)
        for op in operations:
            p = op["payload"]
            if op["kind"] == "board_update":
                for board in snapshot["boards"]:
                    if board["id"] == p["board_id"]:
                        board.update(p["changes"])
                continue
            stacks = snapshot["stacks"].get(str(p["board_id"]), [])
            card = next((c for s in stacks for c in s.get("cards", []) if c["id"] == p.get("card_id")), None)
            if op["kind"] == "create":
                card = {"id": -op["id"], "stackId": p["stack_id"], "title": p["title"],
                        "description": p.get("description", ""), "duedate": p.get("duedate"),
                        "order": p.get("order", 999), "labels": p.get("labels", []), "assignedUsers": p.get("assignedUsers", []), "owner": p.get("owner"), "archived": False}
                target = next((s for s in stacks if s["id"] == p["stack_id"]), None)
                if target:
                    target.setdefault("cards", []).append(card)
            elif card and op["kind"] == "move":
                for stack in stacks:
                    stack["cards"] = [c for c in stack.get("cards", []) if c["id"] != card["id"]]
                target = next((s for s in stacks if s["id"] == p["target_stack"]), None)
                if target:
                    card["stackId"] = p["target_stack"]
                    if 'archived' in p:
                        card['archived'] = p['archived']
                    peers = sorted((child for child in target.get('cards', [])
                                    if bool(child.get('archived')) == bool(card.get('archived'))),
                                   key=lambda child:(child.get('order',0),child['id']))
                    peers.insert(min(p['order'],len(peers)),card)
                    others = [child for child in target.get('cards', [])
                              if bool(child.get('archived')) != bool(card.get('archived'))]
                    for index, child in enumerate(peers):
                        child["order"] = index
                    target['cards'] = sorted(peers+others,key=lambda child:(bool(child.get('archived')),child.get('order',0),child['id']))
            elif card and op["kind"] in {"update", "archive"}:
                card.update(p["changes"])
            if card:
                card["_pending"] = True
                card["_blocked"] = op["state"] == "blocked"
        return snapshot
