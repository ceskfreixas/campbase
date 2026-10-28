# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
import unittest
from campbase.update_targets import destination, matches_comment
from campbase.mention_style import mention_spans
from campbase.collaboration import comment_tokens, display_comment


class UpdateTargetTests(unittest.TestCase):
    def test_comments_use_stable_ids_and_deck_deep_links(self):
        target = destination({'link':'https://cloud.example.invalid/apps/deck/#/board/12/card/34/comments/56'})
        self.assertEqual((target['board_id'], target['card_id'], target['comment_id'], target['section']), (12,34,'56','comments'))
        self.assertTrue(matches_comment({'id':56},target))
        self.assertFalse(matches_comment({'id':57},target))
        target = destination({'event':'self-mentioned','key':'local:comment:34:56','board_id':12,'card_id':34})
        self.assertEqual(target['comment_id'],'56')

    def test_activity_rich_parameters_select_the_correct_section(self):
        for extra,section in [({'comment':{'id':'56'}},'comments'), ({'assigneduser':{'id':'alice'}},'assignees'),
                              ({'label':{'id':'7'}},'labels'), ({'after':{'id':'dt:2027-01-01'}},'due'),
                              ({'stackBefore':{'id':'4'}},'column'), ({'acl':{'id':'alice'}},'members')]:
            target=destination({'subject_rich':['Translated text',{'board':{'id':'12'},'card':{'id':'34'},**extra}]})
            self.assertEqual((target['board_id'],target['card_id'],target['section']),(12,34,section))

    def test_notifications_resolve_from_metadata_not_translated_subjects(self):
        common={'notification_id':1,'object_type':'card','object_id':'34','subject':'Unrelated translated wording',
                'subjectRichParameters':{'deck-card':{'id':'34'},'deck-board':{'id':'12'},'user':{'id':'alice'}}}
        self.assertEqual(destination(common)['section'],'assignees')
        mention={**common,'message':'@bob hello','datetime':'2026-10-28T12:00:00Z'}
        target=destination(mention)
        self.assertEqual(target['section'],'comments')
        self.assertEqual(target['comment_actor'],'alice')
        self.assertEqual(destination({**target,'kind':'card'})['comment_actor'],'alice')
        self.assertTrue(matches_comment({'message':'@bob hello','actorId':'alice','creationDateTime':'2026-10-28T13:00:00+01:00'},target))
        self.assertFalse(matches_comment({'message':'@bob hello','actorId':'bob','creationDateTime':'2026-10-28T12:00:00Z'},target))
        self.assertFalse(matches_comment({'message':'@bob hello','actorId':'alice','creationDateTime':'2026-10-27T12:00:00Z'},target))
        due={**common,'subjectRichParameters':{'deck-card':{'id':'34'},'deck-board':{'id':'12'}}}
        self.assertEqual(destination(due)['section'],'due')
        self.assertEqual(destination({'notification_id':2,'object_type':'board','object_id':'12'})['section'],'members')

    def test_unknown_targets_do_not_guess_from_visible_text(self):
        self.assertEqual(destination({'title':'Someone mentioned you in card 34'}),{})
        self.assertEqual(destination({'subject_rich':['text',{'after':'unexpected'}]}),{})

    def test_mention_ranges_use_utf8_and_do_not_color_emails_or_partial_users(self):
        text='Sí, @alice. mail@alice.test @alice2 @alice@example.invalid!'
        spans=mention_spans(text,['@alice','@alice@example.invalid'])
        self.assertEqual([text.encode()[start:end].decode() for start,end in spans],['@alice','@alice@example.invalid'])
        item={'message':'Hola @"user/Alícia Miró" <b>text</b>',
              'mentions':[{'mentionId':'Alícia Miró','mentionDisplayName':'Alícia'}]}
        text=display_comment(item)
        spans=mention_spans(text,comment_tokens(item))
        self.assertEqual([text.encode()[start:end].decode() for start,end in spans],['@Alícia'])
        self.assertIn('<b>text</b>',text)
