# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Catalog coverage, fallback behavior and safe preference reads."""
import ast
import gettext
import json
import os
from pathlib import Path
import sqlite3
import string
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch
from campbase import i18n

ROOT=Path(__file__).resolve().parents[1]


class LanguageTests(unittest.TestCase):
    def tearDown(self):
        i18n.configure()

    def test_system_languages_and_english_fallback(self):
        for tag,expected in [('ca_ES.UTF-8','ca'),('eu_ES','eu'),('gl_ES@agal','gl'),('es_MX','es'),('oc_ES@aranese','oc'),('en_GB','en'),('fr_FR','en'),('de_DE','en'),('C.UTF-8','en')]:
            self.assertEqual(i18n.system_language({'LANG':tag}),expected)
        self.assertEqual(i18n.system_language({'LANGUAGE':'eu:en','LANG':'ca_ES'}),'eu')
        self.assertEqual(i18n.system_language({'LANGUAGE':'fr:ca'}),'en')

    def test_live_messages_keep_formatting_plural_and_literal_content(self):
        i18n.configure('ca', user_choice=True)
        version = i18n._('Versió {version}').format(version='0.1.0')
        count = i18n.ngettext('{count} targeta', '{count} targetes', 2).format(count=2)
        combined = 'Projecte: ' + i18n._('Preferències')
        literal = str(i18n._('Descripció'))
        i18n.configure('en', user_choice=True)
        self.assertEqual(version.render(), 'Version 0.1.0')
        self.assertEqual(count.render(), '2 cards')
        self.assertEqual(combined.render(), 'Projecte: Preferences')
        self.assertEqual(literal, 'Descripció')

    def test_automatic_choice_restores_the_original_desktop_language(self):
        with patch.dict(i18n._SYSTEM_ENVIRONMENT, {'LANG':'ca_ES.UTF-8', 'LANGUAGE':'ca'}):
            i18n.configure('en', user_choice=True)
            with patch.dict(os.environ, {'LANGUAGE':'en:ca'}):
                self.assertEqual(i18n.configure('auto', user_choice=True), 'ca')

    def test_reading_language_does_not_recover_or_modify_pending_creates(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'campbase';path.mkdir()
            with closing(sqlite3.connect(path/'cache.sqlite3')) as db, db:
                db.execute('CREATE TABLE state (key TEXT PRIMARY KEY,value TEXT)')
                db.execute('CREATE TABLE outbox (state TEXT)')
                db.execute('INSERT INTO state VALUES (?,?)',('settings',json.dumps({'language':'eu'})))
                db.execute('INSERT INTO outbox VALUES (?)',('sending',))
            with patch.dict(os.environ,{'XDG_DATA_HOME':directory}):
                self.assertEqual(i18n.saved_preference(),'eu')
            with closing(sqlite3.connect(path/'cache.sqlite3')) as db, db:
                self.assertEqual(db.execute('SELECT state FROM outbox').fetchone()[0],'sending')

    def test_all_source_messages_and_placeholders_exist_in_every_catalog(self):
        singular=set();plural=[]
        for path in (ROOT/'campbase').glob('*.py'):
            for node in ast.walk(ast.parse(path.read_text())):
                if not isinstance(node,ast.Call) or not isinstance(node.func,ast.Name):continue
                if node.func.id=='_' and node.args and isinstance(node.args[0],ast.Constant):singular.add(node.args[0].value)
                if node.func.id=='ngettext':plural.append((node.args[0].value,node.args[1].value))
        fields=lambda text:{item[1] for item in string.Formatter().parse(text) if item[1]}
        for language in i18n.LANGUAGES:
            catalog=gettext.translation('campbase',localedir=i18n.LOCALE_DIR,languages=[language])
            for key in singular:
                self.assertIn(key,catalog._catalog,(language,key))
                self.assertTrue(catalog.gettext(key))
                self.assertEqual(fields(key),fields(catalog.gettext(key)))
            for one,many in plural:
                for number in [0,1,2,9]:
                    text=catalog.ngettext(one,many,number)
                    self.assertEqual(fields(one),fields(text))
                    self.assertIn((one,int(number!=1)),catalog._catalog)

    def test_persisted_errors_follow_the_selected_language(self):
        with patch.dict(os.environ,{'CAMPBASE_LANGUAGE':'eu'}):
            i18n.configure()
            self.assertEqual(i18n.saved_error("No s'ha pogut sincronitzar"),'Ezin izan da sinkronizatu')
            self.assertEqual(i18n.saved_error('Could not sync'),'Ezin izan da sinkronizatu')
            self.assertIn('503',i18n.saved_error('Nextcloud returned an error (503).'))
