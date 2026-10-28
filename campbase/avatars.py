# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Small same-origin Nextcloud avatars, loaded separately from card syncing."""
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote
import gi
gi.require_version('Adw', '1')
gi.require_version('Gtk', '4.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Adw, Gdk, GdkPixbuf, GLib
from .assets import Assets
from .collaboration import person


class AvatarLoader:
    def __init__(self, window):
        self.window = window
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='campbase-avatars')
        self.waiters = {}
        self.attempted = {}
        self.closed = False

    def widget(self, user, size=32):
        user = person(user)
        avatar = Adw.Avatar(size=size, text=user['displayname'], show_initials=True,
                            tooltip_text=user['displayname']+' (@'+user['uid']+')')
        api = self.window.engine.api
        if self.window.demo or not api or not user['uid'] or user['uid'] in {'.', '..'}:
            return avatar
        url = api.server+'/index.php/avatar/'+quote(user['uid'], safe='')+'/64'
        key = (api.server, api.username, user['uid'])
        assets = Assets(self.window.store.directory, getattr(api, 'goa_id', ''))
        path = assets.remote_path(url)
        if path.exists():
            self.apply(avatar, path)
            if time.time()-path.stat().st_mtime < 3600:
                return avatar
        if key in self.waiters:
            self.waiters[key].append(avatar.weak_ref())
        elif time.time()-self.attempted.get(key, 0) >= 3600:
            self.waiters[key] = [avatar.weak_ref()]
            self.attempted[key] = time.time()
            self.executor.submit(self.download, api, assets, key, url)
        return avatar

    @staticmethod
    def apply(avatar, path):
        try:
            info = GdkPixbuf.Pixbuf.get_file_info(str(path))
            if info and info[0] and 0 < info[1] <= 512 and 0 < info[2] <= 512:
                avatar.set_custom_image(Gdk.Texture.new_from_filename(str(path)))
        except (GLib.Error, OSError):
            pass

    def download(self, api, assets, key, url):
        path = None
        try:
            data = api.fetch_image(url, max_bytes=512*1024, timeout=4)
            path = assets.cache_image(url, data)
        except Exception:
            # Missing/generated SVG/private avatars keep the native initials.
            pass
        if not self.closed:
            GLib.idle_add(self.loaded, api, key, path)

    def loaded(self, api, key, path):
        references = self.waiters.pop(key, [])
        if not self.closed and api is self.window.engine.api and path:
            for reference in references:
                if avatar := reference():
                    self.apply(avatar, path)
        return GLib.SOURCE_REMOVE

    def close(self):
        self.closed = True
        self.waiters.clear()
        self.executor.shutdown(wait=False, cancel_futures=True)
