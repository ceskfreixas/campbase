# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""One serialized worker prevents card moves and edits racing each other."""
from .i18n import _, ngettext, saved_error
import threading
import time
import re
import shutil
from concurrent.futures import ThreadPoolExecutor

from .deck import Deck, DeckError, OfflineError, ConflictError
from .assets import Assets


class SyncEngine:
    def __init__(self, store, account=None, dispatch=None, changed=None):
        self.store = store
        self.api = Deck(account) if account else None
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="campbase-sync")
        self.updates_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="campbase-updates")
        self.account_changing = False
        self.dispatch = dispatch or (lambda fn, *args: fn(*args))
        self.changed = changed or (lambda: None)
        self.busy = False
        self.closed = False
        self.error = ""
        self._queued_sync = set()
        self._lock = threading.Lock()

    def notify(self):
        if not self.closed:
            self.dispatch(self.changed)

    def sync(self, *, automatic=False, read_only=False):
        if self.closed or self.account_changing:
            return None
        if automatic and not self.store.settings().get("auto_sync", True):
            return None
        if not self.api:
            self.error = _("Connecta el compte de Nextcloud per sincronitzar.")
            self.notify()
            return None
        with self._lock:
            if self.busy:
                self._queued_sync.add((automatic, read_only))
                return None
            self.busy = True
        self.notify()
        return self.executor.submit(self._sync, read_only)

    def _sync(self, read_only=False):
        try:
            self.api.refresh_auth()
            self.error = ""
            if not read_only:
                self._send_pending()
            snapshot = self.api.fetch(refresh_auth=False)
            self.store.put("snapshot", snapshot)
            self.notify()
            self.store.put("last_sync", time.time())
            # Optional feeds must not delay the next card edit or the sync state.
            self.refresh_updates()
        except DeckError as error:
            self.error = saved_error(str(error))
        except Exception:
            # Never include server payloads, credentials or private card text in logs.
            self.error = _("No s'ha pogut completar la sincronització. Els canvis locals es conserven.")
        finally:
            with self._lock:
                self.busy = False
                queued, self._queued_sync = self._queued_sync, set()
            self.notify()
            if queued:
                automatic_enabled = self.store.settings().get("auto_sync", True)
                allowed = [mode for mode in queued if not mode[0] or automatic_enabled]
                if allowed:
                    # A manual read never authorizes a queued automatic write.
                    automatic, read_only = min(allowed, key=lambda mode: (mode[1], mode[0]))
                    self.sync(automatic=automatic, read_only=read_only)

    def _send_pending(self):
        """Confirm local writes first, then refresh the complete workspace once."""
        blocked_cards, checked_boards = set(), set()
        for operation in self.store.operations():
            payload = operation["payload"]
            card_key = ("board", payload["board_id"]) if operation["kind"] == "board_update" else payload.get("card_id", -operation["id"])
            if operation["state"] != "pending" or card_key in blocked_cards:
                blocked_cards.add(card_key)
                continue
            # An earlier create may have remapped this operation's card ID.
            operation = self.store.operation(operation['id'])
            if not operation:
                continue
            creation_attempted = False
            try:
                if operation["kind"] == "create":
                    board_id = operation["payload"]["board_id"]
                    if board_id not in checked_boards:
                        # A failed preflight leaves an unsent create safe to retry.
                        self.api.check_board(board_id)
                        checked_boards.add(board_id)
                    self.store.begin_send(operation["id"])
                    creation_attempted = True
                if operation['kind'] in ('move', 'archive') and not payload.get('batch_archive'):
                    self.store.mark_undo_attempted(operation['id'])
                result = self.perform(operation)
                if operation["kind"] == "create":
                    from .collaboration import remember_creator
                    remember_creator(self.store, 'card', result['id'], result.get('owner') or self.api.username)
                if operation["kind"] == "create" and (operation["payload"].get("images") or operation["payload"].get("labels") or operation["payload"].get("assignedUsers")):
                    self.store.complete(operation, result, stage_followups=True)
                    self.notify()
                    operation = self.store.operation(operation['id'])
                    if operation is None:
                        continue
                    result = self.perform(operation)
                self.store.complete(operation, result)
                if not payload.get('batch_archive'):
                    self.notify()
            except OfflineError:
                if creation_attempted and operation["kind"] == "create":
                    self.store.block(operation["id"], _("No es pot confirmar si Deck ha creat la targeta. Obre Deck i comprova-ho abans de tornar-la a enviar."))
                raise
            except DeckError as error:
                self.store.block(operation["id"], str(error))
                blocked_cards.add(card_key)
                self.error = saved_error(str(error))

    def close(self):
        self.closed = True
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.updates_executor.shutdown(wait=False, cancel_futures=True)

    def refresh_updates(self, done=None, *, force=False):
        """Serialize inbox refresh/deletion separately from Deck card writes."""
        from .updates import collect_updates
        return self.run_updates(lambda api: collect_updates(
            api, self.store, self.store.get('snapshot', {}), force=force), done)

    def run_updates(self, action, done=None):
        if self.account_changing:
            return None
        return self._run(self.updates_executor, action, done)

    def perform(self, operation):
        p = operation["payload"]
        if operation["kind"] == "board_update":
            return self.api.update_board(p["board_id"], p["changes"], p.get("base"), p.get("force", False))
        if operation["kind"] == "create":
            description = re.sub(r'!\[((?:\\.|[^\]])*)\]\(bivac-image://[a-f0-9]{32}\)', r'[\1]', p.get("description", ""))
            return self.api.create_card(p["board_id"], p["stack_id"], p["title"], description, p.get("duedate"), p.get("order", 0))
        if p["card_id"] < 0:
            raise ConflictError(_("Primer cal enviar la targeta nova a Deck."))
        if operation["kind"] == "move":
            from .card_movement import perform_move
            return perform_move(self.api, self.store, operation)
        changes = dict(p["changes"])
        if p.get("images") and "description" in changes:
            assets = Assets(self.store.directory, getattr(self.api, "goa_id", ""))
            for record in p["images"]:
                marker = "bivac-image://" + record["token"]
                if marker not in changes["description"]:
                    continue
                url = p.get("uploaded_images", {}).get(record["token"])
                if not url:
                    path = assets.resolve(record["path"])
                    if path is None:
                        raise DeckError(_("No s'ha trobat una imatge pendent d'enviar. L'esborrany es conserva."))
                    url = self.api.upload_image(p["board_id"], p["stack_id"], p["card_id"], record, path.read_bytes())
                    self.store.record_image_upload(operation["id"], record["token"], url)
                    shutil.copy2(path, assets.remote_path(url))
                changes["description"] = changes["description"].replace(marker, url)
        return self.api.update_card(p["board_id"], p["stack_id"], p["card_id"], changes, p.get("base"), p.get("force", False))

    def enqueue(self, kind, payload, undo=None):
        op_id = self.store.enqueue(kind, payload, undo=undo)
        self.notify()
        self.sync(automatic=True)
        return op_id

    def archive_cards(self, board_id, stack_id, card_ids):
        count = self.store.archive_cards(board_id, stack_id, card_ids)
        if count:
            self.notify()
            self.sync(automatic=True)
        return count

    def undo(self, operation_id, done):
        def task():
            if self.closed or self.account_changing:
                return
            try:
                from .undo import undo_action
                undo_action(self.store, operation_id)
                self.notify()
                self.sync(automatic=True)
                self.dispatch(done, None)
            except DeckError as error:
                self.dispatch(done, saved_error(str(error)))
            except Exception:
                self.dispatch(done, _("No s'ha pogut desfer l'acció. Els canvis es conserven."))
        return self.executor.submit(task)

    def run(self, action, done):
        """Read details or perform a user-requested board operation on the same worker."""
        return self._run(self.executor, action, done)

    def _run(self, executor, action, done):
        if self.closed:
            return None
        api = self.api
        def task():
            try:
                if self.closed or api is not self.api:
                    return
                if not api:
                    raise DeckError(_("Connecta el compte de Nextcloud."))
                result = action(api)
                if not self.closed:
                    if done:
                        self.dispatch(done, result, None)
                    else:
                        self.notify()
            except DeckError as error:
                if not self.closed and done:
                    self.dispatch(done, None, saved_error(str(error)))
            except Exception:
                if not self.closed and done:
                    self.dispatch(done, None, _("No s'ha pogut completar l'operació."))
        return executor.submit(task)
