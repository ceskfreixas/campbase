# SPDX-License-Identifier: GPL-3.0-or-later
import copy
import io
from urllib.error import HTTPError
import json
import tempfile
import time
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import Mock
from campbase.deck import Deck, DeckError, ConflictError
from campbase.conditional_cache import ConditionalCache
from campbase.storage import Store
from campbase.talk import Talk
from campbase.deck_resources import attachment_name


class ETagHandler(BaseHTTPRequestHandler):
    def log_message(self,*_):pass
    def do_GET(self):
        if '/attachment/' in self.path:
            self.send_response(200);self.end_headers();self.wfile.write(b'%PDF-test');return
        self.server.reads.append(self.headers.get('If-None-Match'))
        if self.headers.get('If-None-Match') == '"v1"':
            self.send_response(304);self.end_headers();return
        data=json.dumps({'id':1,'cards':[{'title':'Original'}]}).encode()
        self.send_response(200);self.send_header('ETag','"v1"');self.end_headers();self.wfile.write(data)
    def do_POST(self):
        self.send_response(200);self.end_headers();self.wfile.write(b'{"ocs":{"meta":{"statuscode":200},"data":{}}}' if self.path.startswith('/ocs/') else b'{}')


class ETagTests(unittest.TestCase):
    def test_actual_304_reuses_unchanged_data_but_verification_is_fresh(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),ETagHandler);server.reads=[]
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            api=Deck(SimpleNamespace(server=f'http://127.0.0.1:{server.server_port}',username='alice',password='dummy'),allow_local=True)
            result=api.cached_get('/boards')
            result['cards'][0]['title']='Mutated locally'
            self.assertEqual(api.cached_get('/boards')['cards'][0]['title'],'Original')
            api.request('POST','/chat/room123/read',{},service='chat')
            api.cached_get('/boards')
            api.request('GET','/boards')
            self.assertEqual(server.reads,[None,'"v1"','"v1"',None])
            api.request('POST','/boards',{})
            api.cached_get('/boards')
            self.assertIsNone(server.reads[-1])
            other=Deck(SimpleNamespace(server=api.server,username='bob',password='other'),allow_local=True)
            other.cached_get('/boards')
            self.assertIsNone(server.reads[-1])
            self.assertEqual(api.download_attachment(99,8,'file'), b'%PDF-test')
            with self.assertRaises(DeckError):api.download_attachment(99,8,'../remote')
        finally:server.shutdown();server.server_close()

    def test_invalidated_inflight_304_is_retried_without_a_validator(self):
        api=Deck(SimpleNamespace(server='https://cloud.example.invalid',username='alice',password='dummy'))
        key=api.server+'/index.php/apps/deck/api/v1.0/boards'
        generation=api._cache.version()
        api._cache.put(key, '"old"', {'title':'Stale'}, 10, generation)
        calls=[]
        class Opener:
            def open(self, request, **kwargs):
                calls.append(request.get_header('If-none-match'))
                if len(calls)==1:
                    api._cache.invalidate()
                    raise HTTPError(key,304,'Not Modified',{},io.BytesIO())
                response=io.BytesIO(b'{"title":"Fresh"}');response.headers={}
                return response
        api.opener=Opener()
        self.assertEqual(api.cached_get('/boards'),{'title':'Fresh'})
        self.assertEqual(calls,['"old"',None])

    def test_cache_has_limits_and_rejects_pre_mutation_insertions(self):
        cache=ConditionalCache(max_bytes=10,max_entries=2)
        generation,_=cache.get('a')
        for key in ['a','b','c']:cache.put(key,'etag',{'value':key},4,generation)
        self.assertEqual(len(cache.rows),2);self.assertLessEqual(cache.size,10)
        cache.invalidate();cache.put('late','etag',{},1,generation)
        self.assertFalse(cache.rows)
        generation,_=cache.get('a');cache.put('large','etag',{},11,generation)
        self.assertFalse(cache.rows)


class ResourceTests(unittest.TestCase):
    def setUp(self):
        self.api=Deck(SimpleNamespace(server='https://cloud.example.invalid',username='alice',password='dummy'))
        self.label={'id':4,'title':'Old','color':'3584e4'}
        self.board={'id':1,'permissions':{'PERMISSION_MANAGE':True,'PERMISSION_EDIT':True},'labels':[self.label]}
        self.api.check_board=Mock(return_value=copy.deepcopy(self.board))
        self.api.request=Mock()

    def test_label_update_checks_concurrent_changes_and_permissions_before_writing(self):
        original=copy.deepcopy(self.label)
        changed={**self.label,'title':'Remote change'}
        self.api.check_board.return_value={**self.board,'labels':[changed]}
        with self.assertRaises(ConflictError):self.api.manage_label(1,original,title='New',color='#3584e4')
        self.api.request.assert_not_called()
        self.api.check_board.return_value={**self.board,'permissions':{}}
        with self.assertRaises(DeckError):self.api.manage_label(1,original,delete=True)
        self.api.request.assert_not_called()

    def test_label_update_and_delete_are_verified(self):
        saved={**self.label,'title':'New','color':'FF0000'}
        self.api.check_board.side_effect=[self.board,{**self.board,'labels':[saved]}]
        self.assertEqual(self.api.manage_label(1,self.label,title='New',color='#ff0000')['labels'],[saved])
        self.api.request.assert_called_once_with('PUT','/boards/1/labels/4',{'title':'New','color':'FF0000'})
        self.api.request.reset_mock();self.api.check_board.side_effect=[self.board,self.board]
        with self.assertRaises(DeckError):self.api.manage_label(1,self.label,delete=True)
        self.api.request.assert_called_once_with('DELETE','/boards/1/labels/4')

    def test_board_restore_confirms_state_and_is_idempotent(self):
        self.api.check_board.side_effect=[{**self.board,'deletedAt':10},self.board,self.board]
        self.api.restore_board(1);self.api.restore_board(1)
        self.api.request.assert_called_once_with('POST','/boards/1/undo_delete')

    def test_attachment_upload_uses_current_stack_and_confirms_acknowledgement(self):
        self.api.get_card=Mock(return_value={'id':99,'stackId':20})
        checkpoint=Mock()
        self.api.request.return_value={'id':8}
        self.api.upload_attachment(1,10,99,'../example\r\n.pdf',b'%PDF-test',checkpoint)
        args=self.api.request.call_args
        self.assertEqual(args.args[:2],('POST','/boards/1/stacks/20/cards/99/attachments'))
        self.assertIn(b'filename="example.pdf"',args.args[2]);checkpoint.assert_called_once_with()
        self.api.request.return_value=None
        with self.assertRaises(DeckError):self.api.upload_attachment(1,10,99,'file.txt',b'test')

    def test_attachment_list_validates_and_follows_moved_card(self):
        self.api.get_card=Mock(return_value={'id':99,'stackId':20})
        self.api.request.return_value=[{'id':1,'data':'example.pdf'},{'id':2,'deletedAt':20}]
        self.assertEqual(len(self.api.attachments(1,10,99)),1)
        self.api.request.assert_called_once_with('GET','/boards/1/stacks/20/cards/99/attachments',version='1.1')
        self.api.request.return_value={'unexpected':True}
        with self.assertRaises(DeckError):self.api.attachments(1,10,99)
        self.assertEqual(attachment_name({'data':'../../file.txt'}),'file.txt')

    def test_label_cache_updates_all_cards_and_preserves_other_board(self):
        with tempfile.TemporaryDirectory() as d:
            store=Store(d)
            store.put('snapshot',{'boards':[self.board,{'id':2}], 'stacks':{'1':[{'cards':[{'labels':[self.label]}]}]}})
            store.replace_board_labels({**self.board,'labels':[]})
            result=store.get('snapshot')
            self.assertFalse(result['stacks']['1'][0]['cards'][0]['labels'])
            self.assertEqual(result['boards'][1],{'id':2})

    def test_recovery_records_are_account_scoped_and_preserve_other_preferences(self):
        with tempfile.TemporaryDirectory() as d:
            store=Store(d)
            store.put('deleted_board:https://a|alice:1',{'id':1,'title':'A'})
            store.put('deleted_board:https://b|alice:1',{'id':1,'title':'B'})
            self.assertEqual(store.deleted_boards('https://a','alice')[0][1]['title'],'A')
            store.put('board_metadata',{'2':{'icon':'existing'}})
            store.restore_board_presentation({'id':1,'metadata':{'icon':'restored'},'colors':{'10':'red'}})
            self.assertEqual(store.get('board_metadata')['2'],{'icon':'existing'})
            self.assertEqual(store.settings()['colors']['10'],'red')


class TalkMutationTests(unittest.TestCase):
    def setUp(self):
        self.api=Mock();self.talk=Talk(self.api)
        self.item={'id':5,'actorType':'users','actorId':'alice','message':'Original','timestamp':int(time.time())}
        self.features={'edit-messages','delete-messages','chat-get-context'}

    def test_edit_and_delete_require_owned_fresh_context_and_confirmed_parent(self):
        event={'systemMessage':'message_edited','parent':{**self.item,'message':'New'}}
        self.api.request.side_effect=[[self.item],event]
        self.assertEqual(self.talk.change_message('room123',self.item,'alice',self.features,text='New'),event)
        self.assertEqual(self.api.request.call_args.args[:2],('PUT','/chat/room123/5'))
        self.api.request.reset_mock();self.api.request.side_effect=[[self.item],{'parent':{'id':5,'deleted':True}}]
        self.talk.change_message('room123',self.item,'alice',self.features,delete=True)
        self.assertEqual(self.api.request.call_args.args[:2],('DELETE','/chat/room123/5'))

    def test_stale_other_user_and_expired_messages_cannot_be_overwritten(self):
        for current,uid in [({**self.item,'message':'Someone changed it'},'alice'),(self.item,'bob'),
                            ({**self.item,'timestamp':0},'alice')]:
            self.api.request.reset_mock();self.api.request.side_effect=None;self.api.request.return_value=[current]
            with self.assertRaises(DeckError):self.talk.change_message('room123',self.item,uid,self.features,text='New')
            self.assertEqual(self.api.request.call_count,1)
        self.api.request.reset_mock()
        with self.assertRaises(DeckError):self.talk.change_message('room123',self.item,'alice',set(),delete=True)
        self.api.request.assert_not_called()

    def test_lost_edit_response_is_reconciled_without_a_second_write(self):
        self.api.request.return_value=[{**self.item,'message':'New'}]
        result=self.talk.change_message('room123',self.item,'alice',self.features,text='New')
        self.assertEqual(result['message'],'New');self.api.request.assert_called_once()
