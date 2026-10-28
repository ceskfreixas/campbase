# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Private, content-checked images selected through the file portal."""
from .i18n import _, ngettext
import hashlib
import json
import re
import uuid
from pathlib import Path

import gi
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, Gio
from .storage import private_dir

MAX_IMAGE_BYTES = 16 * 1024 * 1024
# The existing URI scheme is retained for previously queued offline images.
LOCAL_IMAGE = re.compile(r"bivac-image://([a-f0-9]{32})")


class Assets:
    def __init__(self, directory, account_key=""):
        self.directory = Path(directory)
        self.account_key = account_key
        self.images = private_dir(self.directory / "images")
        self.records = private_dir(self.directory / "image-records")
        self.remote = private_dir(self.directory / "image-cache")
        self.icons = private_dir(self.directory / "board-icons")

    @staticmethod
    def validate(path, allow_svg=False):
        if path.stat().st_size > MAX_IMAGE_BYTES:
            raise ValueError(_("La imatge és massa gran. El límit és de 16 MB."))
        info = GdkPixbuf.Pixbuf.get_file_info(str(path))
        if not info or info[0] is None:
            raise ValueError(_("Aquest fitxer no és una imatge vàlida."))
        image_format, width, height = info
        name = image_format.get_name()
        allowed = {"png", "jpeg", "webp", "gif"} | ({"svg"} if allow_svg else set())
        if name not in allowed or width <= 0 or height <= 0 or width * height > 40_000_000:
            raise ValueError(_("Tria una imatge PNG, JPEG, WebP o GIF de mida adequada.") if not allow_svg else _("Tria una imatge o una icona SVG vàlida."))
        return {"jpeg": "jpg"}.get(name, name)

    def import_file(self, file, icon=False):
        size = file.query_info("standard::size", Gio.FileQueryInfoFlags.NONE, None).get_size()
        if size > MAX_IMAGE_BYTES:
            raise ValueError(_("La imatge és massa gran. El límit és de 16 MB."))
        success, data, _etag = file.load_contents(None)
        if not success:
            raise ValueError(_("No s'ha pogut llegir la imatge."))
        return self.import_bytes(data, file.get_basename() or _("Imatge"), icon=icon)

    def import_bytes(self, data, name="Imatge.png", icon=False):
        if len(data) > MAX_IMAGE_BYTES:
            raise ValueError(_("La imatge és massa gran. El límit és de 16 MB."))
        token = uuid.uuid4().hex
        directory = self.icons if icon else self.images
        temporary = directory / (token + ".tmp")
        temporary.write_bytes(data)
        temporary.chmod(0o600)
        try:
            extension = self.validate(temporary, allow_svg=icon)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        target = temporary.with_suffix("." + extension)
        temporary.rename(target)
        record = {"token": token, "path": str(target.relative_to(self.directory)),
                  "sha256": hashlib.sha256(data).hexdigest(), "extension": extension,
                  "name": name.replace("\n", " ").replace("\r", " ")}
        if not icon:
            path = self.records / (token + ".json")
            path.write_text(json.dumps(record))
            path.chmod(0o600)
        return record

    def local(self, uri):
        match = LOCAL_IMAGE.fullmatch(uri)
        if not match:
            return None
        path = self.records / (match[1] + ".json")
        if not path.exists():
            return None
        record = json.loads(path.read_text())
        if self.resolve(record["path"]) is None:
            return None
        return record

    def resolve(self, relative):
        if not relative:
            return None
        path = (self.directory / relative).resolve()
        if not path.is_relative_to(self.directory.resolve()) or not path.is_file():
            return None
        return path

    def remote_path(self, url):
        return self.remote / (hashlib.sha256((self.account_key+"\n"+url).encode()).hexdigest() + ".image")

    def cache_image(self, url, data):
        path = self.remote_path(url)
        path.write_bytes(data)
        path.chmod(0o600)
        try:
            self.validate(path)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return path
