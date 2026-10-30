# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Deck REST/OCS client. Requests contain credentials only for this origin."""
from .i18n import _, ngettext
import base64
import copy
import json
import socket
import uuid
import hashlib
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urljoin
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .account import Account, normalize_server
from . import VERSION
from .collaboration import CollaborationAPI
from .due_dates import same_due, server_due
from .conditional_cache import ConditionalCache
from .deck_resources import DeckResources


class DeckError(Exception):
    pass


class ServiceUnavailable(DeckError):
    """An optional Nextcloud app is not installed or enabled."""


class OfflineError(DeckError):
    pass


class ConflictError(DeckError):
    pass


class NotFoundError(DeckError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Deck(DeckResources, CollaborationAPI):
    def __init__(self, account, allow_local=False):
        self.server = normalize_server(account.server, allow_local=allow_local)
        self.username = account.username
        self.goa_id = getattr(account, "goa_id", "")
        self._auth = "Basic " + base64.b64encode(f"{account.username}:{account.password}".encode()).decode()
        self._transport = threading.local()
        self._cache = ConditionalCache()

    @property
    def opener(self):
        # urllib handlers hold request state: never share one across read workers.
        if not hasattr(self._transport, 'opener'):
            self._transport.opener = build_opener(NoRedirect())
        return self._transport.opener

    @opener.setter
    def opener(self, value):
        self._transport.opener = value

    def refresh_auth(self):
        if self.goa_id:
            try:
                account = Account.from_goa(self.goa_id)
            except ValueError as error:
                raise DeckError(str(error)) from None
            if account.server != self.server or account.username != self.username:
                raise DeckError(_("El compte de GNOME ha canviat. Torna a seleccionar-lo a les preferències."))
            self._auth = "Basic " + base64.b64encode(f"{account.username}:{account.password}".encode()).decode()

    def cached_get(self, path):
        self._transport.conditional = True
        try:
            return self.request('GET', path)
        finally:
            self._transport.conditional = False

    def request(self, method, path, body=None, *, ocs=False, internal=False, version="1.0", content_type="application/json", service=None, timeout=None):
        prefix = "/ocs/v2.php/apps/deck/api/v1.0" if ocs else "/index.php/apps/deck"
        if not ocs and not internal:
            prefix += "/api/v" + version
        if service:
            prefix = {"cloud": "/ocs/v1.php/cloud", "sharing": "/ocs/v1.php/apps/files_sharing/api/v1",
                      "notifications": "/ocs/v1.php/apps/notifications/api/v2",
                      "activity": "/ocs/v1.php/apps/activity/api/v2",
                      "talk": "/ocs/v2.php/apps/spreed/api/v4",
                      "chat": "/ocs/v2.php/apps/spreed/api/v1"}[service]
        payload = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else None
        request = Request(self.server + prefix + path, data=payload, method=method,
                          headers={"Authorization": self._auth, "OCS-APIRequest": "true",
                                   "Accept": "application/json", "Content-Type": content_type,
                                   "User-Agent": f"Campbase/{VERSION} (GNOME; Nextcloud Deck)"})
        conditional = method == 'GET' and not service and getattr(self._transport, 'conditional', False)
        generation, cached = self._cache.get(request.full_url) if conditional else (None, None)
        if cached:
            request.add_header('If-None-Match', cached[0])
        # Invalidate before a write: even an interrupted response may mean it succeeded.
        if method not in {'GET', 'HEAD'} and service is None:
            self._cache.invalidate()
        try:
            with self.opener.open(request, timeout=timeout or (6 if service else 18)) as response:
                raw = response.read(32 * 1024 * 1024 + 1)
                etag = response.headers.get('ETag')
                if len(raw) > 32 * 1024 * 1024:
                    raise DeckError(_("La resposta de Nextcloud és massa gran."))
        except HTTPError as error:
            code = error.code
            error.close()
            if code == 304 and conditional and cached:
                current_generation = self._cache.version()
                if current_generation != generation:
                    self._transport.conditional = False
                    try:
                        return self.request(method, path, body, ocs=ocs, internal=internal,
                                            version=version, content_type=content_type, service=service, timeout=timeout)
                    finally:
                        self._transport.conditional = True
                return cached[1]
            if code == 304 and service == 'chat':
                return []
            if code == 404 and service in {'activity', 'notifications'}:
                raise ServiceUnavailable() from None
            messages = {401: _("El compte no s'ha pogut autenticar. Revisa'l a Comptes en línia de GNOME."),
                        403: _("Nextcloud no permet aquesta operació amb el compte actual."),
                        404: _("La targeta o el tauler ja no són a Deck. Torna a sincronitzar."),
                        409: _("La targeta ha canviat a Deck. Revisa les dues versions."),
                        412: _("La targeta ha canviat a Deck. Revisa les dues versions.")}
            error_type = NotFoundError if code == 404 else DeckError
            raise error_type(messages.get(code, _("Nextcloud ha retornat un error ({code}).").format(code=code))) from None
        except (URLError, TimeoutError, socket.timeout, ConnectionError, OSError):
            raise OfflineError(_("No s'ha pogut contactar amb Nextcloud. Els canvis pendents es conserven en aquest ordinador.")) from None
        try:
            data = json.loads(raw) if raw else None
            if (ocs or service) and data is not None:
                status = data["ocs"]["meta"].get("statuscode")
                if status in (404, 998) and service in {'activity', 'notifications'}:
                    raise ServiceUnavailable()
                if status not in (100, 200, 201, 204, 304):
                    raise DeckError(_("Nextcloud no ha pogut completar l'operació."))
                return data["ocs"]["data"]
            if conditional:
                self._cache.put(request.full_url, etag, data, len(raw), generation)
            return data
        except (ValueError, KeyError, TypeError):
            raise DeckError(_("La resposta de Nextcloud no té el format esperat.")) from None

    def fetch(self, refresh_auth=True):
        if refresh_auth:
            self.refresh_auth()
        # Only independent GETs run in parallel. Writes and their verification
        # remain on the serialized sync worker; publish one complete snapshot.
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix='campbase-read') as pool:
            lists = list(pool.map(lambda path: self.cached_get(path),
                                  ['/boards?details=1', '/boards?archived=1&details=1']))
            if any(not isinstance(rows, list) for rows in lists):
                raise DeckError(_("Nextcloud no ha retornat una llista de taulers vàlida."))
            boards = {b['id']: b for rows in lists for b in rows if not b.get('deletedAt')}
            paths = [(board_id, suffix) for board_id in boards for suffix in ('', '/archived')]
            results = list(pool.map(lambda item: self.cached_get(f'/boards/{item[0]}/stacks{item[1]}'), paths))
        if any(not isinstance(rows, list) for rows in results):
            raise DeckError(_("No s'han pogut llegir les columnes del tauler."))
        fetched = dict(zip(paths, results))
        stacks = {}
        for board in boards.values():
            board_id = board["id"]
            rows = fetched[(board_id, '')]
            # The archived endpoint contains archived cards under their stacks.
            archived = fetched[(board_id, '/archived')]
            by_id = {s["id"]: s for s in rows if not s.get("deletedAt")}
            for stack in archived:
                if stack.get("deletedAt"):
                    continue
                if stack["id"] not in by_id:
                    by_id[stack["id"]] = stack
                else:
                    merged = {c["id"]: c for c in by_id[stack["id"]].get("cards") or []}
                    merged.update({c["id"]: c for c in stack.get("cards") or []})
                    by_id[stack["id"]]["cards"] = list(merged.values())
            for stack in by_id.values():
                stack["cards"] = [dict(c, boardId=board_id) for c in stack.get("cards") or [] if not c.get("deletedAt")]
                stack["cards"].sort(key=lambda c: (c.get("order", 0), c["id"]))
            stacks[str(board_id)] = sorted(by_id.values(), key=lambda s: (s.get("order", 0), s["id"]))
        return {"boards": sorted(boards.values(), key=lambda b: (b.get("archived", False), b.get("title", "").casefold())), "stacks": stacks}

    def check_board(self, board_id):
        board = self.request("GET", f"/boards/{int(board_id)}")
        if not isinstance(board, dict) or board.get("id") != board_id:
            raise DeckError(_("No s'ha pogut verificar el tauler a Deck."))
        return board

    @staticmethod
    def card_path(board_id, stack_id, card_id):
        return f"/boards/{int(board_id)}/stacks/{int(stack_id)}/cards/{int(card_id)}"

    def get_card(self, board_id, stack_id, card_id):
        card = self.request("GET", self.card_path(board_id, stack_id, card_id))
        if not isinstance(card, dict) or card.get("id") != card_id:
            raise DeckError(_("No s'ha pogut verificar la targeta a Deck."))
        card["boardId"] = board_id
        return card

    def card_for_move(self, board_id, card_id, source_stack, target_stack):
        try:
            return self.get_card(board_id, source_stack, card_id)
        except NotFoundError:
            if source_stack == target_stack:
                raise
            return self.get_card(board_id, target_stack, card_id)

    def set_archived(self, board_id, stack_id, card_id, archived, *, current=None):
        current = current or self.get_card(board_id, stack_id, card_id)
        if current['stackId'] != stack_id:
            raise ConflictError(_("La targeta s'ha mogut a una altra columna des d'un altre dispositiu."))
        if bool(current.get('archived')) == bool(archived):
            return current
        action = '/archive' if archived else '/unarchive'
        self.request('PUT', self.card_path(board_id, stack_id, card_id)+action)
        result = self.get_card(board_id, stack_id, card_id)
        if result['stackId'] != stack_id or bool(result.get('archived')) != bool(archived):
            raise DeckError(_("Deck no ha confirmat tots els canvis. L'esborrany es conserva."))
        return result

    def archived_cards(self, board_id, stack_id):
        stacks = self.request('GET', f'/boards/{board_id}/stacks/archived')
        if not isinstance(stacks, list):
            raise DeckError(_("La resposta de Nextcloud no té el format esperat."))
        return next((stack.get('cards') or [] for stack in stacks if stack.get('id') == stack_id), [])

    def move_card(self, board_id, card_id, source_stack, target_stack, order, force=False, *, current=None):
        current = current or self.card_for_move(board_id, card_id, source_stack, target_stack)
        if current["stackId"] not in (source_stack, target_stack) and not force:
            raise ConflictError(_("La targeta s'ha mogut a una altra columna des d'un altre dispositiu."))
        # Deck resolves stackId from the URL before reading the JSON body.
        cards = self.request("PUT", self.card_path(board_id, target_stack, card_id) + "/reorder",
                             {"stackId": target_stack, "order": int(order)})
        if not isinstance(cards, list) or not any(c.get("id") == card_id and c.get("stackId") == target_stack for c in cards):
            raise DeckError(_("Deck no ha confirmat el canvi de columna. El moviment queda pendent."))
        result = self.get_card(board_id, target_stack, card_id)
        if result["stackId"] != target_stack:
            raise DeckError(_("La targeta no és a la columna esperada a Deck."))
        return result

    def update_card(self, board_id, stack_id, card_id, changes, base=None, force=False):
        current = self.get_card(board_id, stack_id, card_id)
        if current.get('deletedAt'):
            raise ConflictError(_("La targeta s'ha esborrat de Deck. Els canvis locals s'han conservat."))
        fields = {key: value for key, value in changes.items() if key not in {"labels", "assignedUsers"}}
        for key in ('stackId','archived'):
            if base and key in base and key not in fields and current.get(key) != base[key]:
                raise ConflictError(_("El contingut d'aquesta targeta ha canviat a Deck. El teu esborrany s'ha conservat."))
        for key, desired in fields.items():
            equal = same_due if key == 'duedate' else lambda a, b: a == b
            if not force and base and not any(equal(current.get(key), value) for value in (base.get(key), desired)):
                raise ConflictError(_("El contingut d'aquesta targeta ha canviat a Deck. El teu esborrany s'ha conservat."))
        written = any(not (same_due(current.get(key), value) if key == 'duedate'
                          else current.get(key) == value) for key, value in fields.items())
        if written:
            archive_change = fields.get('archived') if fields.get('archived') != current.get('archived') else None
            self._write_card(board_id, card_id, current | fields, archived=archive_change)
        if "labels" in changes:
            result = self.update_labels(board_id, current["stackId"], card_id, changes["labels"],
                                        (base or {}).get("labels", current.get("labels")), current=current)
        else:
            result = self.get_card(board_id, fields.get('stackId', current["stackId"]), card_id) if written else current
        if "assignedUsers" in changes:
            result = self.update_assignments(board_id, result["stackId"], card_id, changes["assignedUsers"],
                                             (base or {}).get("assignedUsers", current.get("assignedUsers")), current=result)
        for key, desired in fields.items():
            # The server may normalize the timezone component of due dates.
            actual = result.get(key)
            equal = same_due(actual, desired) if key == "duedate" else actual == desired
            if not equal:
                raise DeckError(_("Deck no ha confirmat tots els canvis. L'esborrany es conserva."))
        return result

    def _write_card(self, board_id, card_id, updated, *, archived=None):
        owner = updated.get("owner", self.username)
        if isinstance(owner, dict):
            owner = owner.get("uid") or owner.get("primaryKey") or self.username
        body = {"title": updated["title"], "description": updated.get("description") or "",
                "type": updated.get("type", "plain"), "owner": owner,
                "order": updated.get("order", 0), "duedate": server_due(updated.get("duedate")),
                "done": updated.get('done')}
        if archived is not None:
            body['archived'] = bool(archived)
        self.request("PUT", self.card_path(board_id, updated["stackId"], card_id), body)

    def update_labels(self, board_id, stack_id, card_id, desired, base, current=None):
        """Merge only explicit membership changes; retries tolerate partial success."""
        ids = lambda labels: {int(item["id"]) for item in labels or []}
        desired_ids, base_ids = ids(desired), ids(base)
        changed = desired_ids ^ base_ids
        current = current if current is not None else self.get_card(board_id, stack_id, card_id)
        current_ids = ids(current.get("labels"))
        path = self.card_path(board_id, current["stackId"], card_id)
        for label_id in sorted(changed):
            selected = label_id in desired_ids
            if selected != (label_id in current_ids):
                action = "assignLabel" if selected else "removeLabel"
                self.request("PUT", path + "/" + action, {"labelId": label_id})
        result = self.get_card(board_id, current["stackId"], card_id)
        actual_ids = ids(result.get("labels"))
        if any((label_id in actual_ids) != (label_id in desired_ids) for label_id in changed):
            raise DeckError(_("Deck no ha confirmat les etiquetes. El canvi es conserva."))
        return result

    def create_label(self, board_id, title, color):
        """Reuse an exact match after an uncertain response instead of duplicating it."""
        title, color = title.strip(), color.lstrip("#").upper()
        if not title or len(title) > 100 or not re.fullmatch(r"[0-9A-F]{6}", color):
            raise DeckError(_("Revisa el nom i el color de l'etiqueta."))
        board = self.request("GET", f"/boards/{int(board_id)}")
        existing = next((item for item in board.get("labels") or []
                         if item["title"].casefold() == title.casefold() and item["color"].upper() == color), None)
        if existing:
            return existing
        result = self.request("POST", f"/boards/{int(board_id)}/labels", {"title": title, "color": color})
        if not isinstance(result, dict) or not isinstance(result.get("id"), int) or result["id"] <= 0:
            raise DeckError(_("No s'ha pogut confirmar l'etiqueta nova. Sincronitza abans de tornar-ho a provar."))
        return result

    def create_card(self, board_id, stack_id, title, description="", duedate=None, order=0):
        body = {"title": title, "description": description, "type": "plain", "order": order, "duedate": server_due(duedate)}
        result = self.request("POST", f"/boards/{board_id}/stacks/{stack_id}/cards", body)
        if not isinstance(result, dict) or not isinstance(result.get("id"), int):
            raise ConflictError(_("No es pot confirmar la creació. Revisa Deck abans de tornar a enviar aquesta targeta."))
        return self.get_card(board_id, stack_id, result["id"]) if result.get("stackId") is None else dict(result, boardId=board_id)

    def comments(self, card_id, offset=0, *, limit=50):
        result = self.request("GET", f"/cards/{card_id}/comments?limit={int(limit)}"+(f'&offset={int(offset)}' if offset else ''), ocs=True)
        if result is None:
            return []
        if not isinstance(result, list) or any(not isinstance(item, dict) for item in result):
            raise DeckError(_("No s'han pogut llegir els comentaris de Deck."))
        return result

    def comment_summary(self, card_id, expected_total, keep_reading=lambda: True):
        from .comment_reactions import reaction
        seen, text_count = set(), 0
        for offset in range(0, expected_total, 200):
            if not keep_reading():
                return None
            page = self.comments(card_id, offset, limit=200)
            for item in page:
                key = item.get('id')
                if key is None or str(key) in seen:
                    return None
                seen.add(str(key))
                text_count += reaction(item) is None
            if len(page) < 200:
                break
        return text_count if len(seen) == expected_total else None

    def comments_for_update(self, card_id, target):
        from .update_targets import matches_comment
        for offset in range(0, 1000, 50):
            rows = self.comments(card_id, offset)
            if offset == 0:
                latest = rows
            if any(matches_comment(item, target) for item in rows):
                return rows
            if len(rows) < 50 or not (target.get('comment_id') or target.get('comment_time')):
                break
        return latest

    def add_comment(self, card_id, message, *, parent_id=None):
        body = {'message': message}
        if parent_id is not None:
            body['parentId'] = int(parent_id)
        result = self.request("POST", f"/cards/{card_id}/comments", body, ocs=True)
        if not isinstance(result, dict) or not result.get('id') or not isinstance(result.get('message'), str):
            raise DeckError(_("No s'ha pogut confirmar el comentari"))
        if parent_id is not None and str((result.get('replyTo') or {}).get('id')) != str(parent_id):
            raise DeckError(_("Nextcloud no ha confirmat la resposta al comentari."))
        return result

    def delete_comment(self, card_id, comment_id):
        try:
            result = self.request('DELETE', f'/cards/{int(card_id)}/comments/{int(comment_id)}', ocs=True)
        except NotFoundError:
            rows = self.comments_for_update(card_id, {'comment_id': comment_id})
            if any(str(row.get('id')) == str(comment_id) for row in rows):
                raise DeckError(_("Nextcloud no ha confirmat que s'hagi esborrat el comentari.")) from None
            return
        if result not in (None, []):
            raise DeckError(_("Nextcloud no ha confirmat que s'hagi esborrat el comentari."))

    def delete_archived_card(self, board_id, stack_id, card_id):
        try:
            current = self.get_card(board_id, stack_id, card_id)
        except NotFoundError:
            return
        if current.get('deletedAt'):
            return
        if not current.get('archived'):
            raise ConflictError(_("La targeta ja no està arxivada. No s'ha esborrat."))
        if current.get('stackId') != stack_id:
            raise ConflictError(_("La targeta s'ha mogut a una altra columna. No s'ha esborrat."))
        result = self.request('DELETE', self.card_path(board_id, stack_id, card_id))
        if isinstance(result, dict) and result.get('id') == card_id and result.get('deletedAt'):
            return
        try:
            result = self.get_card(board_id, stack_id, card_id)
        except NotFoundError:
            return
        if not result.get('deletedAt'):
            raise DeckError(_("Deck no ha confirmat que s'hagi esborrat la targeta."))

    def create_board(self, title):
        return self.request("POST", "/boards", {"title": title, "color": "3584e4"})

    def delete_board(self, board_id):
        from .collaboration import person
        current = self.check_board(board_id)
        uid = self.profile()['uid']
        if not uid or person(current.get('owner'))['uid'] != uid:
            raise DeckError(_("Només el propietari pot esborrar aquest tauler."))
        result = self.request('DELETE', f'/boards/{int(board_id)}')
        if isinstance(result, dict) and result.get('id') == board_id and result.get('deletedAt'):
            return
        try:
            result = self.check_board(board_id)
        except NotFoundError:
            return
        if not result.get('deletedAt'):
            raise DeckError(_("Deck no ha confirmat que s'hagi esborrat el tauler."))

    def create_stack(self, board_id, title, order):
        return self.request("POST", f"/boards/{board_id}/stacks", {"title": title, "order": order})

    def rename_stack(self, board_id, stack, title):
        return self.request("PUT", f"/boards/{board_id}/stacks/{stack['id']}", {"title": title, "order": stack.get("order", 0)})

    def update_board(self, board_id, changes, base=None, force=False):
        current = self.request("GET", f"/boards/{board_id}")
        if not force and base and current["title"] not in (base.get("title"), changes["title"]):
            raise ConflictError(_("El nom del projecte ha canviat a Deck. El teu canvi es conserva."))
        if current["title"] != changes["title"]:
            self.request("PUT", f"/boards/{board_id}", {"title": changes["title"], "color": current.get("color", "3584e4"), "archived": bool(current.get("archived"))})
        result = self.request("GET", f"/boards/{board_id}")
        if result["title"] != changes["title"]:
            raise DeckError(_("Deck no ha confirmat el nom del projecte."))
        return result

    def fetch_image(self, url, *, max_bytes=16 * 1024 * 1024, timeout=18):
        target = urljoin(self.server+"/", url)
        origin, remote = urlsplit(self.server), urlsplit(target)
        if (origin.scheme, origin.hostname, origin.port) != (remote.scheme, remote.hostname, remote.port) or remote.username or remote.password:
            raise DeckError(_("La imatge no és al servidor de Nextcloud del compte."))
        request = Request(target, headers={"Authorization": self._auth, "OCS-APIRequest": "true", "User-Agent": f"Campbase/{VERSION} (GNOME)"})
        try:
            with self.opener.open(request, timeout=timeout) as response:
                data = response.read(max_bytes + 1)
        except (HTTPError, URLError, OSError):
            raise DeckError(_("No s'ha pogut carregar la imatge de Nextcloud.")) from None
        if len(data) > max_bytes or not (data.startswith(b'\x89PNG\r\n\x1a\n') or data.startswith(b'\xff\xd8\xff') or data.startswith((b'GIF87a', b'GIF89a')) or (data[:4] == b'RIFF' and data[8:12] == b'WEBP')):
            raise DeckError(_("Nextcloud no ha retornat una imatge compatible."))
        return data

    def upload_image(self, board_id, stack_id, card_id, record, data):
        if hashlib.sha256(data).hexdigest() != record["sha256"]:
            raise DeckError(_("La imatge local ha canviat. Torna-la a seleccionar."))
        filename = f"campbase-{card_id}-{record['token']}-{record['sha256'][:12]}.{record['extension']}"
        path = self.card_path(board_id, stack_id, card_id) + "/attachments"
        existing = self.request("GET", path, version="1.1")
        def name(attachment):
            info = attachment.get("extendedData", {}).get("info", {})
            return info.get("name") or info.get("basename") or (info.get("filename", "") + ("."+info["extension"] if info.get("extension") else "")) or attachment.get("data", "")
        attachment = next((a for a in existing if name(a) == filename or a.get("data") == filename), None)
        if attachment is None:
            boundary = "Campbase" + uuid.uuid4().hex
            mime = {"png": "image/png", "jpg": "image/jpeg", "gif": "image/gif", "webp": "image/webp"}[record["extension"]]
            body = (f'--{boundary}\r\nContent-Disposition: form-data; name="type"\r\n\r\nfile\r\n'
                    f'--{boundary}\r\nContent-Disposition: form-data; name="data"\r\n\r\n\r\n'
                    f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: {mime}\r\n\r\n').encode() + data + f'\r\n--{boundary}--\r\n'.encode()
            attachment = self.request("POST", path, body, version="1.1", content_type="multipart/form-data; boundary="+boundary)
        if not isinstance(attachment, dict) or not attachment.get("id"):
            raise DeckError(_("Deck no ha confirmat l'adjunt de la imatge."))
        file_id = attachment.get("extendedData", {}).get("fileid")
        if file_id:
            return f"{self.server}/index.php/core/preview?fileId={int(file_id)}&x=1200&y=1200&a=true"
        return f"{self.server}/index.php/apps/deck/cards/{card_id}/attachment/{int(attachment['id'])}"
