# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Release metadata and the publishable notes must match the running version."""
from pathlib import Path
import re
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET

from campbase import VERSION
from campbase.releases import RELEASE_VERSION

ROOT = Path(__file__).resolve().parents[1]


class ReleaseTests(unittest.TestCase):
    def test_current_version_has_matching_notes_and_package_metadata(self):
        self.assertEqual(VERSION, RELEASE_VERSION)
        build = (ROOT / 'meson.build').read_text()
        self.assertEqual(re.search(r"version: '([^']+)'", build)[1], VERSION)
        appstream = ET.parse(ROOT / 'data/cat.cesk.Campbase.metainfo.xml')
        self.assertEqual(appstream.find('releases/release').get('version'), VERSION)

    def test_release_notes_export_in_all_six_languages(self):
        for language in ['ca', 'eu', 'gl', 'es', 'oc', 'en']:
            with self.subTest(language=language):
                result = subprocess.run([sys.executable, str(ROOT / 'scripts/release_notes.py'),
                                         '--language', language], check=True, capture_output=True, text=True)
                self.assertIn('Campbase', result.stdout)
                self.assertEqual(result.stdout.count('\n- **'), 11)
                self.assertIn('Nextcloud Deck', result.stdout)
