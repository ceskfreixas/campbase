# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Compact card counters aligned by visible text and icon centers."""
from gi.repository import Graphene, Gsk, Gtk, Pango
from . import localization as ui
from .i18n import _, ngettext


class BadgeLayout(Gtk.BoxLayout):
    def do_allocate(self, box, width, height, baseline):
        Gtk.BoxLayout.do_allocate(self, box, width, height, baseline)
        icon, number = box.get_first_child(), box.get_last_child()
        _, image = icon.compute_bounds(box)
        _, text = number.compute_bounds(box)
        _, offset = number.get_layout_offsets()
        ink, _ = number.get_layout().get_extents()
        center = image.origin.y + image.size.height*7/16
        top = center - offset - (ink.y+ink.height/2)/Pango.SCALE
        position = Graphene.Point().init(text.origin.x, top)
        number.allocate(number.get_width(), number.get_height(), -1,
                        Gsk.Transform.new().translate(position))
        if box.has_css_class('card-comment-count'):
            position = Graphene.Point().init(image.origin.x, image.origin.y-.5)
            icon.allocate(icon.get_width(), icon.get_height(), -1,
                          Gsk.Transform.new().translate(position))


def comment_badge(count):
    text = ngettext("{count} comentari", "{count} comentaris", count).format(count=count)
    return counter_badge(str(count) if count < 100 else '99+', text,
                         'cat.ceskfreixas.Campbase-comments-symbolic', 'card-comment-count')


def task_badge(description):
    from .task_progress import task_progress
    completed, total = task_progress(description)
    if not total:
        return None
    text = _("Tasques completades: {completed}/{total}").format(completed=completed, total=total)
    return counter_badge(f'{completed}/{total}', text,
                         'cat.ceskfreixas.Campbase-task-progress-symbolic', 'card-task-count')


def counter_badge(value, text, icon_name, css_class):
    box = ui.create(Gtk.Box, spacing=3, valign=Gtk.Align.CENTER, margin_top=4, tooltip_text=text)
    box.set_layout_manager(BadgeLayout(spacing=3))
    box.add_css_class(css_class)
    box.add_css_class('dim-label')
    ui.accessible(box, [Gtk.AccessibleProperty.LABEL], [text])
    box.append(Gtk.Image(icon_name=icon_name, pixel_size=13,
                         valign=Gtk.Align.CENTER))
    number = Gtk.Label(label=value, valign=Gtk.Align.CENTER)
    number.add_css_class('caption')
    attributes = Pango.AttrList()
    attributes.insert(Pango.attr_scale_new(.9))
    number.set_attributes(attributes)
    box.append(number)
    return box
