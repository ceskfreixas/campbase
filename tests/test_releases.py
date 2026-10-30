# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Release metadata and the publishable notes must match the running version."""
from pathlib import Path
import re
import json
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET

from campbase import APP_ID, VERSION
from campbase.releases import RELEASE_VERSION, sections

ROOT = Path(__file__).resolve().parents[1]


class ReleaseTests(unittest.TestCase):
    def test_application_identity_matches_package_and_icons(self):
        manifest = json.loads((ROOT / f'{APP_ID}.json').read_text())
        self.assertEqual(manifest['app-id'], APP_ID)
        metadata = ET.parse(ROOT / f'data/{APP_ID}.metainfo.xml')
        self.assertEqual(metadata.findtext('id'), APP_ID)
        self.assertEqual(metadata.findtext('launchable'), f'{APP_ID}.desktop')
        desktop = (ROOT / f'data/{APP_ID}.desktop').read_text()
        self.assertIn(f'Icon={APP_ID}\n', desktop)
        self.assertTrue((ROOT / f'data/icons/{APP_ID}.svg').is_file())
        symbolic = ROOT / f'data/icons/hicolor/symbolic/apps/{APP_ID}-symbolic.svg'
        self.assertTrue(symbolic.is_file())
        self.assertEqual(ET.parse(symbolic).getroot().get('viewBox'), '0 0 16 16')
        for name in ['comments', 'assigned', 'conversations', 'link', 'reaction']:
            self.assertTrue((ROOT / f'data/icons/hicolor/scalable/actions/{APP_ID}-{name}-symbolic.svg').is_file())

    def test_current_version_has_matching_notes_and_package_metadata(self):
        self.assertEqual(VERSION, RELEASE_VERSION)
        build = (ROOT / 'meson.build').read_text()
        self.assertEqual(re.search(r"version: '([^']+)'", build)[1], VERSION)
        appstream = ET.parse(ROOT / 'data/cat.ceskfreixas.Campbase.metainfo.xml')
        self.assertEqual(appstream.find('releases/release').get('version'), VERSION)

    def test_release_notes_export_in_all_six_languages(self):
        for language in ['ca', 'eu', 'gl', 'es', 'oc', 'en']:
            with self.subTest(language=language):
                result = subprocess.run([sys.executable, str(ROOT / 'scripts/release_notes.py'),
                                         '--language', language], check=True, capture_output=True, text=True)
                self.assertIn('Campbase', result.stdout)
                self.assertEqual(result.stdout.count('\n- **'), len(sections()))
                self.assertIn(VERSION, result.stdout)
