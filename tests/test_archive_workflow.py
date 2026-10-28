# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Archive defaults and undo are tested against synthetic local data only."""
import copy,http.server,json,re,tempfile,threading,unittest
from types import SimpleNamespace
from unittest.mock import patch
from test_sync import Fixture
from campbase.settings import archive_overrides,archives_visible
from campbase.storage import Store
from campbase.sync import SyncEngine
from campbase.deck import Deck,ConflictError,OfflineError
from campbase.due_dates import same_due
from campbase.undo import undo_action

class ArchiveSettingsTests(unittest.TestCase):
 def test_general_change_resets_all_exceptions_and_keeps_other_settings(self):
  with tempfile.TemporaryDirectory() as directory:
   store=Store(directory);store.set_setting('archived_overrides',{'10':True,'20':False,'30':False})
   store.set_setting('archived_columns',['40']);store.set_setting('columns_per_row',3)
   for default in (True,False,True):
    store.set_archived_default(default);settings=store.settings()
    self.assertEqual(settings['archived_overrides'],{})
    self.assertNotIn('archived_columns',settings);self.assertEqual(settings['columns_per_row'],3)
    for column in (10,20,30,40):self.assertEqual(archives_visible(settings,column),default)
 def test_legacy_explicit_shown_columns_are_preserved(self):
  settings={'archived_columns':['10']}
  self.assertEqual(archive_overrides(settings),{'10':True})
  settings['show_archived_default']=True
  self.assertTrue(archives_visible(settings,20))
 def test_column_exception_can_be_created_after_a_general_change(self):
  settings={'show_archived_default':True,'archived_overrides':{'10':False}}
  self.assertFalse(archives_visible(settings,10));self.assertTrue(archives_visible(settings,20))

class StrictFixture(Fixture):
 def do_GET(self):
  match=re.search(r'/stacks/(\d+)/cards/(\d+)$',self.path)
  if match and int(match[1])!=self.server.cards.get(int(match[2]),{}).get('stackId'):
   self.respond({},404);return
  super().do_GET()

class ArchiveUndoTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),StrictFixture)
  threading.Thread(target=cls.server.serve_forever,daemon=True).start()
 @classmethod
 def tearDownClass(cls):cls.server.shutdown();cls.server.server_close()
 def setUp(self):
  directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup);self.store=Store(directory.name)
  self.server.cards={99:{'id':99,'stackId':10,'title':'Original','description':'Preserve','labels':[],
   'owner':'test','archived':False,'order':0,'duedate':None}}
  self.server.board={'id':1,'title':'Synthetic','labels':[]};self.server.reads=[];self.server.writes=[]
  self.server.reject_move=False;self.server.reject_labels=False;self.server.reject_archive=False;self.server.attachments=[]
  self.api=Deck(SimpleNamespace(server=f'http://127.0.0.1:{self.server.server_port}',username='test',password='dummy'),allow_local=True)
  self.store.put('snapshot',self.api.fetch());self.engine=SyncEngine(self.store);self.engine.api=self.api
  self.addCleanup(self.engine.close)
 def action(self,kind='move',card_id=99,archived=None,before_archived=False):
  if kind=='move':
   payload={'board_id':1,'card_id':card_id,'source_stack':10,'target_stack':20,'order':0}
   if archived is not None:payload.update(archived=archived,base_archived=before_archived)
  else:payload={'board_id':1,'card_id':card_id,'stack_id':10,'changes':{'archived':True},'base':{'archived':False}}
  return self.store.enqueue(kind,payload,undo={'before':{'stack_id':10,'order':0,'archived':before_archived}})
 def card(self,card_id=99):
  return next(c for s in self.store.view()['stacks']['1'] for c in s['cards'] if c['id']==card_id)
 def test_offline_undo_removes_only_its_unsent_action(self):
  other=self.store.enqueue('update',{'board_id':1,'stack_id':10,'card_id':99,'changes':{'title':'Kept'},'base':{'title':'Original'}})
  action=self.action();undo_action(self.store,action)
  self.assertEqual([op['id'] for op in self.store.operations()],[other]);self.assertEqual(self.card()['title'],'Kept')
  self.assertEqual(self.card()['stackId'],10);self.assertFalse(self.server.writes)
 def test_synced_move_and_archive_undo_restores_both(self):
  action=self.action(archived=True);self.engine._send_pending()
  self.assertEqual(self.server.cards[99]['stackId'],20);self.assertTrue(self.server.cards[99]['archived'])
  undo_action(self.store,action);self.engine._send_pending()
  self.assertEqual(self.server.cards[99]['stackId'],10);self.assertFalse(self.server.cards[99]['archived'])
  self.assertFalse(self.store.operations())
 def test_archived_move_and_restoration_keep_undo_on_the_server(self):
  self.server.cards[99]['archived']=True;self.store.put('snapshot',self.api.fetch())
  for archived in (False,True):
   with self.subTest(archived=archived):
    action=self.store.enqueue('move',{'board_id':1,'card_id':99,'source_stack':10,
     'target_stack':20,'order':0,'archived':archived,'base_archived':True},
     undo={'before':{'stack_id':10,'order':0,'archived':True}})
    self.engine._send_pending()
    self.assertEqual(self.server.cards[99]['stackId'],20)
    self.assertEqual(self.server.cards[99]['archived'],archived)
    undo_action(self.store,action);self.engine._send_pending()
    self.assertEqual(self.server.cards[99]['stackId'],10)
    self.assertTrue(self.server.cards[99]['archived']);self.assertFalse(self.store.operations())
 def test_same_column_restore_happens_before_reorder_and_keeps_other_fields(self):
  self.server.cards[99].update(archived=True,done='2026-01-01T12:00:00Z')
  self.store.put('snapshot',self.api.fetch())
  op=self.store.enqueue('move',{'board_id':1,'card_id':99,'source_stack':10,'target_stack':10,
   'order':0,'archived':False,'base_archived':True})
  self.engine._send_pending()
  paths=[path.rsplit('/',1)[-1] for path,_ in self.server.writes]
  self.assertEqual(paths,['unarchive','reorder'])
  self.assertFalse(self.server.cards[99]['archived']);self.assertEqual(self.server.cards[99]['description'],'Preserve')
  self.assertEqual(self.server.cards[99]['done'],'2026-01-01T12:00:00Z');self.assertFalse(self.store.operations())
 def test_interruption_after_restore_resumes_the_original_archive_intent(self):
  self.server.cards[99]['archived']=True;self.store.put('snapshot',self.api.fetch())
  action=self.action(archived=True,before_archived=True)
  self.store.checkpoint_move(action,{'restore_started':True}) # Resume the previous release's protocol.
  with patch.object(self.api,'move_card',side_effect=OfflineError('offline')):
   with self.assertRaises(OfflineError):self.engine._send_pending()
  self.assertFalse(self.server.cards[99]['archived'])
  saved=self.store.operations()[0];self.assertTrue(saved['payload']['restore_started'])
  self.store=Store(self.store.directory);self.engine.store=self.store;self.engine._send_pending()
  self.assertEqual(self.server.cards[99]['stackId'],20);self.assertTrue(self.server.cards[99]['archived'])
  self.assertEqual(sum(path.endswith('/unarchive') for path,_ in self.server.writes),1)
  self.assertFalse(self.store.operations())
 def test_lost_final_archive_response_does_not_repeat_completed_steps(self):
  self.server.cards[99]['archived']=True;self.store.put('snapshot',self.api.fetch())
  action=self.action(archived=True,before_archived=True)
  self.store.checkpoint_move(action,{'restore_started':True});request=self.api.request
  def lose_response(method,path,*args,**kwargs):
   result=request(method,path,*args,**kwargs)
   if method=='PUT' and path.endswith('/archive'):raise OfflineError('lost response')
   return result
  with patch.object(self.api,'request',side_effect=lose_response):
   with self.assertRaises(OfflineError):self.engine._send_pending()
  writes=len(self.server.writes);self.engine._send_pending()
  self.assertEqual(len(self.server.writes),writes);self.assertTrue(self.server.cards[99]['archived'])
  self.assertFalse(self.store.operations())
 def test_remote_archive_change_is_not_overwritten_by_an_active_move(self):
  action=self.action();self.store.checkpoint_move(action,{'archived':False,'base_archived':False})
  self.server.cards[99]['archived']=True;self.engine._send_pending()
  self.assertTrue(self.server.cards[99]['archived']);self.assertFalse(self.server.writes)
  self.assertEqual(self.store.operations()[0]['state'],'blocked')
 def test_changed_position_after_partial_move_requires_explicit_force(self):
  action=self.action(archived=True);self.store.checkpoint_move(action,{'restore_started':True});self.server.reject_archive=True
  self.engine._send_pending();self.assertTrue(self.store.operations()[0]['payload']['move_done'])
  self.server.cards[99]['order']=3;self.server.reject_archive=False
  writes=len(self.server.writes);self.store.retry(action);self.engine._send_pending()
  self.assertEqual(len(self.server.writes),writes);self.assertEqual(self.server.cards[99]['order'],3)
  self.store.retry(action,force=True);self.engine._send_pending()
  self.assertEqual(self.server.cards[99]['order'],0);self.assertTrue(self.server.cards[99]['archived'])
  self.assertFalse(self.store.operations())
 def test_archive_placement_preserves_neighbor_contents_and_completion(self):
  self.server.cards[50]=dict(self.server.cards[99],id=50,stackId=20,archived=True,order=0,done='2026-01-01T12:00:00Z')
  self.server.cards[70]=dict(self.server.cards[99],id=70,stackId=20,archived=True,order=5)
  self.store.put('snapshot',self.api.fetch());self.action(archived=True);self.engine._send_pending()
  cards=sorted((c for c in self.server.cards.values() if c['stackId']==20),key=lambda c:(c['order'],c['id']))
  self.assertEqual([c['id'] for c in cards],[99,50,70]);self.assertFalse(self.store.operations())
  self.assertEqual(self.server.cards[50]['done'],'2026-01-01T12:00:00Z')
  self.assertEqual(self.server.cards[50]['description'],'Preserve')
  changes=[body for path,body in self.server.writes if path.endswith(('/cards/50','/cards/70'))]
  self.assertTrue(changes);self.assertTrue(all('archived' not in body for body in changes))
 def test_restoring_before_an_active_card_ignores_archived_order_slots(self):
  self.server.cards[99]['archived']=True
  self.server.cards[50]=dict(self.server.cards[99],id=50,stackId=20,archived=True,order=0)
  self.server.cards[70]=dict(self.server.cards[99],id=70,stackId=20,archived=False,order=0)
  self.store.put('snapshot',self.api.fetch());self.action(archived=False,before_archived=True)
  self.engine._send_pending()
  active=sorted((c for c in self.server.cards.values() if c['stackId']==20 and not c.get('archived')),key=lambda c:c['order'])
  self.assertEqual([c['id'] for c in active],[99,70]);self.assertTrue(self.server.cards[50]['archived'])
  self.assertFalse(self.store.operations())
 def test_deleted_archive_neighbor_is_not_restored_by_an_order_update(self):
  self.server.cards[99].update(stackId=20,archived=True)
  self.server.cards[50]=dict(self.server.cards[99],id=50,deletedAt=123,order=0)
  self.store.put('snapshot',self.api.fetch());action=self.action(archived=True)
  self.store.checkpoint_move(action,{'move_done':True,'archive_order':[{'id':99,'base':0,'order':0},{'id':50,'base':0,'order':1}]})
  self.engine._send_pending()
  self.assertEqual(self.server.cards[50]['deletedAt'],123);self.assertFalse(self.server.writes)
  self.assertEqual(self.store.operations()[0]['state'],'blocked')
 def test_neighbor_restored_during_order_confirmation_is_preserved(self):
  self.server.cards[99].update(stackId=20,archived=True)
  self.server.cards[50]=dict(self.server.cards[99],id=50,order=0)
  self.store.put('snapshot',self.api.fetch());action=self.action(archived=True)
  self.store.checkpoint_move(action,{'move_done':True,'archive_order':[{'id':99,'base':0,'order':0},{'id':50,'base':0,'order':1}]})
  read=self.api.get_card;count=0
  def restore_during_read(board,stack,card):
   nonlocal count
   if card==50:
    count+=1
    if count==1:self.server.cards[50]['archived']=False
   return read(board,stack,card)
  with patch.object(self.api,'get_card',side_effect=restore_during_read):self.engine._send_pending()
  self.assertFalse(self.server.cards[50]['archived']);self.assertEqual(self.server.cards[50]['order'],0)
  self.assertFalse(self.server.writes);self.assertEqual(self.store.operations()[0]['state'],'blocked')
 def test_later_edit_is_preserved_when_undoing_move(self):
  action=self.action()
  self.store.enqueue('update',{'board_id':1,'stack_id':20,'card_id':99,'changes':{'title':'Later edit'},'base':{'title':'Original'}})
  undo_action(self.store,action)
  self.assertEqual(self.card()['title'],'Later edit');self.assertEqual(self.card()['stackId'],10)
  self.engine._send_pending();self.assertEqual(self.server.cards[99]['title'],'Later edit')
  self.assertEqual(self.server.cards[99]['stackId'],10);self.assertFalse(self.store.operations())
 def test_uncertain_partial_move_retries_from_the_new_stack(self):
  action=self.action(archived=True);self.store.mark_undo_attempted(action)
  self.api.move_card(1,99,10,20,0) # Simulate a committed move with a lost response.
  undo_action(self.store,action);self.engine._send_pending()
  self.assertEqual(self.server.cards[99]['stackId'],10);self.assertFalse(self.server.cards[99]['archived'])
  self.assertFalse(self.store.operations())
 def test_create_id_is_remapped_for_a_later_archive_undo(self):
  create=self.store.enqueue('create',{'board_id':1,'stack_id':10,'title':'New card','description':'','order':1})
  action=self.action(kind='archive',card_id=-create);self.engine._send_pending()
  created=max(self.server.cards);self.assertTrue(self.server.cards[created]['archived'])
  undo_action(self.store,action);self.engine._send_pending()
  self.assertFalse(self.server.cards[created]['archived']);self.assertFalse(self.store.operations())
 def test_stale_undo_cannot_remove_a_newer_action(self):
  first=self.action();second=self.action(kind='archive')
  with self.assertRaises(ConflictError):undo_action(self.store,first)
  self.assertEqual([op['id'] for op in self.store.operations()],[first,second])
 def test_remote_move_to_another_stack_is_preserved(self):
  action=self.action();self.engine._send_pending()
  self.server.cards[99]['stackId']=30;self.store.put('snapshot',self.api.fetch())
  writes=len(self.server.writes)
  with self.assertRaises(ConflictError):undo_action(self.store,action)
  self.assertEqual(self.server.cards[99]['stackId'],30);self.assertEqual(len(self.server.writes),writes)

 def test_all_move_directions_keep_assignments_and_other_content(self):
  original=copy.deepcopy(self.server.cards[99])
  original.update(assignedUsers=[{'participant':{'uid':'alice','displayname':'Alícia Miró'}}],
                  done='2026-01-01T12:00:00Z',duedate='2026-12-01T15:30:00Z')
  for same_column in (False,True):
   for source_archived in (False,True):
    for target_archived in (False,True):
     with self.subTest(same=same_column,source=source_archived,target=target_archived):
      self.server.cards={99:dict(original,archived=source_archived)}
      self.store.put('snapshot',self.api.fetch());target=10 if same_column else 20
      self.store.enqueue('move',{'board_id':1,'card_id':99,'source_stack':10,'target_stack':target,
       'order':0,'archived':target_archived,'base_archived':source_archived})
      self.assertEqual(self.card()['assignedUsers'],original['assignedUsers'])
      self.engine._send_pending();self.assertFalse(self.store.operations())
      for card in (self.server.cards[99],self.card()):
       self.assertEqual(card['stackId'],target);self.assertEqual(card['archived'],target_archived)
       self.assertTrue(same_due(card['duedate'],original['duedate']))
       for key in ('assignedUsers','labels','done','title','description','owner'):
        self.assertEqual(card[key],original[key],key)

 def test_archive_move_request_count_is_independent_of_unchanged_neighbors(self):
  self.server.cards[99].update(archived=True)
  for index in range(100):
   self.server.cards[1000+index]=dict(self.server.cards[99],id=1000+index,stackId=20,order=index*100)
  self.store.put('snapshot',self.api.fetch());self.server.reads.clear();self.server.writes.clear()
  action=self.action(archived=True,before_archived=True)
  self.store.checkpoint_move(action,{'order':50});self.engine._send_pending()
  self.assertFalse(self.store.operations());self.assertEqual(len(self.server.writes),1)
  self.assertLessEqual(len(self.server.reads),4)
  self.assertFalse(any(path.endswith(('/archive','/unarchive','/reorder')) for path,_ in self.server.writes))
  cards=sorted((card for card in self.server.cards.values() if card['stackId']==20),key=lambda card:(card['order'],card['id']))
  self.assertEqual(cards[50]['id'],99)

 def test_direct_archive_move_resumes_after_a_lost_write_response(self):
  self.server.cards[99]['archived']=True;self.store.put('snapshot',self.api.fetch())
  self.action(archived=True,before_archived=True);request=self.api.request
  def lose_response(method,path,*args,**kwargs):
   result=request(method,path,*args,**kwargs)
   if method=='PUT' and path.endswith('/cards/99'):raise OfflineError('lost response')
   return result
  with patch.object(self.api,'request',side_effect=lose_response):
   with self.assertRaises(OfflineError):self.engine._send_pending()
  writes=len(self.server.writes);self.engine._send_pending()
  self.assertEqual(len(self.server.writes),writes);self.assertFalse(self.store.operations())

 def test_direct_archive_neighbor_conflict_preserves_the_remote_change(self):
  self.server.cards[50]=dict(self.server.cards[99],id=50,stackId=20,archived=True)
  self.store.put('snapshot',self.api.fetch());self.action(archived=True)
  update=self.api.update_card
  def change_neighbor(board,stack,card,*args,**kwargs):
   if card==50:self.server.cards[50]['archived']=False
   return update(board,stack,card,*args,**kwargs)
  with patch.object(self.api,'update_card',side_effect=change_neighbor):self.engine._send_pending()
  self.assertFalse(self.server.cards[50]['archived']);self.assertEqual(self.server.cards[50]['order'],0)
  self.assertEqual(self.store.operations()[0]['state'],'blocked')
