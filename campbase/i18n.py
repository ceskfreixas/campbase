# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Application languages, standard gettext catalogs and an English fallback."""
import gettext as _gettext
import locale
import os
import sqlite3
from contextlib import closing
from pathlib import Path

LANGUAGES = {'ca':'Català', 'eu':'Euskara', 'gl':'Galego (AGAL)', 'es':'Español', 'oc':'Occitan aranés', 'en':'English'}
_SOURCE = Path(__file__).resolve().parents[1] / 'po/locale'
LOCALE_DIR = _SOURCE if _SOURCE.exists() else Path(__file__).resolve().parents[2] / 'locale'
CURRENT_LANGUAGE = 'en'
CURRENT_PREFERENCE = 'auto'
_translator = _gettext.NullTranslations()
_SYSTEM_ENVIRONMENT = {key: value for key, value in os.environ.items()
                       if key in {'LANG', 'LANGUAGE'} or key.startswith('LC_')}


class Message(str):
    """A string with enough context to translate an existing UI binding again."""
    def __new__(cls, renderer):
        value = super().__new__(cls, renderer())
        value._renderer = renderer
        return value

    def render(self):
        return self._renderer()

    def __copy__(self):
        return self

    def __deepcopy__(self, memo):
        return self

    def format(self, *args, **kwargs):
        render = lambda value: value.render() if isinstance(value, Message) else value
        return Message(lambda: self.render().format(*[render(value) for value in args],
                                                    **{key: render(value) for key, value in kwargs.items()}))

    def __add__(self, other):
        return Message(lambda: self.render() + (other.render() if isinstance(other, Message) else other))

    def __radd__(self, other):
        return Message(lambda: (other.render() if isinstance(other, Message) else other) + self.render())


def system_language(environment=None):
    environment = os.environ if environment is None else environment
    value = (environment.get('LANGUAGE') or environment.get('LC_ALL') or environment.get('LC_MESSAGES') or environment.get('LANG') or 'en').split(':')[0]
    base = value.replace('-', '_').split('_')[0].split('.')[0].split('@')[0].lower()
    return base if base in LANGUAGES else 'en'


def resolve_language(preference='auto', environment=None):
    return preference if preference in LANGUAGES else system_language(environment)


def saved_preference():
    path = Path(os.environ.get('XDG_DATA_HOME', Path.home()/'.local/share')) / 'campbase/cache.sqlite3'
    if not path.exists():
        return 'auto'
    try:
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as db:
            row = db.execute("SELECT value FROM state WHERE key='settings'").fetchone()
        import json
        value = json.loads(row[0]).get('language', 'auto') if row else 'auto'
        return value if value in LANGUAGES else 'auto'
    except (OSError, ValueError, sqlite3.Error):
        return 'auto'


def configure(preference='auto', native=False, *, user_choice=False):
    global CURRENT_LANGUAGE, CURRENT_PREFERENCE, _translator
    if not user_choice:
        preference = os.environ.get('CAMPBASE_LANGUAGE', preference)
    CURRENT_PREFERENCE = preference
    CURRENT_LANGUAGE = resolve_language(preference, _SYSTEM_ENVIRONMENT)
    english = _gettext.translation('campbase', localedir=LOCALE_DIR, languages=['en'], fallback=True)
    _translator = _gettext.translation('campbase', localedir=LOCALE_DIR, languages=[CURRENT_LANGUAGE], fallback=True)
    if CURRENT_LANGUAGE != 'en':
        _translator.add_fallback(english)
    if native:
        # Native GTK/Adwaita controls use GNU gettext's language selection too.
        os.environ['LANGUAGE'] = CURRENT_LANGUAGE + ':en'
        choices = {'ca':'ca_ES', 'eu':'eu_ES', 'gl':'gl_ES', 'es':'es_ES', 'oc':'oc_FR', 'en':'en_US'}
        for candidate in [choices[CURRENT_LANGUAGE]+'.UTF-8', choices[CURRENT_LANGUAGE]+'.utf8', 'C.UTF-8']:
            try:
                locale.setlocale(locale.LC_ALL, candidate)
                os.environ['LC_ALL'] = candidate
                break
            except locale.Error:
                continue
    return CURRENT_LANGUAGE


def _(text):
    return Message(lambda: _translator.gettext(text))


def ngettext(singular, plural, count):
    return Message(lambda: _translator.ngettext(singular, plural, count))


def change_language(preference):
    configure(preference, native=True, user_choice=True)
    from .localization import refresh
    refresh()


_reverse = None

def canonical_message(text):
    global _reverse
    if _reverse is None:
        _reverse = {}
        for language in LANGUAGES:
            translator = _gettext.translation('campbase', localedir=LOCALE_DIR, languages=[language], fallback=True)
            for key, value in getattr(translator, '_catalog', {}).items():
                if isinstance(key, str) and key and isinstance(value, str):
                    _reverse[value] = key
    return _reverse.get(text, text)


def saved_error(text):
    key = canonical_message(text)
    if key != text or key in getattr(_translator, '_catalog', {}):
        return _(key)
    # HTTP status codes are the only formatted errors stored in the outbox.
    import re
    template = 'Nextcloud ha retornat un error ({code}).'
    for language in LANGUAGES:
        translator = _gettext.translation('campbase', localedir=LOCALE_DIR, languages=[language], fallback=True)
        pattern = re.escape(translator.gettext(template)).replace(re.escape('{code}'), r'(?P<code>\d+)')
        match = re.fullmatch(pattern, text)
        if match:
            return _(template).format(code=match['code'])
    return text


configure()
