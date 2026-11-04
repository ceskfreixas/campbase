# SPDX-License-Identifier: GPL-3.0-or-later
"""Optional board roles backed by ordinary shared Deck columns and labels."""
from gi.repository import Adw, Gtk
from . import localization as ui
from .i18n import _
from .dialog_widgets import dialog_form
from .widgets import label
from .workflow_state import options, save_options, hold_label, resource_choices, suggested_choice, NOT_NOW_TITLES, HOLD_TITLES


class WorkflowDialog(Adw.Dialog):
    def __init__(self, window, board, hold_column=None):
        super().__init__(content_width=520, follows_content_size=True)
        ui.widget(self, title=_("Flux de treball"))
        self.window, self.board, self.hold_column = window, board, hold_column
        self.api, self.busy, self.closed = window.engine.api, False, False
        self.connect('closed', lambda *_: setattr(self, 'closed', True))
        cfg = options(window.store, board['id'])
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        self.save = ui.create(Gtk.Button, label=_("Desa"))
        self.save.add_css_class('suggested-action');self.save.connect('clicked', self.apply)
        header.pack_end(self.save);outer.append(header)
        form = dialog_form(spacing=20)
        form.append(label(board['title'], 'title-2', xalign=0, wrap=True))
        group = ui.create(Adw.PreferencesGroup, title=_("Ara no"),
                          description=_("Aparta la feina que ara no vols prioritzar."))
        self.enabled = ui.create(Adw.SwitchRow, title=_("Mostra l'espai «Ara no»"))
        self.enabled.set_active(bool(cfg.get('not_now_enabled')))
        group.add(self.enabled)
        self.stacks = resource_choices(window.snapshot.get('stacks', {}).get(str(board['id']), []),cfg.get('not_now_stack'),NOT_NOW_TITLES)
        self.stack_choice = ui.create(Adw.ComboRow, title=_("Columna"),
            model=ui.strings([item['title'] if item else _("Crea una columna «Ara no»") for item in self.stacks]))
        self.stack_choice.set_selected(suggested_choice(self.stacks,cfg.get('not_now_stack'),NOT_NOW_TITLES))
        group.add(self.stack_choice);form.append(group)
        self.labels = resource_choices(sorted(board.get('labels') or [],key=lambda item:item['title'].casefold()),cfg.get('hold_label'),HOLD_TITLES)
        group = ui.create(Adw.PreferencesGroup, title=_("En espera"),
                          description=_("Separa les targetes pausades sense canviar-les de columna. Activa la secció des del menú de cada columna."))
        self.label_choice = ui.create(Adw.ComboRow, title=_("Etiqueta compartida"),
            model=ui.strings([item['title'] if item else _("Crea l'etiqueta «En espera»") for item in self.labels]))
        self.label_choice.set_selected(suggested_choice(self.labels,cfg.get('hold_label'),HOLD_TITLES))
        group.add(self.label_choice)
        self.configure_hold = ui.create(Adw.SwitchRow, title=_("Activa «En espera» en aquesta columna") if hold_column else _("Activa «En espera»"))
        self.configure_hold.set_active(bool(hold_column or hold_label(window,board['id'])))
        group.add(self.configure_hold);form.append(group)
        self.status = label('', 'dim-label', xalign=0, wrap=True, visible=False)
        form.append(self.status)
        outer.append(Gtk.ScrolledWindow(child=form, vexpand=True, propagate_natural_height=True,
                     max_content_height=620, propagate_natural_width=True, min_content_width=480, max_content_width=520, hscrollbar_policy=Gtk.PolicyType.NEVER))
        self.set_child(outer)
        self.enabled.connect('notify::active', self.controls)
        self.configure_hold.connect('notify::active', self.controls)
        ui.selection(self.stack_choice, self.controls);ui.selection(self.label_choice, self.controls)
        self.controls()

    def controls(self, *_unused):
        enabled, held = self.enabled.get_active(), self.configure_hold.get_active()
        permissions = self.board.get('permissions', {})
        can_create_stack = self.window.demo or permissions.get('PERMISSION_MANAGE', False)
        can_create_label = self.window.demo or permissions.get('PERMISSION_EDIT', False)
        allowed = (not enabled or self.stacks[self.stack_choice.get_selected()] is not None or can_create_stack)
        allowed &= not held or self.labels[self.label_choice.get_selected()] is not None or can_create_label
        self.save.set_sensitive(not self.busy and allowed)
        self.stack_choice.set_sensitive(not self.busy and enabled)
        self.label_choice.set_sensitive(not self.busy and held)
        self.enabled.set_sensitive(not self.busy);self.configure_hold.set_sensitive(not self.busy)

    def apply(self, *_unused):
        if (self.busy or self.window.engine.closed or self.window.engine.account_changing
                or self.api is not self.window.engine.api or not self.save.get_sensitive()):
            return
        enabled, held = self.enabled.get_active(), self.configure_hold.get_active()
        stack = self.stacks[self.stack_choice.get_selected()]
        label_item = self.labels[self.label_choice.get_selected()]
        if self.window.demo:
            if enabled and stack is None:
                stack={'id':max((item['id'] for stacks in self.window.snapshot.get('stacks',{}).values() for item in stacks),default=0)+1,
                       'title':ui.render(_("Ara no")),'order':max((item.get('order',0) for item in self.stacks if item),default=-1)+1,'cards':[]}
            if held and label_item is None:
                label_item={'id':max((item['id'] for board in self.window.snapshot.get('boards',[]) for item in board.get('labels') or []),default=0)+1,
                            'title':ui.render(_("En espera")),'color':'E9AD0C'}
            self.finish(stack,label_item,enabled,held)
            return
        if (not enabled or stack) and (not held or label_item):
            self.finish(stack,label_item,enabled,held)
            return
        self.busy=True;self.set_can_close(False);self.controls()
        self.status.set_visible(True);ui.text(self.status,'text',_("S'està preparant el flux de treball…"))
        def action(api):
            board = api.check_board(self.board['id'])
            if board.get('archived') or board.get('deletedAt'):
                from .deck import ConflictError
                raise ConflictError(_("Aquest tauler ja no es pot modificar."))
            selected_stack = stack or (api.ensure_not_now_stack(self.board['id'],ui.render(_("Ara no"))) if enabled else None)
            selected_label = label_item
            if held and selected_label is None:
                selected_label = api.ensure_hold_label(self.board['id'],ui.render(_("En espera")),board=board)
            return selected_stack,selected_label
        def done(result,error):
            if self.closed or self.api is not self.window.engine.api or self.window.engine.account_changing:
                return
            self.busy=False;self.set_can_close(True);self.controls()
            if error:
                ui.text(self.status,'text',error);return
            self.finish(*result,enabled,held)
        self.window.engine.run(action,done)

    def finish(self, stack, label_item, enabled, held):
        board_id=self.board['id']
        cfg=options(self.window.store,board_id)
        known = self.window.store.get('snapshot', {}).get('stacks', {}).get(str(board_id), [])
        if enabled and stack and not any(item['id']==stack['id'] for item in known):
            self.window.store.cache_restored_stack(board_id,stack)
        if held and label_item:
            self.window.store.cache_label(board_id,label_item)
        columns=set(cfg.get('hold_columns',[]))
        if self.hold_column and held:columns.add(self.hold_column)
        if self.hold_column and not held:columns.discard(self.hold_column)
        save_options(self.window.store,board_id,not_now_enabled=enabled,
                     not_now_stack=stack['id'] if stack else cfg.get('not_now_stack'),
                     hold_label=label_item['id'] if held and label_item else cfg.get('hold_label'),
                     hold_columns=sorted(columns),
                     hold_enabled=(held if self.hold_column is None else held or cfg.get('hold_enabled',True)))
        self.window.render();self.force_close()


def configure_workflow(window, board, hold_column=None):
    dialog=WorkflowDialog(window,board,hold_column)
    dialog.present(window)
    return dialog


def toggle_hold_column(window, stack):
    cfg=options(window.store,window.board_id)
    columns=set(cfg.get('hold_columns',[]))
    if stack['id'] in columns:
        columns.remove(stack['id'])
    elif hold_label(window):
        columns.add(stack['id'])
    else:
        board=next(item for item in window.snapshot['boards'] if item['id']==window.board_id)
        return configure_workflow(window,board,stack['id'])
    save_options(window.store,window.board_id,hold_columns=sorted(columns))
    window.workflow=options(window.store,window.board_id)
    if window.dragged_card:
        window.render()
        return
    from .widgets import Column
    from .column_sections import refresh_hold
    def refresh(widget):
        if isinstance(widget,Column) and widget.stack['id']==stack['id']:
            refresh_hold(widget)
            return True
        child=widget.get_first_child()
        while child:
            if refresh(child):return True
            child=child.get_next_sibling()
        return False
    if not refresh(window.board_body):window.render()
