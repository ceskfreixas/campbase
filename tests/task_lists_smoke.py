# SPDX-License-Identifier: GPL-3.0-or-later
"""Interactive tasks preserve formatting, nesting, history and editor drafts."""
import tempfile
import time
from types import SimpleNamespace
import gi
gi.require_version('Gtk', '4.0');gi.require_version('Adw', '1')
from gi.repository import Adw, Gdk, GLib, Gtk
from campbase.assets import Assets
from campbase.rich_text import RichTextEditor

Adw.init()
with tempfile.TemporaryDirectory() as folder:
    window = SimpleNamespace(assets=Assets(folder), demo=True)
    expected_icons = [
        'format-text-bold-symbolic', 'format-text-italic-symbolic', 'format-text-underline-symbolic',
        'format-text-strikethrough-symbolic', 'format-text-rich-symbolic', 'view-list-bullet-symbolic',
        'view-list-ordered-symbolic', 'cat.ceskfreixas.Campbase-task-list-symbolic',
        'cat.ceskfreixas.Campbase-link-symbolic', 'image-x-generic-symbolic', 'edit-undo-symbolic', 'edit-redo-symbolic']
    source = '- [ ] **Preparar**\n- [x] Publicar\n  - [ ] Revisar'
    editor = RichTextEditor(window, source)
    toolbar = editor.get_first_child()
    icons=[];separators=0;group=toolbar.get_first_child()
    while group:
        control=group.get_child().get_first_child()
        while control:
            if isinstance(control,Gtk.Separator):separators+=1
            else:icons.append(control.get_icon_name())
            control=control.get_next_sibling()
        group=group.get_next_sibling()
    assert icons == expected_icons and separators == 4
    assert len(editor.task_nodes) == 3
    assert all(isinstance(node['widget'], Gtk.CheckButton) for node in editor.task_nodes)
    assert editor.get_markdown() == source
    assert all(node['widget'].get_cursor().get_name() == 'pointer' for node in editor.task_nodes)
    completed = editor.buffer.get_tag_table().lookup('task-completed')
    assert completed and completed.get_property('strikethrough')
    for node in editor.task_nodes:
        text = editor.buffer.get_iter_at_child_anchor(node['anchor']);text.forward_chars(2)
        assert text.has_tag(completed) == node['checked']
    editor.task_nodes[-1]['widget'].set_active(True)
    result = editor.get_markdown()
    assert '- [x] **Preparar**' in result and '  - [ ] Revisar' in result, result
    editor.undo();assert editor.get_markdown() == source
    editor.redo();assert '- [x] **Preparar**' in editor.get_markdown()
    editor = RichTextEditor(window, 'Primer\nSegon')
    editor.buffer.select_range(editor.buffer.get_start_iter(), editor.buffer.get_end_iter())
    editor.task_list()
    assert editor.get_markdown() == '- [ ] Primer\n- [ ] Segon', editor.get_markdown()
    editor.buffer.place_cursor(editor.buffer.get_end_iter())
    assert editor.key_pressed(None, Gdk.KEY_Return, 0, Gdk.ModifierType(0))
    assert editor.get_markdown().endswith('\n- [ ] '), repr(editor.get_markdown())
    assert editor.key_pressed(None, Gdk.KEY_Return, 0, Gdk.ModifierType(0))
    assert editor.get_markdown().endswith('Segon\n'), repr(editor.get_markdown())
    editor.undo();assert editor.get_markdown().endswith('\n- [ ] ')
    editor.redo();assert editor.get_markdown().endswith('Segon\n')
    editor = RichTextEditor(window, '1. [ ] Primer\n2. [x] Segon')
    editor.task_nodes[0]['widget'].set_active(False)
    assert '2. [ ] Segon' in editor.get_markdown()
    editor = RichTextEditor(window, '- [ ] Tasca')
    editor.buffer.select_range(editor.buffer.get_start_iter(), editor.buffer.get_end_iter())
    editor.list_format(False)
    assert editor.get_markdown() == '- Tasca', repr(editor.get_markdown())
    editor.undo();assert editor.get_markdown() == '- [ ] Tasca'
    editor = RichTextEditor(window, '- [x] **Fet**\n- [ ] Pendent')
    node = editor.task_nodes[-1]
    node['widget'].set_active(False)
    assert editor.get_markdown() == '- [ ] **Fet**\n- [ ] Pendent'
    text = editor.buffer.get_iter_at_child_anchor(node['anchor']);text.forward_chars(2)
    assert not text.has_tag(editor.buffer.get_tag_table().lookup('task-completed'))
    assert text.has_tag(editor.buffer.get_tag_table().lookup('bold'))
    node['widget'].set_active(True)
    assert '~~' not in editor.get_markdown()

    editor.buffer.set_text('Text sense tasques')
    assert editor.get_markdown() == 'Text sense tasques'
    editor = RichTextEditor(window, '```\n- [ ] Literal\n```')
    assert not editor.task_nodes
    editor = RichTextEditor(window, '```\n• ☑ Literal\n```')
    assert not editor.task_nodes
    editor.buffer.insert(editor.buffer.get_end_iter(), '!')
    assert '• ☑ Literal' in editor.get_markdown()
    editor = RichTextEditor(window, '')
    editor.task_list()
    editor.buffer.insert_at_cursor('Tasca nova')
    assert editor.get_markdown() == '- [ ] Tasca nova'
    body = editor.buffer.get_iter_at_offset(2)
    assert all(tag.get_property('rise') == 0 for tag in body.get_tags())
    for width in (360, 680):
        editor = RichTextEditor(window, '- [ ] Tasca')
        surface = Gtk.Window(child=editor, default_width=width, default_height=400)
        surface.present()
        deadline = time.monotonic()+.3
        while time.monotonic()<deadline:
            while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
            time.sleep(.005)
        settings = Gtk.Settings.get_default()
        original_font = settings.get_property('gtk-font-name')
        settings.set_property('gtk-font-name', 'Sans 15')
        while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
        assert not editor.modified and editor.get_markdown() == '- [ ] Tasca'
        settings.set_property('gtk-font-name', original_font)
        toolbar = editor.get_first_child()
        child = toolbar.get_first_child()
        while child:
            ok, bounds = child.compute_bounds(toolbar)
            assert ok and bounds.origin.x >= 0 and bounds.origin.y >= 0
            assert bounds.origin.x+bounds.size.width <= toolbar.get_width()+1
            assert bounds.origin.y+bounds.size.height <= toolbar.get_height()+1
            child = child.get_next_sibling()
        surface.destroy()
    editor = RichTextEditor(window, '- [x] Tasca feta')
    surface = Gtk.Window(child=editor, default_width=400, default_height=400)
    surface.present()
    manager = Adw.StyleManager.get_default()
    original_scheme = manager.get_color_scheme()
    for scheme in (Adw.ColorScheme.FORCE_LIGHT, Adw.ColorScheme.FORCE_DARK):
        manager.set_color_scheme(scheme)
        deadline = time.monotonic()+.3
        while time.monotonic()<deadline:
            while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
            time.sleep(.005)
        tag = editor.buffer.get_tag_table().lookup('task-completed')
        actual = tag.get_property('foreground-rgba')
        expected = editor.view.get_style_context().get_color()
        assert abs(actual.red-expected.red)<.01 and abs(actual.green-expected.green)<.01 and abs(actual.blue-expected.blue)<.01
        assert 0<actual.alpha<expected.alpha
        assert not editor.modified and editor.get_markdown() == '- [x] Tasca feta'
    surface.destroy()
    manager.set_color_scheme(original_scheme)
print('PASS native task toggles, nested Markdown, formatting, conversion, Enter continuation and undo/redo')
