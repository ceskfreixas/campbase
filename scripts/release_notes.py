#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Export the in-app release notes as Markdown for a GitHub release."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from campbase import VERSION
from campbase.i18n import LANGUAGES, configure
from campbase.releases import RELEASE_VERSION, introduction, sections

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--language', choices=LANGUAGES, default='en')
args = parser.parse_args()
if VERSION != RELEASE_VERSION:
    parser.error('Update the release notes to match the application version.')
configure(args.language, user_choice=True)
print(introduction().render())
for title, text in sections():
    print('\n- **' + title.render() + '**: ' + text.render())
