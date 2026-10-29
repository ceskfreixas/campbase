# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Collaboration contracts against an isolated HTTP server and synthetic users."""
import copy
from datetime import datetime, timezone
import http.server
import json
import struct,zlib
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from urllib.parse import urlsplit, parse_qs
from unittest.mock import Mock
from campbase.collaboration import (person, members, assignment_ids, mention_token,
                                    display_comment, activity_creators)
from campbase.deck import Deck, DeckError
from campbase.due_dates import same_due
from campbase.storage import Store
from campbase.sync import SyncEngine
from campbase.updates import collect_updates, entries, mark_read, erase_entries

USERS = [{'uid': 'alice', 'displayname': 'Alícia'}, {'uid': 'bob', 'displayname': 'Robert'},
         {'uid': 'carol', 'displayname': 'Carolina'}]


class Fixture(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def respond(self, data, status=200, ocs_status=None):
        if self.path.startswith('/ocs/'):
            data = {'ocs': {'meta': {'statuscode': ocs_status or status}, 'data': data}}
        payload = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        self.server.reads.append(self.path)
        path = urlsplit(self.path).path
        if '/avatar/' in path:
            self.server.avatar_reads += 1
            def chunk(kind, data):
                return struct.pack('!I', len(data))+kind+data+struct.pack('!I', zlib.crc32(kind+data))
            data = b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('!2I5B', 64,64,8,6,0,0,0))
            data += chunk(b'IDAT', zlib.compress((b'\0'+b'\x35\x84\xe4\xff'*64)*64))+chunk(b'IEND', b'')
            self.send_response(200);self.send_header('Content-Type','image/png');self.end_headers();self.wfile.write(data)
            return
        if path.endswith('/cloud/user'):
            self.respond({'id': 'alice', 'displayname': 'Alícia'})
        elif path.endswith('/sharees'):
            self.respond({'exact': {'users': [{'label': 'Robert', 'value': {'shareType': 0, 'shareWith': 'bob'}}]},
                          'users': [{'label': 'Robert', 'value': {'shareType': 0, 'shareWith': 'bob'}}]})
        elif path.endswith('/boards/1'):
            time.sleep(getattr(self.server, 'board_delay', 0))
            self.respond(self.server.board)
        elif path.endswith('/cards/99/comments'):
            params = parse_qs(urlsplit(self.path).query)
            offset = int(params.get('offset', ['0'])[0])
            limit = int(params.get('limit', ['50'])[0])
            self.respond(self.server.comments[offset:offset+limit])
        elif path.endswith('/cards/99'):
            self.respond(self.server.card)
        elif path.endswith('/notifications'):
            self.respond([{'notification_id': 1, 'app': 'deck', 'subject': 'A board was shared', 'object_type': 'board', 'object_id': '1'},
                          {'notification_id': 2, 'app': 'mail', 'subject': 'Private unrelated mail'}])
        elif path.endswith('/activity/deck'):
            if self.server.no_activity:
                self.respond([], ocs_status=998)
                return
            self.respond([{'activity_id': 3, 'app': 'deck', 'subject': 'New comment', 'datetime': '2026-10-28T12:30:00Z'}])
        else:
            self.respond({}, 404)

    def write(self):
        data = self.rfile.read(int(self.headers.get('Content-Length') or 0))
        body = json.loads(data) if data else None
        self.server.writes.append((self.command, self.path, body))
        return body

    def do_POST(self):
        body = self.write()
        if self.path.endswith('/comments'):
            result = {'id': str(len(self.server.comments)+1), 'actorId': 'alice', 'actorDisplayName': 'Alícia',
                      'message': body['message'], 'creationDateTime': '2026-10-28T15:00:00Z',
                      'mentions': [{'mentionId': 'alice', 'mentionDisplayName': 'Alícia'}] if '@alice' in body['message'] else []}
            if body.get('parentId'):
                parent = next((item for item in self.server.comments if str(item['id']) == str(body['parentId'])), None)
                if parent is None:
                    self.respond({},400);return
                result['replyTo'] = copy.deepcopy(parent)
            self.server.comments.append(result)
            self.respond(result)
            return
        if self.path.endswith('/acl'):
            self.server.board['acl'].append(body | {'id': 10, 'participant': USERS[1]})
            self.server.board['users'].append(USERS[1])
        self.respond(self.server.board)

    def do_PUT(self):
        body = self.write()
        if '/acl/' in self.path:
            self.server.board['acl'][0].update(body)
        elif self.path.endswith('/assignUser'):
            if not self.server.reject_assignment:
                self.server.card['assignedUsers'].append({'type': 0, 'participant': person(body['userId'])})
        elif self.path.endswith('/unassignUser'):
            self.server.card['assignedUsers'] = [item for item in self.server.card['assignedUsers'] if person(item['participant'])['uid'] != body['userId']]
        else:
            self.server.card.update(body)
            if body.get('duedate'):
                # Reproduce Deck's offset loss during datetime persistence.
                self.server.card['duedate'] = datetime.fromisoformat(body['duedate']).replace(tzinfo=timezone.utc).isoformat()
            if self.server.shift_time:
                self.server.card['duedate'] = '2027-02-03T15:31:00Z'
        self.respond(self.server.card)

    def do_DELETE(self):
        self.write()
        if self.path.endswith('/boards/1'):
            status = getattr(self.server, 'board_delete_error', 0)
            if status:
                self.respond({}, status)
            else:
                if not getattr(self.server, 'reject_board_delete', False):
                    self.server.board['deletedAt'] = 1234567890
                self.respond(self.server.board)
            return
        if '/comments/' in self.path:
            comment_id = self.path.split('?')[0].rsplit('/', 1)[-1]
            item = next((row for row in self.server.comments if str(row['id']) == comment_id), None)
            status = getattr(self.server, 'comment_delete_error', 0)
            if status:
                self.respond({}, status)
            elif item is None:
                self.respond({}, 404)
            elif item.get('actorId') != 'alice' or item.get('actorType', 'users') != 'users':
                self.respond({}, 403)
            else:
                self.server.comments.remove(item)
                self.respond([])
            return
        if self.server.dismiss_error and '/notifications/' in self.path:
            self.respond({}, self.server.dismiss_error)
            return
        if '/acl/' in self.path:
            self.server.board['acl'] = []
        self.respond(None)


class CollaborationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = Store(self.directory.name)
        self.server.board = {'id': 1, 'title': 'Projecte de prova', 'owner': USERS[0], 'users': [USERS[0]],
                             'permissions': {'PERMISSION_SHARE': True}, 'acl': []}
        self.server.card = {'id': 99, 'title': 'Prova', 'stackId': 10, 'description': '',
                            'duedate': None, 'owner': USERS[0], 'labels': [], 'assignedUsers': []}
        self.server.writes, self.server.reads = [], []
        self.server.avatar_reads = 0
        self.server.comments = []
        self.server.comment_delete_error = 0
        self.server.board_delete_error = 0
        self.server.reject_board_delete = False
        self.server.dismiss_error = 0
        self.server.reject_assignment = self.server.shift_time = self.server.no_activity = False
        self.api = Deck(SimpleNamespace(server=f'http://127.0.0.1:{self.server.server_port}',
                                      username='login@example.invalid', password='dummy', goa_id='test'), allow_local=True)

    def test_profile_is_canonical_uid_and_search_stays_local(self):
        self.assertEqual(self.api.profile(), USERS[0])
        self.assertEqual(self.api.search_users('Robert'), [USERS[1]])
        params = parse_qs(urlsplit(self.server.reads[-1]).query)
        self.assertEqual(params['lookup'], ['false'])
        self.assertEqual(params['shareType'], ['0'])
        self.assertFalse(self.server.writes)

    def test_board_delete_uses_fresh_canonical_owner_not_login_alias(self):
        self.api.delete_board(1)
        self.assertTrue(self.server.board['deletedAt'])
        self.assertEqual(self.server.writes[-1][:2], ('DELETE', '/index.php/apps/deck/api/v1.0/boards/1'))

    def test_board_manager_who_is_not_owner_cannot_delete_through_client(self):
        self.server.board['owner'] = USERS[1]
        self.server.board['permissions']['PERMISSION_MANAGE'] = True
        with self.assertRaises(DeckError):
            self.api.delete_board(1)
        self.assertFalse(self.server.writes)

    def test_unconfirmed_board_deletion_is_not_success(self):
        self.server.reject_board_delete = True
        with self.assertRaises(DeckError):
            self.api.delete_board(1)
        self.assertFalse(self.server.board.get('deletedAt'))

    def test_board_cache_cleanup_preserves_other_boards_and_drafts(self):
        self.store.put('snapshot', {'boards': [self.server.board, {'id':2,'title':'Keep'}],
                                  'stacks': {'1':[{'id':10,'cards':[]}], '2':[{'id':20,'cards':[]}]}})
        self.store.put('board_metadata', {'1':{'description':'Remove'},'2':{'description':'Keep'}})
        self.store.set_setting('colors', {'10':'#fff000','20':'#123456'})
        self.store.set_setting('archived_columns', ['10','20'])
        self.store.set_setting('startup_board_id', 1)
        op=self.store.enqueue('update',{'board_id':2,'card_id':200,'changes':{'title':'Keep this draft'}})
        self.store.remove_board(1)
        self.assertEqual([b['id'] for b in self.store.get('snapshot')['boards']], [2])
        self.assertEqual(self.store.get('snapshot')['stacks'], {'2':[{'id':20,'cards':[]}]})
        self.assertEqual(self.store.get('board_metadata'), {'2':{'description':'Keep'}})
        self.assertEqual(self.store.settings()['colors'], {'20':'#123456'})
        self.assertEqual(self.store.settings()['archived_columns'], ['20'])
        self.assertIsNone(self.store.settings()['startup_board_id'])
        self.assertEqual(self.store.operations()[0]['id'],op)

    def test_sharing_verifies_members_and_is_idempotent(self):
        perms = {'permissionEdit': True, 'permissionShare': False, 'permissionManage': False}
        board = self.api.share_board(1, 'bob', perms)
        self.assertEqual(len(board['acl']), 1)
        self.api.share_board(1, 'bob', perms)
        self.assertEqual(len(self.server.writes), 1)
        self.assertEqual(self.server.writes[0][2], {'type': 0, 'participant': 'bob', **perms})
        perms['permissionEdit'] = False
        board = self.api.change_access(1, 10, perms)
        self.assertFalse(board['acl'][0]['permissionEdit'])
        self.assertFalse(self.api.change_access(1, 10)['acl'])

    def test_read_only_user_cannot_share(self):
        self.server.board['permissions']['PERMISSION_SHARE'] = False
        with self.assertRaises(DeckError):
            self.api.share_board(1, 'bob', {})
        self.assertFalse(self.server.writes)

    def test_assignment_merges_concurrent_membership_and_retries(self):
        self.server.card['assignedUsers'] = [{'participant': USERS[2], 'type': 0}]
        desired = [{'participant': USERS[1], 'type': 0}]
        result = self.api.update_card(1, 10, 99, {'assignedUsers': desired}, {'assignedUsers': []})
        self.assertEqual(assignment_ids(result['assignedUsers']), {'bob', 'carol'})
        self.api.update_card(1, 10, 99, {'assignedUsers': desired}, {'assignedUsers': []})
        self.assertEqual(len(self.server.writes), 1)
        result = self.api.update_card(1, 10, 99, {'assignedUsers': []}, {'assignedUsers': desired})
        self.assertEqual(assignment_ids(result['assignedUsers']), {'carol'})

    def test_unconfirmed_assignment_is_not_reported_as_success(self):
        self.server.reject_assignment = True
        with self.assertRaises(DeckError):
            self.api.update_card(1, 10, 99, {'assignedUsers': [{'participant': USERS[1]}]}, {'assignedUsers': []})

    def test_due_verification_checks_time_not_only_calendar_day(self):
        value = '2027-02-03T16:30:00+01:00'
        self.assertTrue(same_due(value, '2027-02-03T15:30:00Z'))
        self.assertFalse(same_due(value, '2027-02-03T15:31:00Z'))
        self.server.shift_time = True
        with self.assertRaises(DeckError):
            self.api.update_card(1, 10, 99, {'duedate': value}, {'duedate': None})

    def test_due_transport_uses_utc_before_deck_discards_the_offset(self):
        desired = '2027-02-03T16:30:00+01:00'
        result = self.api.update_card(1, 10, 99, {'duedate': desired}, {'duedate': None})
        self.assertEqual(self.server.writes[-1][2]['duedate'], '2027-02-03T15:30:00+00:00')
        self.assertTrue(same_due(result['duedate'], desired))

    def test_assignee_draft_survives_creation_checkpoint(self):
        self.store.put('snapshot', {'boards': [self.server.board], 'stacks': {'1': [{'id': 10, 'cards': []}]}})
        payload = {'board_id': 1, 'stack_id': 10, 'title': 'Nova', 'assignedUsers': [{'participant': USERS[1]}]}
        op_id = self.store.enqueue('create', payload)
        self.assertEqual(assignment_ids(self.store.view()['stacks']['1'][0]['cards'][0]['assignedUsers']), {'bob'})
        operation = self.store.operations()[0]
        self.store.complete(operation, self.server.card, stage_followups=True)
        reopened = Store(self.directory.name)
        update = reopened.operations()[0]
        self.assertEqual(update['kind'], 'update')
        self.assertEqual(update['payload']['card_id'], 99)
        self.assertEqual(assignment_ids(update['payload']['changes']['assignedUsers']), {'bob'})

    def test_mentions_are_nextcloud_identifiers_and_names_are_presentation(self):
        self.assertEqual(mention_token('bob'), '@bob')
        self.assertEqual(mention_token('Bob User'), '@"user/Bob User"')
        self.assertEqual(mention_token('bob@example.invalid'), '@bob@example.invalid')
        with self.assertRaises(ValueError):
            mention_token('bob" injected')
        self.assertEqual(display_comment({'message': '@"user/bob" revisa-ho', 'mentions': [
            {'mentionId': 'bob', 'mentionDisplayName': 'Robert'}]}), '@Robert revisa-ho')

    def test_feeds_filter_other_apps_and_read_marks_survive_restart(self):
        collect_updates(self.api, self.store)
        self.assertEqual(len(entries(self.store)), 1)
        self.assertNotIn('Private unrelated mail', str(self.store.get('updates')))
        mark_read(self.store, 'n:1')
        self.assertTrue(next(row for row in entries(Store(self.directory.name)) if row['key'] == 'n:1')['read'])
        self.assertFalse(self.server.writes)
        reads = len(self.server.reads)
        collect_updates(self.api, self.store)
        self.assertEqual(len(self.server.reads), reads)
        self.api.dismiss_notification(1)
        self.assertEqual(self.server.writes[-1][0], 'DELETE')
        self.assertIn('/notifications/1?', self.server.writes[-1][1])

    def test_confirmed_self_assignment_does_not_fill_the_inbox(self):
        self.store.put('profile', {**USERS[0], 'account': 'test'})
        self.store.enqueue('update', {'board_id': 1, 'card_id': 99, 'stack_id': 10,
            'changes': {'assignedUsers': [{'type': 0, 'participant': USERS[0]}]},
            'base': {'assignedUsers': []}})
        engine = SyncEngine(self.store)
        self.addCleanup(engine.close)
        engine.api = self.api
        engine._send_pending()
        self.assertFalse(self.store.operations())
        self.assertFalse(self.store.get('local_notices'))
        self.assertFalse(entries(Store(self.directory.name)))

    def test_failed_self_assignment_does_not_create_a_notification(self):
        self.store.put('profile', {**USERS[0], 'account': 'test'})
        self.server.reject_assignment = True
        self.store.enqueue('update', {'board_id': 1, 'card_id': 99, 'stack_id': 10,
                                      'changes': {'assignedUsers': [{'type': 0, 'participant': USERS[0]}]},
                                      'base': {'assignedUsers': []}})
        engine = SyncEngine(self.store)
        self.addCleanup(engine.close)
        engine.api = self.api
        engine._send_pending()
        self.assertEqual(self.store.operations()[0]['state'], 'blocked')
        self.assertFalse(entries(self.store))

    def test_legacy_own_actions_and_unread_summaries_are_not_notifications(self):
        self.store.record_notice({'key': 'local:comment:99:1', 'event': 'self-mentioned', 'title': 'Old'})
        self.store.put('updates', {'comments': [{'key': 'comments:99:3', 'count': 2, 'title': 'Old'}]})
        self.assertFalse(entries(self.store))

    def test_older_comment_notification_reads_the_matching_page(self):
        self.server.comments = [{'id': str(index), 'message': f'Comment {index}'} for index in range(120, 0, -1)]
        result = self.api.comments_for_update(99, {'comment_id': '6'})
        self.assertIn('6', [row['id'] for row in result])
        self.assertTrue(any('offset=100' in path for path in self.server.reads))
        self.assertFalse(self.server.writes)

    def test_only_the_author_can_delete_a_comment(self):
        self.server.comments = [{'id':'1','actorId':'alice','message':'Own comment'},
                                {'id':'2','actorId':'bob','message':'Another author'}]
        with self.assertRaises(DeckError):
            self.api.delete_comment(99, 2)
        self.assertEqual(len(self.server.comments), 2)
        self.api.delete_comment(99, 1)
        self.assertEqual([row['id'] for row in self.server.comments], ['2'])
        self.assertEqual(self.server.writes[-1][0], 'DELETE')
        self.assertIn('/cards/99/comments/1', self.server.writes[-1][1])

    def test_failed_comment_delete_does_not_remove_it(self):
        self.server.comments = [{'id':'1','actorId':'alice','message':'Keep me'}]
        self.server.comment_delete_error = 503
        with self.assertRaises(DeckError):
            self.api.delete_comment(99, 1)
        self.assertEqual(self.server.comments[0]['message'], 'Keep me')
        self.server.comment_delete_error = 404
        with self.assertRaises(DeckError):
            self.api.delete_comment(99, 1)
        self.assertEqual(self.server.comments[0]['message'], 'Keep me')

    def test_deleted_local_activity_and_comment_alerts_stay_hidden_after_refresh(self):
        collect_updates(self.api, self.store)
        local = {'key': 'local:test', 'event': 'own-comment', 'title': 'Prova', 'card_id': 99, 'board_id': 1}
        self.store.record_notice(local)
        rows = [row for row in entries(self.store) if not row.get('notice_id')]
        erase_entries(self.api, self.store, rows)
        self.assertFalse(self.server.writes)
        collect_updates(self.api, self.store, force=True)
        self.assertEqual([row['key'] for row in entries(Store(self.directory.name))], ['n:1'])
        self.assertEqual(self.store.get('local_notices'), [local])

    def test_clear_all_only_deletes_the_displayed_deck_notifications(self):
        collect_updates(self.api, self.store)
        rows = entries(self.store)
        erase_entries(self.api, self.store, rows)
        self.assertEqual(len(self.server.writes), 1)
        self.assertEqual(self.server.writes[0][0], 'DELETE')
        self.assertIn('/notifications/1?', self.server.writes[0][1])
        self.assertFalse(entries(self.store))
        collect_updates(self.api, self.store, force=True)
        self.assertFalse(entries(self.store))
        self.store.record_notice({'key': 'local:new', 'event': 'own-comment', 'title': 'Nou'})
        self.assertFalse(entries(self.store))

    def test_failed_notification_delete_preserves_that_notification(self):
        collect_updates(self.api, self.store)
        rows = sorted(entries(self.store), key=lambda row: bool(row.get('notice_id')))
        self.server.dismiss_error = 403
        with self.assertRaises(DeckError):
            erase_entries(self.api, self.store, rows)
        self.assertEqual([row['key'] for row in entries(self.store)], ['n:1'])
        self.server.dismiss_error = 404
        erase_entries(self.api, self.store, entries(self.store))
        self.assertFalse(entries(self.store))

    def test_missing_optional_activity_app_is_not_a_sync_failure(self):
        self.server.no_activity = True
        snapshot = {'boards': [self.server.board], 'stacks': {'1': [{'id': 10, 'cards': [
            {**self.server.card, 'commentsUnread': 1, 'commentsCount': 3}]}]}}
        state = collect_updates(self.api, self.store, snapshot)
        self.assertEqual(state['errors'], {})
        self.assertTrue(state['unavailable']['activity'])
        self.assertEqual({row['key'] for row in entries(self.store)}, {'n:1'})
        self.assertFalse(self.server.writes)

    def test_reopening_inbox_reuses_cache_and_unavailable_services_back_off(self):
        self.server.no_activity = True
        collect_updates(self.api, self.store)
        self.server.reads.clear()
        collect_updates(self.api, self.store)
        self.assertFalse(self.server.reads)
        state = self.store.get('updates')
        self.store.put('updates', state | {'checked': time.time()-61})
        collect_updates(self.api, self.store)
        self.assertEqual(len(self.server.reads), 1)
        self.assertIn('/notifications', self.server.reads[0])
        self.server.reads.clear()
        collect_updates(self.api, self.store, force=True)
        self.assertEqual(len(self.server.reads), 2)
        self.assertFalse(any('/cloud/user' in path for path in self.server.reads))

    def test_unknown_authorship_stays_unknown_and_creation_activity_is_evidence(self):
        self.assertEqual(self.store.get('creators', {}), {})
        event = {'app': 'deck', 'datetime': '2026-10-28T10:00:00Z', 'icon': 'https://example.invalid/apps/files/img/add-color.svg',
                 'subject_rich': ['opaque translated subject', {'user': {'type': 'user', 'id': 'bob', 'name': 'Robert'},
                     'stack': {'id': '10'}, 'board': {'id': '1'}}]}
        activity_creators(self.store, [event])
        self.assertEqual(self.store.get('creators')['stack:10']['uid'], 'bob')
        self.assertNotIn('board:1', self.store.get('creators'))
        event['icon'] = 'https://example.invalid/apps/files/img/change.svg'
        event['subject_rich'][1]['stack']['id'] = '11'
        activity_creators(self.store, [event])
        self.assertNotIn('stack:11', self.store.get('creators'))

    def test_board_members_use_uid_not_display_name(self):
        board = self.server.board | {'acl': [{'type': 0, 'participant': USERS[1]}, {'type': 1, 'participant': 'staff'}]}
        self.assertEqual({p['uid'] for p in members(board)}, {'alice', 'bob'})


if __name__ == '__main__':
    unittest.main()
