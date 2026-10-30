# SPDX-License-Identifier: GPL-3.0-or-later
"""Own-message actions with explicit confirmation and preserved editing drafts."""
import time
from gi.repository import Adw, Gtk
from . import localization as ui
from .i18n import _
from .widgets import icon_button, label
from .dialog_widgets import dialog_form


def message_actions(chat, item):
    if item.get('actorType') != 'users' or item.get('actorId') != chat.uid or item.get('systemMessage'):
        return None
    if item.get('messageType', 'comment') != 'comment' or 'chat-get-context' not in chat.features:
        return None
    age = time.time()-item.get('timestamp', 0)
    actions = Gtk.Box(spacing=4, valign=Gtk.Align.START)
    if 'edit-messages' in chat.features and age <= 24*3600 and not item.get('messageParameters'):
        edit = icon_button('document-edit-symbolic', _("Edita el missatge"),
            lambda *_: MessageEditDialog(chat, item).present(chat))
        edit.add_css_class('flat')
        actions.append(edit)
    if 'delete-messages' in chat.features and age <= 6*3600:
        remove = icon_button('user-trash-symbolic', _("Esborra el missatge"), lambda *_: confirm_delete(chat, item))
        remove.add_css_class('flat')
        remove.add_css_class('destructive-action')
        actions.append(remove)
    return actions if actions.get_first_child() else None


def perform(chat, item, done, *, text=None, delete=False):
    if not chat.writer.active():
        return
    chat.set_can_close(False)
    def changed(result, error):
        chat.set_can_close(True)
        if error:
            chat.set_status(error)
        else:
            chat.add_messages([result])
            chat.set_status('')
        done(error)
    chat.writer.run(lambda: chat.talk.change_message(chat.room_token, item, chat.uid, chat.features,
                                                    text=text, delete=delete), changed, queue=True)


def confirm_delete(chat, item):
    prompt = ui.create(Adw.AlertDialog, heading=_("Esborra el missatge"),
        body=_("El missatge s'esborrarà de la conversa per a tots els participants."))
    ui.response(prompt, 'cancel', _("Cancel·la"))
    ui.response(prompt, 'delete', _("Esborra"))
    prompt.set_default_response('cancel')
    prompt.set_close_response('cancel')
    prompt.set_response_appearance('delete', Adw.ResponseAppearance.DESTRUCTIVE)
    prompt.connect('response', lambda _, choice: perform(chat, item, lambda error: None, delete=True) if choice == 'delete' else None)
    prompt.present(chat)


class MessageEditDialog(Adw.Dialog):
    def __init__(self, chat, item):
        super().__init__(content_width=520, follows_content_size=True)
        ui.widget(self, title=_("Edita el missatge"))
        self.chat, self.item, self.busy = chat, dict(item), False
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        self.save = ui.create(Gtk.Button, label=_("Desa"))
        self.save.add_css_class('suggested-action')
        self.save.connect('clicked', self.submit)
        header.pack_end(self.save)
        outer.append(header)
        form = dialog_form()
        self.text = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, height_request=120)
        ui.accessible(self.text, [Gtk.AccessibleProperty.LABEL], [_("Edita el missatge")])
        self.text.get_buffer().set_text(item.get('message') or '')
        form.append(Gtk.ScrolledWindow(child=self.text, min_content_height=120, max_content_height=320,
            propagate_natural_height=True, hscrollbar_policy=Gtk.PolicyType.NEVER))
        self.status = label('', 'dim-label', xalign=0, wrap=True, visible=False)
        form.append(self.status)
        outer.append(form)
        self.set_child(outer)

    def submit(self, *_unused):
        if self.busy:
            return
        buffer = self.text.get_buffer()
        text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)
        if not text.strip():
            return
        self.busy = True
        self.save.set_sensitive(False)
        self.text.set_editable(False)
        self.set_can_close(False)
        def done(error):
            self.busy = False
            self.set_can_close(True)
            self.save.set_sensitive(True)
            self.text.set_editable(True)
            if error:
                ui.text(self.status, 'text', error)
                self.status.set_visible(True)
            else:
                self.force_close()
        perform(self.chat, self.item, done, text=text)
