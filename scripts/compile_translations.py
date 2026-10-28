#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Compile the standard PO catalogs for development outside Flatpak."""
from pathlib import Path
import subprocess
root = Path(__file__).resolve().parents[1]
for source in sorted((root/'po').glob('*.po')):
    target = root/'po/locale'/source.stem/'LC_MESSAGES/campbase.mo'
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['msgfmt','--check','--check-format','-o',str(target),str(source)],check=True)
