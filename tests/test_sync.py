# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Regression tests use a local HTTP fixture, never a real Nextcloud account."""
import copy
import base64
import hashlib
from pathlib import Path
from unittest.mock import Mock
import http.server
import json
import re
import tempfile
import threading
import unittest
from types import SimpleNamespace

from campbase.account import normalize_server, server_from_files_uri
from campbase.deck import ConflictError, Deck, DeckError, OfflineError
from campbase.storage import Store
from campbase.sync import SyncEngine


class Fixture(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def respond(self, value, status=200):
        payload = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        self.server.reads.append(self.path)
        path = re.split(r"/api/v1\.[01]", self.path)[-1]
        if path.startswith("/boards?archived=1"):
            self.respond([])
        elif path in {"/boards", "/boards?details=1"}:
            self.respond([self.server.board])
        elif path == "/boards/1":
            self.respond(self.server.board)
        elif path.endswith("/attachments"):
            self.respond(self.server.attachments)
        elif path.endswith("/stacks/archived"):
            self.respond([{'id':sid,'title':name,'order':index,
                           'cards':[card for card in self.server.cards.values() if card['stackId']==sid and card.get('archived')]}
                          for index,(sid,name) in enumerate([(10,'Triatge'),(20,'En curs'),(30,'Fet')])])
        elif path.endswith("/stacks"):
            self.respond([{"id": sid, "title": name, "order": i,
                           "cards": [c for c in self.server.cards.values() if c["stackId"] == sid and not c.get('archived')]}
                          for i, (sid, name) in enumerate([(10, "Triatge"), (20, "En curs"), (30, "Fet")])])
        elif re.search(r'/cards/\d+/comments(?:\?|$)', path):
            self.respond([])
        elif "/cards/" in path:
            card_id = int(path.rsplit("/", 1)[-1])
            self.respond(self.server.cards.get(card_id, {}))
        else:
            self.respond({}, 404)

    def do_PUT(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b'{}')
        self.server.writes.append((self.path, body))
        if self.path.endswith("/boards/1"):
            self.server.board.update(body)
            self.respond(self.server.board)
            return
        card_id = int(re.search(r"/cards/(\d+)", self.path)[1])
        card = self.server.cards[card_id]
        stack_id = int(re.search(r"/stacks/(\d+)", self.path)[1])
        if self.path.endswith(('/archive','/unarchive')):
            archived = self.path.endswith('/archive')
            if archived and getattr(self.server,'reject_archive',False):
                self.respond({'message':'Archive failed'},500);return
            card['archived']=archived
            self.respond(card);return
        if self.path.endswith("/assignLabel"):
            label = next(item for item in self.server.board["labels"] if item["id"] == body["labelId"])
            if not self.server.reject_labels and not any(item["id"] == label["id"] for item in card["labels"]):
                card["labels"].append(copy.deepcopy(label))
            self.respond(card)
        elif self.path.endswith("/removeLabel"):
            if not self.server.reject_labels:
                card["labels"] = [item for item in card["labels"] if item["id"] != body["labelId"]]
            self.respond(card)
        elif self.path.endswith("/reorder"):
            if card.get('archived'):
                self.respond({'message':'Operation not allowed. This card is archived.'},500)
                return
            # Deck ignores stackId from JSON in favor of the URL route parameter.
            if not self.server.reject_move:
                card["stackId"] = stack_id
                card["order"] = body["order"]
                index=0
                for peer in sorted((c for c in self.server.cards.values() if c['stackId']==stack_id and not c.get('archived')),key=lambda c:(c.get('order',0),c['id'])):
                    if index==body['order']:index+=1
                    if peer['id']!=card_id:
                        peer['order']=index;index+=1
            self.respond([c for c in self.server.cards.values() if c['stackId']==stack_id and not c.get('archived')])
        else:
            if card.get('archived') and body.get('archived') is True:
                self.respond({'message':'Operation not allowed. This card is archived.'},500);return
            card.update(body)
            card["stackId"] = stack_id
            self.respond(card)

    def do_POST(self):
        raw = self.rfile.read(int(self.headers["Content-Length"]))
        if self.path.endswith("/attachments"):
            assert b'name="data"' in raw
            filename = re.search(rb'filename="([^"]+)"', raw)[1].decode()
            attachment = {"id": 5, "type": "file", "data": filename,
                          "extendedData": {"fileid": 6, "info": {"basename": filename}}}
            self.server.attachments.append(attachment)
            self.respond(attachment)
            return
        body = json.loads(raw)
        self.server.writes.append((self.path, body))
        if self.path.endswith("/labels"):
            label = body | {"id": max(item["id"] for item in self.server.board["labels"])+1, "boardId": 1}
            self.server.board["labels"].append(label)
            self.respond(label)
            return
        card_id = max(self.server.cards) + 1
        stack_id = int(re.search(r"/stacks/(\d+)", self.path)[1])
        card = body | {"id": card_id, "stackId": stack_id, "owner": "test", "labels": [], "archived": False}
        self.server.cards[card_id] = card
        self.respond(card)

    def do_DELETE(self):
        card_id = int(re.search(r'/cards/(\d+)', self.path)[1])
        self.server.writes.append((self.path, {'delete': True}))
        error = getattr(self.server, 'delete_errors', {}).get(card_id)
        if error:
            self.respond({}, error)
            return
        card = self.server.cards.get(card_id)
        if card is None:
            self.respond({}, 404)
            return
        if not getattr(self.server, 'reject_delete', False):
            card['deletedAt'] = 1234567890
        self.respond(card)


class SyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = Store(self.directory.name)
        self.server.cards = {99: {"id": 99, "title": "Targeta", "description": "Original",
                                  "stackId": 10, "order": 0, "labels": [], "archived": False,
                                  "owner": "test", "type": "plain", "duedate": None}}
        self.server.writes = []
        self.server.reads = []
        self.server.board = {"id": 1, "title": "Prova", "color": "3584e4", "archived": False}
        self.server.board["labels"] = [{"id": i, "boardId": 1, "title": title, "color": color}
                                       for i, title, color in [(1, "Urgent", "E01B24"), (2, "Disseny", "3584E4"), (3, "Comunitat", "33A56C")]]
        self.server.attachments = []
        self.server.reject_move = False
        self.server.reject_labels = False
        account = SimpleNamespace(server=f"http://127.0.0.1:{self.server.server_port}", username="test", password="dummy")
        self.api = Deck(account, allow_local=True)
        self.store.put("snapshot", self.api.fetch())

    def engine(self):
        engine = SyncEngine(self.store)
        engine.api = self.api
        def cleanup():
            engine.close()
            engine.executor.shutdown(wait=True)
            engine.updates_executor.shutdown(wait=True)
        self.addCleanup(cleanup)
        return engine

    def test_movement_is_confirmed_on_server_and_survives_a_fresh_read(self):
        result = self.api.move_card(1, 99, 10, 20, 0)
        self.assertEqual(result["stackId"], 20)
        self.assertIn("/stacks/20/", self.server.writes[0][0])
        fresh = self.api.fetch()
        self.assertEqual(len(fresh["stacks"]["1"][0]["cards"]), 0)
        self.assertEqual(fresh["stacks"]["1"][1]["cards"][0]["id"], 99)

    def test_http_success_without_movement_is_rejected(self):
        self.server.reject_move = True
        with self.assertRaises(DeckError):
            self.api.move_card(1, 99, 10, 20, 0)

    def test_remote_changes_to_other_fields_are_preserved(self):
        self.server.cards[99]["description"] = "Canvi fet al mòbil"
        result = self.api.update_card(1, 10, 99, {"title": "Títol nou"}, {"title": "Targeta"})
        self.assertEqual(result["description"], "Canvi fet al mòbil")

    def test_simultaneous_changes_to_same_field_create_a_conflict(self):
        self.server.cards[99]["description"] = "Canvi fet al mòbil"
        with self.assertRaises(ConflictError):
            self.api.update_card(1, 10, 99, {"description": "Canvi local"}, {"description": "Original"})
        self.assertFalse(self.server.writes)

    def test_move_then_edit_does_not_move_the_card_back(self):
        self.store.enqueue("move", {"board_id": 1, "card_id": 99, "source_stack": 10, "target_stack": 20, "order": 0})
        self.store.enqueue("update", {"board_id": 1, "card_id": 99, "stack_id": 10,
                                      "changes": {"title": "Editada"}, "base": {"title": "Targeta"}})
        self.engine()._sync()
        self.assertEqual(self.server.cards[99]["stackId"], 20)
        self.assertEqual(self.server.cards[99]["title"], "Editada")
        self.assertEqual(self.store.operations(), [])

    def test_new_card_followed_by_move_remaps_temporary_identity(self):
        op_id = self.store.enqueue("create", {"board_id": 1, "stack_id": 10, "title": "Nova", "order": 1})
        self.store.enqueue("move", {"board_id": 1, "card_id": -op_id, "source_stack": 10, "target_stack": 20, "order": 0})
        self.engine()._sync()
        self.assertEqual(self.server.cards[100]["stackId"], 20)
        self.assertEqual(self.store.operations(), [])

    def test_uncertain_creation_is_not_sent_twice(self):
        class Uncertain:
            def refresh_auth(inner):
                return self.api.refresh_auth()
            def check_board(inner, board_id):
                return self.api.check_board(board_id)
            def fetch(inner, **kwargs):
                return self.api.fetch(**kwargs)
            def create_card(inner, *args):
                self.api.create_card(*args)
                raise OfflineError("Connexió interrompuda després de crear")
        self.store.enqueue("create", {"board_id": 1, "stack_id": 10, "title": "Nova", "order": 1})
        engine = self.engine()
        engine.api = Uncertain()
        engine._sync()
        engine._sync()
        self.assertEqual(len(self.server.cards), 2)
        self.assertEqual(self.store.operations()[0]["state"], "blocked")

    def test_process_interruption_during_creation_requires_review(self):
        op_id = self.store.enqueue("create", {"board_id": 1, "stack_id": 10, "title": "Nova"})
        self.store.begin_send(op_id)
        reopened = Store(self.directory.name)
        self.assertEqual(reopened.operations()[0]["state"], "blocked")

    def test_cache_and_outbox_survive_restart(self):
        self.store.enqueue("move", {"board_id": 1, "card_id": 99, "source_stack": 10, "target_stack": 20, "order": 0})
        reopened = Store(self.directory.name)
        self.assertEqual(reopened.view()["stacks"]["1"][1]["cards"][0]["id"], 99)
        self.assertEqual(len(reopened.operations()), 1)

    def test_new_card_due_time_is_sent_as_a_utc_instant(self):
        from campbase.due_dates import same_due
        due = '2027-07-03T22:05:00+02:00'
        result = self.api.create_card(1, 10, 'Data de prova', duedate=due)
        self.assertEqual(self.server.writes[-1][1]['duedate'], '2027-07-03T20:05:00+00:00')
        self.assertTrue(same_due(result['duedate'], due))

    def test_idle_sync_reads_the_workspace_only_once(self):
        self.server.reads.clear()
        self.engine()._sync()
        self.assertEqual(len([path for path in self.server.reads if '/apps/deck/' in path]), 4)
        self.assertEqual(sum(path.endswith('/boards?details=1') for path in self.server.reads), 1)
        self.assertFalse(self.server.writes)

    def test_pending_writes_are_confirmed_before_the_workspace_refresh(self):
        self.store.enqueue('update', {'board_id': 1, 'stack_id': 10, 'card_id': 99,
                                     'changes': {'title': 'Més ràpid'}, 'base': {'title': 'Targeta'}})
        original = self.api.fetch
        def fetch(**kwargs):
            self.assertEqual(self.server.cards[99]['title'], 'Més ràpid')
            self.assertFalse(self.store.operations())
            return original(**kwargs)
        self.api.fetch = fetch
        self.server.reads.clear()
        self.engine()._sync()
        self.assertIn('/cards/99', self.server.reads[0])
        self.assertEqual(len([path for path in self.server.reads if '/apps/deck/' in path]), 6)

    def test_manual_mode_keeps_edits_pending_until_explicit_sync(self):
        self.store.set_setting('auto_sync', False)
        engine = self.engine()
        engine.enqueue('update', {'board_id': 1, 'stack_id': 10, 'card_id': 99,
                                  'changes': {'title': 'Manual'}, 'base': {'title': 'Targeta'}})
        self.assertFalse(engine.busy)
        self.assertFalse(self.server.writes)
        self.assertEqual(len(self.store.operations()), 1)
        engine.sync().result(timeout=5)
        self.assertEqual(self.server.cards[99]['title'], 'Manual')
        self.assertFalse(self.store.operations())

    def test_read_only_refresh_does_not_send_pending_edits(self):
        self.store.enqueue('update', {'board_id': 1, 'stack_id': 10, 'card_id': 99,
                                     'changes': {'title': 'Pendent'}, 'base': {'title': 'Targeta'}})
        self.engine()._sync(read_only=True)
        self.assertFalse(self.server.writes)
        self.assertEqual(len(self.store.operations()), 1)
        self.assertEqual(self.store.view()['stacks']['1'][0]['cards'][0]['title'], 'Pendent')

    def test_create_preflight_failure_keeps_a_safe_unsent_draft(self):
        self.store.enqueue('create', {'board_id': 1, 'stack_id': 10, 'title': 'Sense connexió'})
        self.api.check_board = Mock(side_effect=OfflineError('Preflight offline'))
        self.api.create_card = Mock()
        self.engine()._sync()
        self.api.create_card.assert_not_called()
        self.assertEqual(Store(self.directory.name).operations()[0]['state'], 'pending')

    def test_disabling_auto_sync_cancels_a_queued_automatic_cycle(self):
        engine = self.engine()
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        original = self.api.fetch
        def fetch(**kwargs):
            entered.set()
            self.assertTrue(release.wait(5))
            return original(**kwargs)
        self.api.fetch = fetch
        future = engine.sync(automatic=True)
        self.assertTrue(entered.wait(5))
        engine.enqueue('update', {'board_id': 1, 'stack_id': 10, 'card_id': 99,
                                  'changes': {'title': 'Es conserva'}, 'base': {'title': 'Targeta'}})
        engine.sync(read_only=True)
        self.store.set_setting('auto_sync', False)
        release.set();future.result(timeout=5)
        engine.executor.submit(lambda: None).result(timeout=5)
        self.assertFalse(self.server.writes)
        self.assertEqual(len(self.store.operations()), 1)

    def test_label_selection_survives_restart_and_uses_dedicated_endpoints(self):
        one, two, _ = self.server.board["labels"]
        self.server.cards[99]["labels"] = [one]
        self.store.put("snapshot", self.api.fetch())
        self.store.enqueue("update", {"board_id": 1, "stack_id": 10, "card_id": 99,
                                      "changes": {"labels": [two]}, "base": {"labels": [one]}})
        self.store = Store(self.directory.name)
        self.assertEqual(self.store.view()["stacks"]["1"][0]["cards"][0]["labels"], [two])
        self.engine()._sync()
        self.assertEqual(self.api.get_card(1, 10, 99)["labels"], [two])
        self.assertEqual(self.store.operations(), [])
        self.assertEqual([path.rsplit("/", 1)[-1] for path, _ in self.server.writes], ["removeLabel", "assignLabel"])
        self.assertEqual(self.server.cards[99]["description"], "Original")

    def test_labels_merge_mobile_changes_and_partial_success_is_retryable(self):
        one, two, three = self.server.board["labels"]
        self.server.cards[99]["labels"] = [one, three]
        self.store.enqueue("update", {"board_id": 1, "stack_id": 10, "card_id": 99,
                                      "changes": {"labels": [two]}, "base": {"labels": [one]}})
        original = self.api.request
        interrupted = []
        def request(method, path, *args, **kwargs):
            if path.endswith("/assignLabel") and not interrupted:
                interrupted.append(True)
                raise OfflineError("Disconnected after removing the first label")
            return original(method, path, *args, **kwargs)
        self.api.request = request
        self.engine()._sync()
        self.assertEqual(self.store.operations()[0]["state"], "pending")
        self.assertEqual(self.server.cards[99]["labels"], [three])
        self.store = Store(self.directory.name)
        self.engine()._sync()
        self.assertEqual({item["id"] for item in self.server.cards[99]["labels"]}, {2, 3})
        self.assertEqual(self.store.operations(), [])
        self.assertEqual(sum(path.endswith("/removeLabel") for path, _ in self.server.writes), 1)

    def test_new_card_label_failure_resumes_assignment_without_recreating_card(self):
        desired = [self.server.board["labels"][0]]
        self.store.enqueue("create", {"board_id": 1, "stack_id": 10, "title": "Amb etiquetes", "labels": desired})
        update = self.api.update_labels
        self.api.update_labels = Mock(side_effect=OfflineError("Offline after creating the card"))
        self.engine()._sync()
        pending = self.store.operations()[0]
        self.assertEqual(pending["kind"], "update")
        self.assertEqual(pending["payload"]["card_id"], 100)
        self.assertEqual(pending["state"], "pending")
        self.api.update_labels = update
        self.store = Store(self.directory.name)
        self.engine()._sync()
        self.assertEqual(len(self.server.cards), 2)
        self.assertEqual(self.server.cards[100]["labels"], desired)
        self.assertEqual(self.store.operations(), [])

    def test_label_success_requires_a_fresh_server_confirmation(self):
        self.server.reject_labels = True
        with self.assertRaises(DeckError):
            self.api.update_card(1, 10, 99, {"labels": [self.server.board["labels"][0]]}, {"labels": []})

    def test_label_creation_reuses_an_existing_match_after_an_uncertain_response(self):
        original = self.api.request
        def request(method, path, *args, **kwargs):
            result = original(method, path, *args, **kwargs)
            if method == "POST" and path.endswith("/labels"):
                raise OfflineError("Response lost after label creation")
            return result
        self.api.request = request
        with self.assertRaises(OfflineError):
            self.api.create_label(1, "Nova", "#33a56c")
        self.api.request = original
        result = self.api.create_label(1, "nova", "#33a56c")
        self.assertEqual(result["id"], 4)
        self.assertEqual(sum(path.endswith("/labels") for path, _ in self.server.writes), 1)
        self.assertEqual(len(self.api.fetch()["boards"][0]["labels"]), 4)

    def test_text_conflicts_are_checked_before_assigning_labels(self):
        self.server.cards[99]["description"] = "Canvi al mòbil"
        with self.assertRaises(ConflictError):
            self.api.update_card(1, 10, 99, {"description": "Canvi local", "labels": [self.server.board["labels"][0]]},
                                 {"description": "Original", "labels": []})
        self.assertFalse(self.server.writes)

    def image(self):
        from campbase.assets import Assets
        from gi.repository import Gio
        path = Path(self.directory.name) / "source.png"
        path.write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1sAAAAASUVORK5CYII="))
        record = Assets(self.directory.name).import_file(Gio.File.new_for_path(str(path)))
        return record, path.read_bytes()

    def test_board_rename_is_durable_and_preserves_remote_properties(self):
        self.store.enqueue("board_update", {"board_id": 1, "changes": {"title": "Nou nom"}, "base": {"title": "Prova"}})
        self.assertEqual(Store(self.directory.name).view()["boards"][0]["title"], "Nou nom")
        self.engine()._sync()
        self.assertEqual(self.server.board["title"], "Nou nom")
        self.assertEqual(self.server.board["color"], "3584e4")
        self.assertFalse(self.store.operations())

    def test_board_rename_conflict_preserves_local_change(self):
        self.server.board["title"] = "Nom al mòbil"
        self.store.enqueue("board_update", {"board_id": 1, "changes": {"title": "Nou nom"}, "base": {"title": "Prova"}})
        self.engine()._sync()
        self.assertEqual(self.server.board["title"], "Nom al mòbil")
        self.assertEqual(self.store.operations()[0]["state"], "blocked")

    def test_upload_retry_reuses_attachment_and_requires_original_image_bytes(self):
        record, data = self.image()
        url = self.api.upload_image(1, 10, 99, record, data)
        self.assertEqual(url, self.api.upload_image(1, 10, 99, record, data))
        self.assertEqual(len(self.server.attachments), 1)
        with self.assertRaises(DeckError):
            self.api.upload_image(1, 10, 99, record, data+b"changed")

    def test_image_failure_after_create_resumes_existing_card_after_restart(self):
        record, data = self.image()
        description = "Text\n\n![Imatge](bivac-image://" + record["token"] + ")"
        op_id = self.store.enqueue("create", {"board_id": 1, "stack_id": 10, "title": "Amb imatge",
                                              "description": description, "images": [record]})
        engine = self.engine()
        upload = self.api.upload_image
        def interrupted(*args):
            upload(*args)
            raise OfflineError("Connexió interrompuda")
        self.api.upload_image = interrupted
        engine._sync()
        self.assertEqual(len(self.server.cards), 2)
        self.assertEqual(self.store.operations()[0]["kind"], "update")
        self.assertNotIn("bivac-image://", self.server.cards[100]["description"])
        engine.store = Store(self.directory.name)
        self.api.upload_image = upload
        engine._sync()
        self.assertFalse(engine.store.operations())
        self.assertEqual(len(self.server.cards), 2)
        self.assertEqual(len(self.server.attachments), 1)
        self.assertIn("/core/preview?fileId=6", self.server.cards[100]["description"])

    def test_later_offline_description_edit_uses_uploaded_image_as_its_base(self):
        record, data = self.image()
        description = "![Imatge](bivac-image://" + record["token"] + ")"
        op_id = self.store.enqueue("create", {"board_id": 1, "stack_id": 10, "title": "Amb imatge",
                                              "description": description, "images": [record]})
        self.store.enqueue("update", {"board_id": 1, "stack_id": 10, "card_id": -op_id,
                                      "changes": {"description": description+"\n\nText posterior"},
                                      "base": {"description": description}, "images": [record]})
        self.engine()._sync()
        self.assertFalse(self.store.operations())
        self.assertEqual(len(self.server.cards), 2)
        self.assertEqual(len(self.server.attachments), 1)
        self.assertIn("Text posterior", self.server.cards[100]["description"])
        self.assertNotIn("bivac-image://", self.server.cards[100]["description"])

    def test_foreign_image_url_is_rejected_before_any_authenticated_request(self):
        opener = Mock()
        self.api.opener = opener
        for url in ["https://external.example/image.png", "//external.example/picture", "http://user:password@127.0.0.1/image"]:
            with self.assertRaises(DeckError):
                self.api.fetch_image(url)
        opener.open.assert_not_called()

    def test_server_requires_https_and_rejects_credentials_in_url(self):
        self.assertEqual(normalize_server("https://cloud.example/remote.php/dav"), "https://cloud.example")
        for value in ["http://cloud.example", "https://user:pass@cloud.example", "https://cloud.example/?secret=x"]:
            with self.assertRaises(ValueError):
                normalize_server(value)

    def test_gnome_files_uri_preserves_server_path_without_userinfo(self):
        self.assertEqual(server_from_files_uri("davs://alice%40example.com@cloud.example/nextcloud/remote.php/webdav"),
                         "https://cloud.example/nextcloud")


if __name__ == "__main__":
    unittest.main()
