# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Comments with explicit loading, empty and error states."""
from . import localization as ui
from .i18n import _, ngettext
from gi.repository import Adw, Gtk
from .people import timestamp, avatar, current_person
from .collaboration import members, mention_token, display_comment, comment_tokens
from .mention_style import MentionStyle, board_tokens
from .update_targets import matches_comment
from .updates import record_own_comment
from .mentions import MentionCompletion, mention_fragment

from .alerts import message
from .widgets import clear, icon_button, label


class CommentsPanel(Gtk.Box):
    def __init__(self, window, card, inline=False, target=None):
        margin = 0 if inline else 24
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_start=margin,
                         margin_end=margin, margin_top=margin, margin_bottom=margin)
        self.window, self.card = window, card
        self.target = target or {}
        self.target_widget = None
        self.on_loaded = lambda: None
        self.board_id = card.get('boardId', window.board_id)
        self.loaded = False
        self.deleting = False
        self.reacting = False
        self.target_status = label('', 'dim-label', xalign=0, wrap=True, visible=False)
        self.append(self.target_status)
        self.state = Gtk.Stack(vexpand=not inline, vhomogeneous=False)
        self.comments = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, valign=Gtk.Align.START)
        content = self.comments if inline else Gtk.ScrolledWindow(child=self.comments, vexpand=True,
                                                                 hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.state.add_named(content, "comments")
        self.loading = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                               halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self.spinner = Gtk.Spinner(spinning=True, width_request=24, height_request=24)
        self.loading.append(self.spinner)
        self.loading.append(label(_("S'estan carregant els comentaris…"), "dim-label", wrap=True))
        self.state.add_named(self.loading, "loading")
        empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                        halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        image = Gtk.Image(icon_name="user-status-pending-symbolic", pixel_size=32)
        image.add_css_class("dim-label")
        empty.append(image)
        empty.append(label(_("Encara no hi ha comentaris."), "dim-label", wrap=True))
        self.state.add_named(empty, "empty")
        error = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                        halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self.error_label = label("", "dim-label", wrap=True)
        error.append(self.error_label)
        retry = ui.create(Gtk.Button, label=_("Torna-ho a provar"), halign=Gtk.Align.CENTER)
        retry.connect("clicked", lambda *_unused: self.refresh())
        error.append(retry)
        self.state.add_named(error, "error")
        self.state.set_visible_child_name("loading")
        self.append(self.state)
        line = Gtk.Box(spacing=8)
        self.entry = ui.create(Gtk.Entry, placeholder_text=_("Escriu un comentari…"), max_length=1000, hexpand=True)
        self.entry_mentions = MentionStyle(self.entry, board_tokens(window, self.board_id))
        line.append(self.entry)
        self.mention = ui.create(Gtk.MenuButton, label='@', tooltip_text=_("Cita un membre del tauler"))
        self.mention.add_css_class('flat')
        self.mention_popover = Gtk.Popover()
        self.mention.set_popover(self.mention_popover)
        chooser = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                          margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        self.mention_search = ui.create(Gtk.SearchEntry, placeholder_text=_("Cerca un membre…"))
        self.mention_search.connect('search-changed', lambda *_: self.show_members())
        chooser.append(self.mention_search)
        self.mention_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        chooser.append(Gtk.ScrolledWindow(child=self.mention_list, min_content_height=80, max_content_height=260,
                                          propagate_natural_height=True, hscrollbar_policy=Gtk.PolicyType.NEVER))
        self.mention_popover.set_child(chooser)
        self.mention_popover.connect('map', lambda *_: self.show_members())
        line.append(self.mention)
        self.send = icon_button("document-send-symbolic", _("Envia el comentari"), self.submit)
        line.append(self.send)
        self.entry.connect("activate", self.submit)
        self.append(line)
        self.completion = MentionCompletion(self.entry, window, self.board_id, self.insert_mention)

    def show(self):
        if not self.loaded:
            self.loaded = True
            self.refresh()

    def refresh(self):
        self.spinner.set_spinning(True)
        self.state.set_visible_child_name("loading")
        self.window.engine.run(lambda api: api.comments_for_update(self.card['id'], self.target)
                               if self.target else api.comments(self.card['id']), self.display)

    def display(self, result, error):
        self.spinner.set_spinning(False)
        clear(self.comments)
        self.target_widget = None
        # A short first page is the complete count. A notification may load a
        # later page, and must never overwrite the server's total with its size.
        if not self.window.demo and not error and not self.target and len(result or []) < 50:
            self.window.store.comment_count(self.board_id, self.card['id'], count=len(result or []))
        if not error:
            self.window.sync_changed()
        if error:
            ui.text(self.error_label, 'text', error)
            self.state.set_visible_child_name("error")
        elif not result:
            self.state.set_visible_child_name("empty")
        else:
            from .comment_reactions import group_comments
            from .reaction_widgets import selector, chips
            items, reactions = group_comments(result)
            for item in items:
                replies = reactions.get(str(item.get('id')), [])
                box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
                box.add_css_class("comment")
                author = item.get('actorDisplayName') or item.get('actorId') or _("Usuari de Deck")
                actor_id = item.get('actorId') or ''
                heading = Gtk.Box(spacing=10)
                heading.append(avatar(self.window, {'uid': actor_id, 'displayname': author}, 32))
                names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True)
                names.append(label(author, 'heading', xalign=0))
                details = ('@'+actor_id+' · ' if actor_id else '') + timestamp(item.get('creationDateTime'))
                names.append(label(details, 'dim-label', xalign=0, wrap=True))
                heading.append(names)
                controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, valign=Gtk.Align.START)
                if self.owns_comment(item):
                    remove = icon_button('user-trash-symbolic', _("Esborra el comentari"),
                                         lambda *_unused, item=item: self.confirm_delete(item))
                    remove.add_css_class('flat')
                    remove.set_valign(Gtk.Align.CENTER)
                    controls.append(remove)
                controls.append(selector(self, item, replies))
                heading.append(controls)
                box.append(heading)
                body = label(display_comment(item), xalign=0, wrap=True, selectable=True)
                MentionStyle(body, board_tokens(self.window, self.board_id)+comment_tokens(item))
                box.append(body)
                if replies:
                    box.append(chips(self, item, replies))
                if matches_comment(item, self.target) or any(matches_comment(reply, self.target) for reply in replies):
                    self.target_widget = box
                    box.set_focusable(True)
                    box.add_css_class('notification-target')
                self.comments.append(box)
            self.state.set_visible_child_name("comments")
        missing = not error and bool(self.target.get('comment_id')) and self.target_widget is None
        ui.text(self.target_status, 'text', _("No s'ha pogut trobar el comentari indicat.") if missing else '')
        self.target_status.set_visible(missing)
        self.on_loaded()

    def owns_comment(self, item):
        uid = current_person(self.window)['uid']
        return bool(uid and item.get('id') and item.get('actorId') == uid and item.get('actorType', 'users') == 'users')

    def confirm_delete(self, item):
        if self.deleting or not self.owns_comment(item):
            return None
        prompt = ui.create(Adw.AlertDialog, heading=_("Vols esborrar aquest comentari?"),
                           body=_("El comentari s'esborrarà de Nextcloud Deck. Aquesta acció no es pot desfer."))
        ui.response(prompt, 'cancel', _("Cancel·la"))
        ui.response(prompt, 'delete', _("Esborra"))
        prompt.set_response_appearance('delete', Adw.ResponseAppearance.DESTRUCTIVE)
        prompt.set_default_response('cancel')
        prompt.connect('response', lambda _dialog, response: self.delete_comment(item) if response == 'delete' else None)
        prompt.present(self)
        return prompt

    def delete_comment(self, item):
        if self.deleting or not self.owns_comment(item):
            return
        self.deleting = True
        self.comments.set_sensitive(False)
        self.send.set_sensitive(False)
        def remove(api):
            api.delete_comment(self.card['id'], item['id'])
            self.window.store.comment_count(self.board_id, self.card['id'], delta=-1)
            self.window.store.dismiss_notice({'key': f'local:comment:{self.card["id"]}:{item["id"]}'})
        def done(_result, error):
            self.deleting = False
            self.comments.set_sensitive(True)
            self.send.set_sensitive(True)
            if error:
                if self.get_root() is not None:
                    message(self.get_root(), _("No s'ha pogut esborrar el comentari"), error)
                return
            if str(self.target.get('comment_id')) == str(item['id']):
                self.target = {}
            self.refresh()
            self.window.update_notification_badge()
        self.window.engine.run(remove, done)

    def show_members(self):
        clear(self.mention_list)
        board = next((b for b in self.window.snapshot.get('boards', []) if b['id'] == self.board_id), {})
        query = self.mention_search.get_text().casefold().strip()
        found = []
        for user in members(board):
            if query and query not in (user['displayname']+' '+user['uid']).casefold():
                continue
            try:
                mention_token(user['uid'])
            except ValueError:
                continue
            button = Gtk.Button()
            button.add_css_class('flat')
            line = Gtk.Box(spacing=8)
            line.append(avatar(self.window, user, 24))
            line.append(label(user['displayname']+' (@'+user['uid']+')', xalign=0))
            button.set_child(line)
            button.connect('clicked', lambda *_, uid=user['uid']: self.insert_mention(uid))
            self.mention_list.append(button)
            found.append(user)
        if not found:
            self.mention_list.append(label(_("No hi ha membres que coincideixin amb la cerca."), 'dim-label', wrap=True))

    def insert_mention(self, uid):
        text = self.entry.get_text()
        position = self.entry.get_position()
        if position < 0:
            position = len(text)
        fragment = mention_fragment(text, position)
        start = fragment.start() if fragment else position
        token = mention_token(uid)+' '
        result = text[:start]+token+text[position:]
        if len(result) > 1000:
            return
        self.entry.set_text(result)
        self.entry.set_position(start+len(token))
        self.mention_popover.popdown()
        self.completion.hide()
        self.entry.grab_focus_without_selecting()

    def submit(self, *_unused):
        text = self.entry.get_text().strip()
        if not text or not self.send.get_sensitive():
            return
        self.send.set_sensitive(False)
        def done(result, error):
            self.send.set_sensitive(True)
            if error:
                message(self.get_root(), _("No s'ha pogut confirmar el comentari"),
                        error+_(" Revisa Deck abans de tornar-lo a enviar."))
            else:
                if self.entry.get_text().strip() == text:
                    ui.text(self.entry, 'text', "")
                self.refresh()
                self.window.update_notification_badge()
        board_id = self.card.get('boardId', self.window.board_id)
        def post(api):
            result = api.add_comment(self.card['id'], text)
            self.window.store.comment_count(board_id, self.card['id'], delta=1)
            record_own_comment(self.window.store, board_id, self.card, result)
            return result
        self.window.engine.run(post, done)
