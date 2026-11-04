# SPDX-License-Identifier: GPL-3.0-or-later
import copy
import tempfile
import unittest
from types import SimpleNamespace
from campbase.deck import OfflineError, ConflictError
from campbase.storage import Store
from campbase.workflow_api import WorkflowAPI
from campbase.workflow_state import save_options, options, merge_labels, resource_choices, suggested_choice, NOT_NOW_TITLES, not_now_ids, visible_labels
from campbase.card_movement import perform_move
from campbase.undo import undo_action


class SetupAPI(WorkflowAPI):
    def __init__(self):
        self.stacks=[];self.labels=[];self.writes=0;self.allowed=True;self.editable=True;self.uncertain=False
    def check_board(self,board):return {'permissions':{'PERMISSION_MANAGE':self.allowed,'PERMISSION_EDIT':self.editable},'labels':copy.deepcopy(self.labels)}
    def request(self,method,path):
        assert method=='GET' and path=='/boards/1/stacks'
        return copy.deepcopy(self.stacks)
    def create_stack(self,board,title,order):
        self.writes+=1
        result={'id':10,'title':title,'order':order,'cards':[]}
        self.stacks.append(result)
        if self.uncertain:raise OfflineError('lost response')
        return copy.deepcopy(result)

    def create_label(self,board,title,color):
        self.writes+=1
        result={'id':9,'title':title,'color':color};self.labels.append(result)
        if self.uncertain:raise OfflineError('lost response')
        return copy.deepcopy(result)


class WorkflowTests(unittest.TestCase):
    def test_setup_is_confirmed_idempotent_and_recognizes_other_languages(self):
        api=SetupAPI();api.uncertain=True
        self.assertEqual(api.ensure_not_now_stack(1,'Ara no')['id'],10)
        self.assertEqual(api.ensure_not_now_stack(1,'Not now')['id'],10)
        self.assertEqual(api.writes,1)

    def test_setup_never_writes_without_permission_or_on_ambiguous_columns(self):
        api=SetupAPI();api.allowed=False
        with self.assertRaises(ConflictError):api.ensure_not_now_stack(1,'Ara no')
        self.assertEqual(api.writes,0)
        api.allowed=True;api.stacks=[{'id':1,'title':'Ara no'},{'id':2,'title':'Not now'}]
        with self.assertRaises(ConflictError):api.ensure_not_now_stack(1,'Ara no')
        self.assertEqual(api.writes,0)

    def test_hold_label_retries_reuse_shared_aliases_and_check_fresh_permissions(self):
        api=SetupAPI();api.uncertain=True
        self.assertEqual(api.ensure_hold_label(1,'En espera')['id'],9)
        self.assertEqual(api.ensure_hold_label(1,'On hold')['id'],9)
        self.assertEqual(api.writes,1)
        api.labels=[];api.editable=False
        with self.assertRaises(ConflictError):api.ensure_hold_label(1,'En espera')
        self.assertEqual(api.writes,1)
        api.labels=[{'id':9,'title':'On hold'},{'id':10,'title':'En espera'}]
        with self.assertRaises(ConflictError):api.ensure_hold_label(1,'En espera')
        self.assertEqual(api.writes,1)

    def test_suggestions_prefer_ids_and_never_guess_ambiguous_names(self):
        items=[None,{'id':10,'title':'Not now'},{'id':20,'title':'Ara no'}]
        self.assertEqual(suggested_choice(items,20,NOT_NOW_TITLES),2)
        self.assertEqual(suggested_choice(items,None,NOT_NOW_TITLES),0)
        self.assertEqual(suggested_choice(items[:2],None,NOT_NOW_TITLES),1)

    def test_creation_is_offered_only_when_the_shared_resource_does_not_exist(self):
        ordinary={'id':1,'title':'Triage'};existing={'id':2,'title':'Ara no'}
        self.assertEqual(resource_choices([ordinary],None,NOT_NOW_TITLES),[None,ordinary])
        self.assertEqual(resource_choices([ordinary,existing],None,NOT_NOW_TITLES),[existing,ordinary])
        renamed={'id':3,'title':'Backlog'}
        self.assertEqual(resource_choices([ordinary,renamed],3,NOT_NOW_TITLES),[renamed,ordinary])
        duplicate={'id':4,'title':'Not now'}
        self.assertNotIn(None,resource_choices([ordinary,existing,duplicate],None,NOT_NOW_TITLES))

    def test_settings_preserve_project_identity_and_are_scoped_to_board(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);store.put('board_metadata',{'1':{'icon':'custom','description':'Keep'}})
            save_options(store,1,hold_label=9,hold_columns=[10])
            self.assertEqual(store.get('board_metadata')['1']['description'],'Keep')
            self.assertEqual(options(store,2),{})
            self.assertEqual(options(store,1)['hold_columns'],[10])

    def test_hidden_not_now_covers_reused_renamed_and_manually_created_columns(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder)
            stacks=[{'id':10,'title':'Backlog'},{'id':20,'title':'Ara no'}]
            window=SimpleNamespace(store=store,board_id=1,stacks=lambda:stacks)
            self.assertEqual(not_now_ids(window),set())
            save_options(store,1,not_now_enabled=False)
            self.assertEqual(not_now_ids(window),{20})
            save_options(store,1,not_now_stack=10)
            self.assertEqual(not_now_ids(window),{10})
            stacks[0]['title']='Renamed elsewhere'
            self.assertEqual(not_now_ids(window),{10})
            save_options(store,1,hold_label=9,hold_enabled=False)
            self.assertEqual(visible_labels(window,[{'id':9},{'id':11}]),[{'id':11}])

    def test_label_merge_preserves_concurrent_unrelated_labels(self):
        held={'id':9};remote={'id':10};base={'id':11}
        self.assertEqual(merge_labels([remote,base],[held,base],[base]),[remote,base,held])
        self.assertEqual(merge_labels([held,remote,base],[base],[held,base]),[remote,base])

    def test_pause_and_resume_are_durable_and_undo_preserves_other_labels(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);held={'id':9,'title':'En espera'};remote={'id':10,'title':'Other'}
            card={'id':1,'stackId':10,'title':'A','labels':[remote],'order':0}
            store.put('snapshot',{'boards':[{'id':1}],'stacks':{'1':[{'id':10,'cards':[card]}]}})
            payload={'board_id':1,'card_id':1,'source_stack':10,'target_stack':10,'order':0,
                     'archived':False,'label_state':{'desired':[held],'base':[]}}
            op=store.enqueue('move',payload,undo={'before':{'stack_id':10,'order':0,'archived':False,'labels':[]}})
            self.assertEqual({item['id'] for item in store.view()['stacks']['1'][0]['cards'][0]['labels']},{9,10})
            store.mark_undo_attempted(op);undo_action(store,op)
            self.assertEqual(store.view()['stacks']['1'][0]['cards'][0]['labels'],[remote])
            self.assertEqual(len(store.operations()),2)

    def test_retry_after_lost_pause_response_does_not_move_or_assign_twice(self):
        held={'id':9};card={'id':1,'stackId':10,'order':0,'labels':[],'archived':False}
        payload={'board_id':1,'card_id':1,'source_stack':10,'target_stack':20,'order':0,
                 'archived':False,'label_state':{'desired':[held],'base':[]}}
        class API:
            moves=0;writes=0
            def card_for_move(self,*args):return copy.deepcopy(card)
            def move_card(self,*args,**kwargs):
                self.moves+=1;card.update(stackId=20,order=0);return copy.deepcopy(card)
            def set_archived(self,*args,**kwargs):return copy.deepcopy(card)
            def update_labels(self,board,stack,key,desired,base,current=None):
                if not card['labels']:
                    self.writes+=1;card['labels']=[held];raise OfflineError('lost response')
                return copy.deepcopy(card)
        class Storage:
            def checkpoint_move(self,key,changes):payload.update(changes);return copy.deepcopy(payload)
        api=API();store=Storage();operation={'id':1,'payload':payload}
        with self.assertRaises(OfflineError):perform_move(api,store,operation)
        self.assertEqual(perform_move(api,store,operation)['labels'],[held])
        self.assertEqual((api.moves,api.writes),(1,1))
