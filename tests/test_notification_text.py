# SPDX-License-Identifier: GPL-3.0-or-later
import tempfile
import unittest
from campbase import i18n
from campbase.notification_text import notification_title
from campbase.storage import Store
from campbase.updates import entries, erase_entries


class NotificationTextTests(unittest.TestCase):
    def setUp(self):
        i18n.configure('ca', user_choice=True)
        self.card={'id':'99','name':'Campbase'}
        self.board={'id':'1','name':'Aixeta'}
        self.user={'id':'bob','name':'Robert'}

    def tearDown(self):
        i18n.configure()

    def notice(self, rich, **extra):
        return {'app':'deck','notification_id':1,'subject':'Original',
                'subjectRichParameters':rich,**extra}

    def test_retained_deck_types_use_consistent_words_and_punctuation(self):
        common={'user':self.user,'deck-card':self.card,'deck-board':self.board}
        cases=[(self.notice(common),"Robert t'ha assignat la targeta «Campbase»."),
               (self.notice(common,message='@alice hola'),"Robert t'ha mencionat en un comentari de la targeta «Campbase»."),
               (self.notice(common,message='👍 @alice'),'Robert ha reaccionat 👍 al teu comentari de la targeta «Campbase».'),
               (self.notice({'user':self.user,'deck-board':self.board}),'Robert ha compartit el tauler «Aixeta» amb tu.'),
               (self.notice({'deck-card':self.card,'deck-board':self.board}),'La targeta «Campbase» del tauler «Aixeta» ha arribat al venciment.')]
        for notice, expected in cases:
            self.assertEqual(str(notification_title(notice)),expected)

    def test_talk_keeps_message_content_separate_and_handles_direct_and_group(self):
        common={'user':self.user,'call':{'name':'Equip'}}
        message=self.notice(common,app='spreed',object_type='chat',message='private content')
        self.assertEqual(str(notification_title(message)),"Robert t'ha enviat un missatge a «Equip».")
        common['call']['name']='Robert'
        self.assertEqual(str(notification_title(message)),"Robert t'ha enviat un missatge.")
        self.assertEqual(notification_title({**message,'object_type':'call'}),'Original')

    def test_unknown_metadata_does_not_invent_events(self):
        for rich in [None,{},[],{'user':self.user,'deck-card':self.card}]:
            self.assertEqual(notification_title(self.notice(rich)),'Original')
        self.assertEqual(notification_title(self.notice({'user':self.user,'deck-board':self.board},app='mail')),'Original')

    def test_own_actions_and_legacy_activity_never_fill_or_delete_from_server(self):
        incoming=self.notice({'user':self.user,'deck-card':self.card,'deck-board':self.board})
        own=self.notice({'user':{'id':'alice','name':'Alícia'},'deck-board':self.board},notification_id=2)
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory)
            store.put('profile',{'uid':'alice'})
            store.put('updates',{'notifications':[incoming,own],'activity':[{'activity_id':3,'subject':'Moved'}],
                'comments':[{'key':'comments:99:3','count':3}]})
            store.record_notice({'key':'local:old','event':'own-comment','title':'Old'})
            rows=entries(store)
            self.assertEqual([r['key'] for r in rows],['n:1'])
            calls=[]
            class API:
                def dismiss_notification(self, notice_id):calls.append(notice_id)
            erase_entries(API(),store,rows)
            self.assertEqual(calls,[1])
            self.assertFalse(entries(Store(directory)))

    def test_live_six_language_titles_preserve_literal_names(self):
        notice=self.notice({'user':self.user,'deck-board':{'name':'<b>{name}</b>'}})
        text=notification_title(notice)
        for language in ('ca','es','en','gl','eu','oc'):
            i18n.configure(language,user_choice=True)
            self.assertIn('<b>{name}</b>',text.render())
            self.assertTrue(text.render().endswith('.'))
        i18n.configure('en',user_choice=True)
        self.assertIn('shared board',text.render())
