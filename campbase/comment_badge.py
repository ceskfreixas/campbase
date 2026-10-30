# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Align comment digits by their visible ink rather than font line height."""
from gi.repository import Graphene, Gsk, Gtk
from . import localization as ui
from .i18n import ngettext


class CommentBadgeLayout(Gtk.BoxLayout):
    def do_allocate(self, box, width, height, baseline):
        Gtk.BoxLayout.do_allocate(self, box, width, height, baseline)
        icon, number = box.get_first_child(), box.get_last_child()
        _, image = icon.compute_bounds(box)
        _, text = number.compute_bounds(box)
        _, offset = number.get_layout_offsets()
        ink, _ = number.get_layout().get_pixel_extents()
        # The bubble's rectangular body is centred at y=7 in its 16px SVG;
        # its tail extends lower and must not pull the digits down with it.
        center = image.origin.y + image.size.height*7/16
        top = center - offset - ink.y - ink.height/2
        position = Graphene.Point().init(text.origin.x, top)
        number.allocate(number.get_width(), number.get_height(), -1,
                        Gsk.Transform.new().translate(position))


def comment_badge(count):
    text = ngettext("{count} comentari", "{count} comentaris", count).format(count=count)
    box = ui.create(Gtk.Box, spacing=3, valign=Gtk.Align.CENTER, margin_top=4, tooltip_text=text)
    box.set_layout_manager(CommentBadgeLayout(spacing=3))
    box.add_css_class('card-comment-count')
    box.add_css_class('dim-label')
    ui.accessible(box, [Gtk.AccessibleProperty.LABEL], [text])
    box.append(Gtk.Image(icon_name='cat.ceskfreixas.Campbase-comments-symbolic', pixel_size=13,
                         valign=Gtk.Align.CENTER))
    number = Gtk.Label(label=str(count) if count < 100 else '99+', valign=Gtk.Align.CENTER)
    number.add_css_class('caption')
    box.append(number)
    return box
