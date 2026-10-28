# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Native editor regression checks; run on an isolated Xvfb display."""
import base64
import tempfile
from types import SimpleNamespace
from pathlib import Path
import gi
gi.require_version('Gtk','4.0')
gi.require_version('Adw','1')
from gi.repository import Adw, Gio
from campbase.assets import Assets
from campbase.rich_text import RichTextEditor, PARSER

Adw.init()
with tempfile.TemporaryDirectory() as directory:
    window = SimpleNamespace(assets=Assets(directory), demo=True)
    sources = ['**Negreta** i _cursiva_ i ~~ratllat~~ i <u>subratllat</u>',
               '# Títol\n\n- **Un**\n- Dos\n\n1. Primer\n2. Segon',
               '```python\nprint(42)\n\nprint(43)\n```\n\nFinal',
               '|A|B|\n|-|-|\n|1|2|\n\nFinal',
               '- primer\n  - segon\n    - tercer\n\nFinal',
               '[Enllaç](https://example.com)\n\n- [x] Fet\n- [ ] Pendent']
    for source in sources:
        editor = RichTextEditor(window, source)
        assert editor.get_markdown() == source
        editor.buffer.insert(editor.buffer.get_end_iter(), '!')
        result = editor.get_markdown()
        assert result.count('Final') == source.count('Final')
        if '```python' in source:
            assert '```python\nprint(42)\n\nprint(43)\n```' in result
        if 'tercer' in source:
            assert '    - tercer' in result
        if '<u>' in source:
            assert '<u>subratllat</u>' in result
        PARSER(result)
    editor = RichTextEditor(window, 'Paraula segona')
    changes = []
    editor.connect('changed', lambda *_: changes.append(True))
    editor.buffer.select_range(editor.buffer.get_start_iter(), editor.buffer.get_iter_at_offset(7))
    editor.toggle('bold')
    assert editor.get_markdown() == '**Paraula** segona' and changes
    editor.undo()
    assert editor.get_markdown() == 'Paraula segona'
    editor.redo()
    assert editor.get_markdown() == '**Paraula** segona'
    editor.buffer.select_range(editor.buffer.get_start_iter(),editor.buffer.get_end_iter())
    editor.list_format(False)
    assert editor.get_markdown() == '- **Paraula** segona'
    path = Path(directory)/'source.png'
    path.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1sAAAAASUVORK5CYII='))
    record = window.assets.import_file(Gio.File.new_for_path(str(path)))
    editor = RichTextEditor(window, '')
    editor.insert_image('bivac-image://'+record['token'], 'Imatge')
    assert record in editor.local_images()
    assert '![Imatge](bivac-image://' in editor.get_markdown()
    editor.buffer.select_range(editor.buffer.get_start_iter(),editor.buffer.get_end_iter())
    editor.list_format(False)
    assert '![Imatge](bivac-image://' in editor.get_markdown()
    assert len(editor.local_images()) == 1
    editor.buffer.set_text('Imatge eliminada')
    assert editor.local_images() == []
    for path in [window.assets.images, window.assets.records]:
        assert path.stat().st_mode & 0o077 == 0
print('PASS native formatting, undo/redo, Markdown preservation, lists, images and private assets')
