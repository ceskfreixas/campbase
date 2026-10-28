# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""The board workspace: triage above, ordinary workflow columns below."""
from . import localization as ui
from .i18n import _, ngettext
import time
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

from .about import about_dialog
from .account import Account
from .assets import Assets
from .avatars import AvatarLoader
from .comment_count_loader import CommentCountLoader
from .dragging import DragSession
from .project import board_header
from .deck import Deck
from .dialogs import AccountDialog, CardDialog, PendingDialog, Preferences, TextDialog, ColumnColorDialog, message
from .sync import SyncEngine
from .settings import sync_interval
from .settings import archive_overrides, archives_visible
from .people import current_person, remember_creator
from .notifications import NotificationsDialog
from .updates import entries
from .update_targets import destination
from .dialog_widgets import scroll_to_widget
from urllib.parse import urlsplit
from .widgets import Column, clear, icon_button, label


class Window(Adw.ApplicationWindow):
    def __init__(self, application, store, demo=False):
        super().__init__(application=application, title="Campbase")
        ui.widget(self, title="Campbase")
        self.store = store
        self.assets = Assets(store.directory, store.get("asset_account", ""))
        self.demo = demo
        self.query = ""
        self.only_mine = False
        settings = store.settings()
        self._last_board_id = settings.get("board_id")
        self.board_id = settings.get("startup_board_id") or self._last_board_id
        self._startup_board_pending = True
        self.timer = 0
        self.dragged_card = None
        self.drag_session = DragSession(self)
        self._render_after_drag = False
        self._manual_sync_until = 0
        self._sync_feedback_timer = 0
        self._rendering = False
        self._open_column_menu = None
        self._render_after_menu = False
        self.account = None
        self.account_loading = not demo
        self._manual_account_sync = False
        self.engine = SyncEngine(store, self.account, GLib.idle_add, self.sync_changed)
        self.avatar_loader = AvatarLoader(self)
        self.comment_counts = CommentCountLoader(self)
        if "startup_sidebar" not in settings:
            self.store.set_setting("startup_sidebar", settings.get("sidebar", False))
            settings = self.store.settings()
        self.set_default_size(settings.get("width", 1240), settings.get("height", 850))
        if settings.get("maximized"):
            self.maximize()
        self.set_theme(settings.get("theme", "system"), persist=False)
        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)
        self.split = Adw.OverlaySplitView(sidebar_width_fraction=.22, min_sidebar_width=240,
                                           max_sidebar_width=280, show_sidebar=settings.get("startup_sidebar", False))
        self.toast_overlay.set_child(self.split)
        self._sidebar()
        self._content()
        breakpoint = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 650sp"))
        breakpoint.add_setter(self.split, "collapsed", True)
        self.add_breakpoint(breakpoint)
        self.split.connect("notify::show-sidebar", self.sidebar_changed)
        self.sidebar_changed()
        self.connect("close-request", self.close_requested)
        self._actions()
        self.render()
        if not demo:
            self.start_account()
        self.configure_sync()
        ui.on_change(self.retranslate)

    def _sidebar(self):
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar(title_widget=label("Campbase", "heading"))
        header.set_show_end_title_buttons(False)
        toolbar.add_top_bar(header)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        group = Gtk.Box(spacing=6, margin_top=18, margin_start=18, margin_end=12)
        group.append(label(_("TAULERS"), "sidebar-title", xalign=0, hexpand=True))
        add = icon_button("list-add-symbolic", _("Crea un tauler"), lambda *_unused: self.new_board())
        add.add_css_class("flat")
        group.append(add)
        box.append(group)
        self.board_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.board_list.add_css_class("navigation-sidebar")
        self.board_list.add_css_class("board-list")
        self.board_list.connect("row-selected", self.selected_board)
        box.append(Gtk.ScrolledWindow(child=self.board_list, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER))
        box.append(Gtk.Separator(margin_start=16, margin_end=16))
        self.status_button = Gtk.Button(margin_start=8, margin_end=8, margin_bottom=8)
        self.status_button.add_css_class("flat")
        self.status_button.add_css_class("account-footer")
        self.status_button.connect("clicked", lambda *_unused: PendingDialog(self).present(self))
        footer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.account_label = label("", "account-name", xalign=0, ellipsize=3)
        footer.append(self.account_label)
        status = Gtk.Box(spacing=8)
        self.status_indicator = Gtk.Stack()
        self.sidebar_spinner = Gtk.Spinner(width_request=14, height_request=14)
        self.status_indicator.add_named(self.sidebar_spinner, "spinner")
        self.status_icon = Gtk.Image(icon_name="object-select-symbolic", pixel_size=14)
        self.status_indicator.add_named(self.status_icon, "icon")
        status.append(self.status_indicator)
        self.status_label = label("", "sync-status", xalign=0, wrap=True, hexpand=True)
        status.append(self.status_label)
        footer.append(status)
        self.status_button.set_child(footer)
        box.append(self.status_button)
        toolbar.set_content(box)
        self.split.set_sidebar(toolbar)

    def _content(self):
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self.toggle_sidebar = ui.create(Gtk.ToggleButton, icon_name="sidebar-show-symbolic", tooltip_text=_("Mostra els taulers"))
        self.toggle_sidebar.connect("toggled", lambda button: self.split.set_show_sidebar(button.get_active()))
        header.pack_start(self.toggle_sidebar)
        self.header_title = ui.create(Adw.WindowTitle, title="Campbase")
        header.set_title_widget(self.header_title)
        self.sync_button = ui.create(Gtk.Button, tooltip_text=_("Sincronitza amb Deck"))
        self.sync_button.add_css_class("flat")
        ui.accessible(self.sync_button, [Gtk.AccessibleProperty.LABEL], [_("Sincronitza amb Deck")])
        self.sync_indicator = Gtk.Stack()
        self.sync_indicator.add_named(Gtk.Image(icon_name="view-refresh-symbolic"), "icon")
        self.sync_spinner = Gtk.Spinner(width_request=16, height_request=16)
        self.sync_indicator.add_named(self.sync_spinner, "spinner")
        self.sync_button.set_child(self.sync_indicator)
        self.sync_button.connect("clicked", lambda *_unused: self.manual_sync())
        header.pack_end(self.sync_button)
        self.search_button = icon_button("system-search-symbolic", _("Cerca al tauler"), lambda *_unused: self.show_search())
        header.pack_end(self.search_button)
        self.notifications_button = ui.create(Gtk.Button, tooltip_text=_("Notificacions"))
        self.notifications_button.add_css_class("flat")
        bell = Gtk.Box(spacing=4)
        bell.append(Gtk.Image(icon_name='preferences-system-notifications-symbolic'))
        self.notification_count = label('', 'notification-badge', visible=False, valign=Gtk.Align.CENTER)
        bell.append(self.notification_count)
        self.notifications_button.set_child(bell)
        self.notifications_button.connect('clicked', lambda *_: NotificationsDialog(self).present(self))
        header.pack_end(self.notifications_button)
        menu, work, application = Gio.Menu(), Gio.Menu(), Gio.Menu()
        ui.menu_append(work, _("Canvis pendents"), "win.pending")
        ui.menu_append(application, _("Preferències"), "win.preferences", '<Control>comma')
        ui.menu_append(application, _("Dreceres de teclat"), "win.shortcuts", '<Control>question')
        ui.menu_append(application, _("Quant al Campbase"), "win.about")
        menu.append_section(None, work)
        menu.append_section(None, application)
        more = ui.create(Gtk.MenuButton, icon_name="open-menu-symbolic", menu_model=menu, tooltip_text=_("Menú del Campbase"))
        self.main_menu = more
        header.pack_end(more)
        toolbar.add_top_bar(header)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.search = ui.create(Gtk.SearchEntry, placeholder_text=_("Cerca títols, descripcions o etiquetes…"), margin_top=8,
                                      margin_bottom=8, margin_start=24, margin_end=24, visible=False)
        self.search.connect("search-changed", self.search_changed)
        self.search.connect("stop-search", lambda *_unused: self.show_search(False))
        body.append(self.search)
        self.banner = ui.create(Adw.Banner, title="", revealed=False, button_label=_("Revisa-ho"))
        self.banner.connect("button-clicked", lambda *_unused: PendingDialog(self).present(self) if self.account else AccountDialog(self).present(self))
        body.append(self.banner)
        self.pages = Gtk.Stack(vexpand=True)
        self.board_body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20, valign=Gtk.Align.START)
        self.board_body.add_css_class("board-body")
        self.scroll = Gtk.ScrolledWindow(child=self.board_body, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        from .scroll_position import ScrollPosition
        self.scroll_position = ScrollPosition(self.scroll, self.board_body)
        self.pages.add_named(self.scroll, "board")
        self.empty = ui.create(Adw.StatusPage, title=_("Els teus taulers"), icon_name="view-grid-symbolic",
                                    description=_("Connecta Nextcloud Deck per treballar amb els mateixos taulers que al mòbil."))
        connect = ui.create(Gtk.Button, label=_("Connecta Nextcloud"), halign=Gtk.Align.CENTER)
        connect.add_css_class("suggested-action")
        connect.connect("clicked", lambda *_unused: AccountDialog(self).present(self))
        self.empty.set_child(connect)
        self.pages.add_named(self.empty, "empty")
        body.append(self.pages)
        toolbar.set_content(body)
        self.split.set_content(toolbar)

    def _actions(self):
        callbacks = {"sidebar": lambda: self.split.set_show_sidebar(not self.split.get_show_sidebar()),
                     "search": lambda: self.show_search(True), "sync": self.manual_sync, "new-card": self.new_card,
                     "notifications": lambda: NotificationsDialog(self).present(self),
                     "pending": lambda: PendingDialog(self).present(self),
                     "account": lambda: AccountDialog(self).present(self),
                     "preferences": lambda: Preferences(self).present(self), "shortcuts": self.show_shortcuts, "about": self.about}
        for name, callback in callbacks.items():
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _unused, parameter, fn=callback: fn())
            self.add_action(action)
        for name, keys in {"sidebar": ["F9"], "search": ["<Control>f"], "sync": ["<Control>r", "F5"],
                           "new-card": ["<Control>n"], "preferences": ["<Control>p", "<Control>comma"], "shortcuts": ["<Control>question", "<Control><Shift>slash"]}.items():
            self.get_application().set_accels_for_action("win." + name, keys)

    def set_theme(self, theme, persist=True):
        values = {"system": Adw.ColorScheme.DEFAULT, "light": Adw.ColorScheme.FORCE_LIGHT, "dark": Adw.ColorScheme.FORCE_DARK}
        Adw.StyleManager.get_default().set_color_scheme(values.get(theme, Adw.ColorScheme.DEFAULT))
        if persist:
            self.store.set_setting("theme", theme)

    def stacks(self):
        return self.snapshot.get("stacks", {}).get(str(self.board_id), [])

    def cards_in_stack(self, stack_id):
        return next((s.get("cards", []) for s in self.stacks() if s["id"] == stack_id), [])

    def find_card(self, card_id):
        return next((c for s in self.stacks() for c in s.get("cards", []) if c["id"] == card_id), None)

    def filtered_cards(self, stack):
        cards = [c for c in stack.get('cards', []) if not c.get('archived') or self.shows_archived(stack['id'])]
        if self.only_mine:
            from .collaboration import assignment_ids
            uid = current_person(self)['uid']
            cards = [card for card in cards if uid and uid in assignment_ids(card.get('assignedUsers'))]
        if self.query:
            cards = [c for c in cards if self.query in (c.get("title", "") + " " + (c.get("description") or "") + " " + " ".join(t.get("title", "") for t in c.get("labels") or [])).casefold()]
        return sorted(cards, key=lambda c: (bool(c.get('archived')), c.get('order', 0), c['id']))

    def shows_archived(self, stack_id):
        return archives_visible(self.store.settings(), stack_id)

    def card_count_text(self):
        count = sum(len(self.filtered_cards(stack)) for stack in self.stacks())
        return ngettext('{count} targeta', '{count} targetes', count).format(count=count)

    def show_archived(self, stack_id, visible):
        selected = archive_overrides(self.store.settings())
        selected[str(stack_id)] = bool(visible)
        self.store.set_setting('archived_overrides', selected)
        self.refresh_archive_sections(stack_id)

    def set_archived_default(self, visible):
        self.store.set_archived_default(visible)
        self.refresh_archive_sections()

    def refresh_archive_sections(self, stack_id=None):
        self.comment_counts.last_refresh = None
        self.scroll_position.prepare((self.board_id, self.query, self.only_mine))
        def refresh(widget):
            if isinstance(widget, Column):
                if stack_id is None or widget.stack['id'] == stack_id:
                    widget.refresh_archives()
                    return True
                return False
            child = widget.get_first_child()
            found = False
            while child:
                found = refresh(child) or found
                child = child.get_next_sibling()
            return found
        if not refresh(self.board_body):
            self.render()
        else:
            ui.text(self.board_count_label, 'text', self.card_count_text())
            self.scroll_position.restore()
        self.comment_counts.refresh(self.snapshot, self.board_id)

    def filter_mine(self, button):
        self.only_mine = button.get_active()
        self.render()

    def delete_archived_cards(self, stack, cards=None, parent=None, after=None):
        from .card_deletion import CardDeletionDialog
        cards = cards if cards is not None else [card for card in self.cards_in_stack(stack['id']) if card.get('archived')]
        if not cards:
            return None
        dialog = CardDeletionDialog(self, stack, cards, after=after)
        dialog.present(parent or self)
        return dialog

    def column_color(self, stack):
        saved = self.store.settings().get("colors", {}).get(str(stack["id"]))
        if saved:
            return saved
        name = stack["title"].strip().casefold()
        if self.stacks() and stack["id"] == self.stacks()[0]["id"]:
            return "#2190a4"
        if name in {"fet", "fetes", "done", "hecho", "feito", "eginda", "hèt"}:
            return "#33a56c"
        if "prepar" in name or "presta" in name:
            return "#e98d26"
        return "#9141ac"

    def render(self, snapshot=None):
        if self.dragged_card:
            self._render_after_drag = True
            return
        if self._rendering:
            return
        self._rendering = True
        try:
            self.snapshot = snapshot if snapshot is not None else self.store.view()
            boards = self.snapshot.get("boards", [])
            if boards and self._startup_board_pending:
                preferred = self.store.settings().get("startup_board_id") or self._last_board_id
                self.board_id = preferred if any(b["id"] == preferred for b in boards) else self._last_board_id
                self._startup_board_pending = False
            if not any(b["id"] == self.board_id for b in boards):
                self.board_id = boards[0]["id"] if boards else None
            clear(self.board_list)
            selected = None
            for board in boards:
                row = Gtk.ListBoxRow()
                row.board_id = board["id"]
                line = Gtk.Box(spacing=10, margin_top=6, margin_bottom=6, margin_start=6, margin_end=6)
                from .project import project_image
                metadata = self.store.get('board_metadata', {}).get(str(board['id']), {})
                line.append(project_image(self, metadata, 20))
                line.append(label(board["title"], xalign=0, hexpand=True, ellipsize=3))
                from .board_deletion import board_delete_button
                remove = board_delete_button(self, board)
                if remove is not None:
                    line.append(remove)
                row.set_child(line)
                self.board_list.append(row)
                if board["id"] == self.board_id:
                    selected = row
            self.board_list.select_row(selected)
            ui.text(self.account_label, 'text', self.account.username if self.account else _("Mode de demostració") if self.demo else _("Comptes en línia de GNOME"))
            if self.board_id is None:
                self.scroll_position.cancel()
                self.pages.set_visible_child_name("empty")
                return
            self.pages.set_visible_child_name("board")
            board = next(b for b in boards if b["id"] == self.board_id)
            ui.text(self.header_title, 'title', board["title"])
            self.store.set_setting("board_id", self.board_id)
            self.scroll_position.prepare((self.board_id, self.query, self.only_mine))
            clear(self.board_body)
            self.board_body.append(board_header(self, board, self.card_count_text()))
            upper, lower = [], []
            for index, stack in enumerate(self.stacks()):
                is_triage = index == 0 and self.store.settings().get("triage", True)
                (upper if is_triage else lower).append(stack)
            for stack in upper:
                self.board_body.append(Column(stack, self, triage=True))
            limit = self.store.settings().get("columns_per_row", 0)
            fixed = isinstance(limit, int) and 1 <= limit <= 6
            columns = (Gtk.Grid(column_homogeneous=True, column_spacing=14, row_spacing=14,
                                valign=Gtk.Align.START, hexpand=True) if fixed else
                       Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                                   column_spacing=14, row_spacing=14, min_children_per_line=1,
                                   max_children_per_line=100, valign=Gtk.Align.START, hexpand=True))
            columns.add_css_class("workflow-grid")
            if fixed:
                columns.add_css_class("fixed-columns")
            for index, stack in enumerate(lower):
                column = Column(stack, self, flexible=fixed)
                if fixed:
                    columns.attach(column, index % limit, index // limit, 1, 1)
                else:
                    columns.insert(column, -1)
            if lower:
                self.board_body.append(columns)
            self.scroll_position.restore()
        finally:
            self._rendering = False
            self.update_status()
            self.update_notification_badge()
            self.comment_counts.refresh(self.snapshot, self.board_id)

    def retranslate(self):
        if self.engine.closed:
            return
        self.render()

    def manual_sync(self):
        self._manual_sync_until = time.monotonic()+.7
        self.update_sync_feedback()
        if not self._sync_feedback_timer:
            self._sync_feedback_timer = GLib.timeout_add(100, self.sync_feedback_tick)
        if not self.demo and not self.engine.api:
            self._manual_account_sync = True
            if not self.account_loading:
                self.account_loading = True
                self.start_account()
        else:
            self.engine.sync()

    def update_sync_feedback(self):
        active = self.engine.busy or time.monotonic() < self._manual_sync_until
        self.sync_spinner.set_spinning(active)
        self.sync_indicator.set_visible_child_name("spinner" if active else "icon")
        ui.text(self.sync_button, 'tooltip_text', _("S'està sincronitzant…") if active else _("Sincronitza amb Deck"))
        return active

    def sync_feedback_tick(self):
        if self.update_sync_feedback():
            return GLib.SOURCE_CONTINUE
        self._sync_feedback_timer = 0
        return GLib.SOURCE_REMOVE

    def update_status(self):
        self.update_sync_feedback()
        operations = self.store.operations()
        working = self.engine.busy or self.account_loading
        self.sidebar_spinner.set_spinning(working)
        self.status_indicator.set_visible_child_name("spinner" if working else "icon")
        self.status_icon.remove_css_class("sync-ok")
        self.status_icon.remove_css_class("sync-warning")
        ui.text(self.status_button, 'tooltip_text', _("Revisa els canvis pendents de sincronitzar"))
        if self.account_loading:
            status = _("S'està obrint el compte de GNOME…")
        elif self.engine.busy:
            status = _("S'està sincronitzant…")
        elif operations:
            status = ngettext("{count} canvi pendent", "{count} canvis pendents", len(operations)).format(count=len(operations))
            self.status_icon.set_from_icon_name("document-send-symbolic")
            self.status_icon.add_css_class("sync-warning")
        elif self.engine.error:
            status = _("No s'ha pogut sincronitzar")
            self.status_icon.set_from_icon_name("network-offline-symbolic")
        elif not self.store.settings().get("auto_sync", True):
            status = _("Sincronització manual")
            self.status_icon.set_from_icon_name("view-refresh-symbolic")
            ui.text(self.status_button, 'tooltip_text', _("Prem F5 per sincronitzar amb Deck."))
        else:
            last = self.store.get("last_sync")
            status = _("Actualitzat") if last else _("Canvis desats")
            self.status_icon.set_from_icon_name("object-select-symbolic")
            self.status_icon.add_css_class("sync-ok")
            if last:
                ui.text(self.status_button, 'tooltip_text', _("Darrera sincronització: {time}").format(time=time.strftime("%x · %H:%M", time.localtime(last))))
        ui.text(self.status_label, 'text', status)
        ui.text(self.banner, 'title', self.engine.error)
        self.banner.set_revealed(bool(self.engine.error) and not self.demo)

    def sync_changed(self):
        fresh = self.store.view()
        if fresh != self.snapshot:
            if self._open_column_menu and self._open_column_menu.get_mapped():
                self._render_after_menu = True
            else:
                self.render(snapshot=fresh)
        self.update_status()
        self.update_notification_badge()
        self.comment_counts.refresh(fresh, self.board_id)
        return GLib.SOURCE_REMOVE

    def column_menu_closed(self, menu):
        if self._open_column_menu is menu:
            self._open_column_menu = None
        if self._render_after_menu:
            self._render_after_menu = False
            GLib.idle_add(self.sync_changed)

    def selected_board(self, _list, row):
        if row and not self._rendering:
            self.board_id = row.board_id
            self.query = ""
            ui.text(self.search, 'text', "")
            self.render()
            if self.split.get_collapsed():
                self.split.set_show_sidebar(False)

    def search_changed(self, entry):
        self.query = entry.get_text().casefold().strip()
        self.render()

    def show_search(self, visible=None):
        if visible is None:
            visible = not self.search.get_visible()
        self.search.set_visible(visible)
        if visible:
            self.search.grab_focus()
        else:
            ui.text(self.search, 'text', "")

    def sidebar_changed(self, *_unused):
        visible = self.split.get_show_sidebar()
        self.store.set_setting("sidebar", visible)
        self.toggle_sidebar.set_active(visible)
        self.toggle_sidebar.set_icon_name("sidebar-show-symbolic" if visible else "sidebar-show-right-symbolic")
        text = _("Amaga els taulers") if visible else _("Mostra els taulers")
        ui.text(self.toggle_sidebar, 'tooltip_text', text)
        ui.accessible(self.toggle_sidebar, [Gtk.AccessibleProperty.LABEL], [text])

    def update_notification_badge(self):
        count = sum(not row['read'] for row in entries(self.store))
        ui.text(self.notification_count, 'text', str(count))
        side = max(20, self.notification_count.get_layout().get_pixel_size()[0]+10)
        self.notification_count.set_size_request(side, side)
        self.notification_count.set_visible(count > 0)

    def open_update(self, row, refreshed=False):
        target = destination(row)
        link = row.get('link') or ''
        board_id, card_id = target.get('board_id'), target.get('card_id')
        self.query = ''
        ui.text(self.search, 'text', '')
        if card_id:
            for bid, stacks in self.snapshot.get('stacks', {}).items():
                for stack in stacks:
                    card = next((c for c in stack.get('cards') or [] if c['id'] == card_id), None)
                    if card:
                        self.board_id = int(bid)
                        if card.get('archived'):
                            self.show_archived(stack['id'], True)
                        self.render()
                        if target.get('section') == 'attachments' and self.account:
                            uri = f'{self.account.server}/index.php/apps/deck/board/{bid}/card/{card_id}/attachments'
                            Gtk.UriLauncher.new(uri).launch(self, None, None)
                        else:
                            self.open_card(card, target=target)
                        return
        elif board_id and any(board['id'] == board_id for board in self.snapshot['boards']):
            self.board_id = board_id
            self.render()
            if target.get('section') == 'members':
                from .sharing import SharingDialog
                board = next(board for board in self.snapshot['boards'] if board['id'] == board_id)
                SharingDialog(self, board, focus_members=True).present(self)
            elif target.get('stack_id'):
                def find(widget):
                    if isinstance(widget, Column) and widget.stack['id'] == target['stack_id']:
                        return widget
                    child = widget.get_first_child()
                    while child:
                        result = find(child)
                        if result is not None:
                            return result
                        child = child.get_next_sibling()
                column = find(self.board_body)
                if column is not None:
                    self.scroll_position.cancel()
                    column.add_css_class('notification-target')
                    scroll_to_widget(self.scroll, self.board_body, column)
            else:
                self.scroll_position.cancel()
                self.scroll.get_vadjustment().set_value(0)
            return
        if not refreshed and not self.demo and self.engine.api and (card_id or board_id):
            def loaded(snapshot, error):
                if error:
                    message(self, _("No s'ha pogut obrir el destí de l'avís."), error)
                    return
                self.store.put('snapshot', snapshot)
                self.render()
                self.open_update(row, refreshed=True)
            self.engine.run(lambda api: api.fetch(), loaded)
            return
        if self.account and link:
            origin, target = urlsplit(self.account.server), urlsplit(link)
            if (origin.scheme, origin.netloc) == (target.scheme, target.netloc) and not target.username:
                Gtk.UriLauncher.new(link).launch(self, None, None)
                return
        message(self, _("No s'ha pogut obrir el destí de l'avís."),
                _("Pot ser que s'hagi eliminat o que ja no hi tinguis accés."))

    def new_card(self, stack_id=None):
        if not self.stacks():
            message(self, _("Crea una columna"), _("Afegeix una columna al tauler abans de crear la primera targeta."))
            return
        CardDialog(self, stack_id or self.stacks()[0]["id"]).present(self)

    def open_card(self, card, target=None):
        dialog = CardDialog(self, card["stackId"], card, target=target)
        dialog.present(self)
        return dialog

    def update_card(self, card, changes, kind="update", images=None):
        payload = {"board_id": self.board_id, "stack_id": card["stackId"], "card_id": card["id"],
                   "changes": changes, "base": {k: card.get(k) for k in changes}, "images": images or []}
        if kind == 'archive':
            self.enqueue_card_action(kind, payload, card,
                _("Targeta arxivada") if changes['archived'] else _("Targeta restaurada"))
        else:
            self.engine.enqueue(kind, payload)

    def move_card(self, card, stack_id, before=None, archived=None):
        state = bool(card.get('archived')) if archived is None else bool(archived)
        all_cards = sorted(self.cards_in_stack(stack_id), key=lambda c:(c.get('order',0),c['id']))
        cards = [c for c in all_cards if c['id'] != card['id']]
        peers = [c for c in cards if bool(c.get('archived')) == state]
        index = next((i for i,c in enumerate(peers) if c['id'] == before),len(peers))
        if stack_id == card['stackId'] and bool(card.get('archived')) == state:
            previous = [c['id'] for c in all_cards if bool(c.get('archived')) == state]
            if card['id'] in previous and previous.index(card['id']) == index:
                return
        order = index
        payload = {"board_id": self.board_id, "card_id": card["id"], "source_stack": card["stackId"],
                   "target_stack": stack_id, "order": order}
        payload.update(archived=state, base_archived=bool(card.get('archived')))
        title = _("Targeta moguda")
        if state != bool(card.get('archived')):
            title = _("Targeta arxivada") if state else _("Targeta restaurada")
        self.enqueue_card_action('move', payload, card, title)

    def enqueue_card_action(self, kind, payload, card, title):
        peers = sorted((item for item in self.cards_in_stack(card['stackId'])
                        if bool(item.get('archived')) == bool(card.get('archived'))),
                       key=lambda item:(item.get('order',0),item['id']))
        position = next((index for index,item in enumerate(peers) if item['id'] == card['id']),card.get('order',0))
        before = {'stack_id': card['stackId'], 'order': position, 'archived': bool(card.get('archived'))}
        operation_id = self.engine.enqueue(kind, payload, undo={'before': before})
        previous = getattr(self, '_undo_toast', None)
        if previous:
            previous.dismiss()
        toast = ui.create(Adw.Toast, title=title, button_label=_("Desfés"), timeout=8)
        def finished(error):
            self.toast_overlay.add_toast(ui.create(Adw.Toast, title=error or _("Acció desfeta")))
        toast.connect('button-clicked', lambda *_unused: self.engine.undo(operation_id, finished))
        self._undo_toast = toast
        self.toast_overlay.add_toast(toast)

    def creation_done(self, kind, result, error):
        if not error and result and result.get('id'):
            remember_creator(self.store, kind, result['id'], current_person(self))
        self.management_done(result, error)

    def new_board(self):
        TextDialog(self, _("Tauler nou"), "", lambda title, _unused: self.engine.run(lambda api: api.create_board(title),
            lambda result, error: self.creation_done('board', result, error))).present(self)

    def new_column(self):
        board_id, order = self.board_id, len(self.stacks())
        TextDialog(self, _("Columna nova"), "", lambda title, _unused: self.engine.run(lambda api: api.create_stack(board_id, title, order),
            lambda result, error: self.creation_done('stack', result, error))).present(self)

    def edit_column(self, stack):
        board_id = self.board_id
        def save(title, _unused):
            if title != stack["title"]:
                self.engine.run(lambda api: api.rename_stack(board_id, stack, title), self.management_done)
        dialog = TextDialog(self, _("Canvia el nom"), stack['title'], save)
        dialog.present(self)
        return dialog

    def edit_column_color(self, stack):
        def save(color):
            colors = self.store.settings().get('colors', {})
            colors[str(stack['id'])] = color
            self.store.set_setting('colors', colors)
            self.render()
        dialog = ColumnColorDialog(self, stack, save)
        dialog.present(self)
        return dialog

    def management_done(self, result, error):
        if error:
            message(self, _("No s'ha pogut completar el canvi"), error)
        else:
            self.engine.sync(read_only=not self.store.settings().get("auto_sync", True))

    def start_account(self):
        def load():
            try:
                account = Account.load()
                if account:
                    account.save()
                error = "" if account else _("Selecciona un compte de Nextcloud a Comptes en línia de GNOME.")
            except ValueError as exception:
                account, error = None, str(exception)
            except Exception:
                account, error = None, _("No s'ha pogut obrir el compte de GNOME. Revisa els Comptes en línia.")
            def loaded():
                if self.engine.closed:
                    return GLib.SOURCE_REMOVE
                self.account_loading = False
                self.account = account
                if account:
                    self.assets.account_key = account.goa_id
                    self.store.put("asset_account", account.goa_id)
                self.engine.api = Deck(account) if account else None
                self.engine.error = error
                self.render()
                manual = self._manual_account_sync
                self._manual_account_sync = False
                if account:
                    self.engine.sync(automatic=not manual)
            GLib.idle_add(loaded)
        self.engine.executor.submit(load)

    def open_deck(self, card):
        if self.account:
            uri = f"{self.account.server}/index.php/apps/deck/#/board/{self.board_id}/card/{card['id']}"
            Gtk.UriLauncher.new(uri).launch(self, None, None, None)

    def show_shortcuts(self):
        from .shortcuts import shortcuts_dialog
        shortcuts_dialog().present(self)

    def about(self):
        about_dialog().present(self)

    def configure_sync(self, enabled=None, interval=None):
        previous = self.store.settings().get("auto_sync", True)
        if enabled is not None:
            self.store.set_setting("auto_sync", enabled)
        if interval is not None:
            self.store.set_setting("sync_interval", sync_interval({"sync_interval": interval}))
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0
        settings = self.store.settings()
        if settings.get("auto_sync", True):
            self.timer = GLib.timeout_add_seconds(sync_interval(settings), self.periodic_sync)
            if not previous and not self.demo:
                self.periodic_sync()
        self.update_status()

    def periodic_sync(self):
        if not self.demo and self.store.settings().get("auto_sync", True):
            if self.engine.api:
                self.engine.sync(automatic=True)
            elif not self.account_loading:
                self.account_loading = True
                self.start_account()
        return GLib.SOURCE_CONTINUE

    def close_requested(self, *_unused):
        self.scroll_position.cancel()
        self.store.set_setting("width", self.get_width())
        self.store.set_setting("height", self.get_height())
        self.store.set_setting("maximized", self.is_maximized())
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0
        if self._sync_feedback_timer:
            GLib.source_remove(self._sync_feedback_timer)
        self.avatar_loader.close()
        self.comment_counts.close()
        self.engine.close()
        return False
