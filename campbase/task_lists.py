# SPDX-License-Identifier: GPL-3.0-or-later
"""Native task controls with Markdown state and editor history."""
import re
from gi.repository import Adw, Gdk, GLib, Gtk, Pango
from . import localization as ui
from .i18n import _


class TaskLists:
    def task_at(self, position):
        node = self.task_by_anchor.get(position.get_child_anchor())
        return node if node and not node['anchor'].get_deleted() else None

    def task_mapped(self, *_unused):
        self.task_unmapped()
        settings = self.view.get_settings()
        self.task_font_handlers = [(settings, settings.connect('notify::'+name, self.align_tasks))
                                   for name in ('gtk-font-name', 'gtk-xft-dpi')]
        manager = Adw.StyleManager.get_default()
        self.task_font_handlers.extend((manager, manager.connect('notify::'+name, self.queue_task_completion))
                                       for name in ('dark', 'high-contrast'))
        self.align_tasks()
        self.refresh_task_completion()

    def task_unmapped(self, *_unused):
        for settings, handler in self.task_font_handlers:
            settings.disconnect(handler)
        self.task_font_handlers.clear()
        if self.task_style_idle:
            GLib.source_remove(self.task_style_idle)
            self.task_style_idle = 0

    def align_tasks(self, *_unused):
        control = next((node['widget'] for node in self.task_nodes if not node['anchor'].get_deleted()), None)
        if control is None:
            return
        context = self.view.get_pango_context()
        metrics = context.get_metrics(context.get_font_description(), context.get_language())
        height = control.measure(Gtk.Orientation.VERTICAL, -1)[0]
        offset = (height-(metrics.get_ascent()-metrics.get_descent())/Pango.SCALE)/2
        tag = self.buffer.get_tag_table().lookup('task-anchor')
        if tag is None:
            tag = self.buffer.create_tag('task-anchor')
        tag.set_property('rise', round(-offset*Pango.SCALE))

    def queue_task_completion(self, *_unused):
        if not self.task_style_idle:
            def refresh():
                self.task_style_idle = 0
                self.refresh_task_completion()
                return GLib.SOURCE_REMOVE
            self.task_style_idle = GLib.idle_add(refresh)

    def refresh_task_completion(self, *_unused):
        tag = self.buffer.get_tag_table().lookup('task-completed')
        if tag is None:
            if not any(node['checked'] and not node['anchor'].get_deleted() for node in self.task_nodes):
                return
            tag = self.buffer.create_tag('task-completed', strikethrough=True)
        color = self.view.get_style_context().get_color()
        dimmed = Gdk.RGBA()
        dimmed.red, dimmed.green, dimmed.blue = color.red, color.green, color.blue
        dimmed.alpha = color.alpha * (.8 if Adw.StyleManager.get_default().get_high_contrast() else .65)
        tag.set_property('foreground-rgba', dimmed)
        self.buffer.remove_tag(tag, self.buffer.get_start_iter(), self.buffer.get_end_iter())
        for node in self.task_nodes:
            if node['checked'] and not node['anchor'].get_deleted():
                start = self.buffer.get_iter_at_child_anchor(node['anchor'])
                start.forward_char()
                end = start.copy();end.forward_to_line_end()
                self.buffer.apply_tag(tag, start, end)

    def insert_task(self, position, checked=False, marker='- '):
        anchor = self.buffer.create_child_anchor(position)
        button = ui.create(Gtk.CheckButton, tooltip_text=_("Marca o desmarca la tasca"), active=checked)
        button.add_css_class('task-checkbox')
        button.set_cursor_from_name('pointer')
        node = {'anchor': anchor, 'widget': button, 'checked': checked, 'marker': marker}
        self.task_nodes.append(node)
        self.task_by_anchor[anchor] = node
        self.view.add_child_at_anchor(button, anchor)
        self.align_tasks()
        start = self.buffer.get_iter_at_child_anchor(anchor)
        end = start.copy();end.forward_char()
        self.buffer.apply_tag_by_name('task-anchor', start, end)
        def toggled(control):
            if self.loading:
                return
            self._capture()
            node['checked'] = control.get_active()
            self._changed()
            self._capture()
        button.connect('toggled', toggled)
        return self.buffer.get_iter_at_child_anchor(anchor)

    def realize_tasks(self):
        for line in range(self.buffer.get_line_count()-1, -1, -1):
            start = self.buffer.get_iter_at_line(line).iter
            if any(tag.get_property('name') == 'literal' or tag.get_property('name') in self.code_blocks for tag in start.get_tags()):
                continue
            end = start.copy();end.forward_to_line_end()
            text = self.buffer.get_slice(start, end, True)
            match = re.match(r'^(\s*)(• |\d+\. )([☐☑]) ', text)
            if not match:
                continue
            start.forward_chars(len(match[1]))
            end = start.copy();end.forward_chars(len(match[2])+2)
            self.buffer.delete(start, end)
            anchor = self.insert_task(start, match[3] == '☑', '- ' if match[2] == '• ' else match[2])
            anchor.forward_char()
            self.buffer.insert(anchor, ' ')

    def task_markdown(self, node):
        return node['marker'] + ('[x]' if node['checked'] else '[ ]')

    def task_list(self):
        self._capture()
        start, end = self.selection(True)
        first, last = start.get_line(), end.get_line()
        self.buffer.begin_user_action()
        for line in range(last, first-1, -1):
            start = self.buffer.get_iter_at_line(line).iter
            end = start.copy();end.forward_to_line_end()
            text = self.buffer.get_slice(start, end, True)
            match = re.match(r'^(\s*)(?:• |\d+\. |[-*] |❯ )?', text)
            position = start.copy();position.forward_chars(len(match[1]))
            if self.task_at(position):
                continue
            cut = start.copy();cut.forward_chars(len(match[0]))
            self.buffer.delete(start, cut)
            self.buffer.insert(start, match[1])
            anchor = self.insert_task(start)
            anchor.forward_char()
            self.buffer.insert(anchor, ' ')
        self.buffer.end_user_action()
        self._capture()
        self.view.grab_focus()

    def continue_task(self, cursor):
        if self.buffer.get_has_selection():
            return False
        start = cursor.copy();start.set_line_offset(0)
        text = self.buffer.get_slice(start, cursor, True)
        match = re.match(r'^(\s*)\ufffc ', text)
        if not match:
            return False
        position = start.copy();position.forward_chars(len(match[1]))
        node = self.task_at(position)
        if not node:
            return False
        self._capture()
        self.buffer.begin_user_action()
        if text == match[0]:
            self.buffer.delete(start, cursor)
        else:
            marker = node['marker']
            number = re.fullmatch(r'(\d+)\. ', marker)
            if number:
                marker = str(int(number[1])+1)+'. '
            self.buffer.insert(cursor, '\n'+match[1])
            anchor = self.insert_task(cursor, marker=marker)
            anchor.forward_char()
            self.buffer.insert(anchor, ' ')
            self.buffer.place_cursor(anchor)
        self.buffer.end_user_action()
        self._capture()
        return True
