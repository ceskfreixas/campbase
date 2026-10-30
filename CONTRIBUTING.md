# Contributing

Campbase is a development version released under GPL-3.0-or-later; see LICENSE.
The project lives at https://github.com/ceskfreixas/campbase. Use the repository
issues for bug reports and suggestions; propose code changes through pull requests.
The final distribution application ID remains to be chosen.
Contributions must be compatible with GPL-3.0-or-later.

## Design and implementation

- Maintain all six gettext catalogs: Catalan, Basque, Galician AGAL, Spanish,
  Aranese Occitan and English. Use AGAL -ão/-ões, não and uma forms; preserve
  Aranese rather than substituting another Occitan variety. Catalan source
  messages use `_()` / `ngettext()`; preserve placeholders and plurals.
  English is the fallback. Compile catalogs with `scripts/compile_translations.py`.
  Catalan and English technical discussion are both welcome.
- Prefer native GTK4/libadwaita widgets and Adwaita symbolic icons.
- Keep cards distinct from to-do checkboxes; triage is a responsive upper row.
- Preserve accessibility, keyboard navigation, system appearance and narrow
  window behavior.
- Obtain account credentials through GNOME Online Accounts; do not store a separate password. Never include real account files,
  database exports, authorization headers or private task content in patches,
  test fixtures, screenshots or logs.
- Use synthetic HTTP fixtures for automated write tests. Never run a developer
  test against an existing user's cards.
- Keep sync operations serialized and durable. Treat uncertain creates and
  same-field conflicts as review states, not automatic retries.

Run `python3 -m unittest discover -s tests -v` and the focused UI smoke test before
proposing a change. Include a short description of the user-visible behavior and
any compatibility limits. Keep unrelated changes separate.

Native pointer tests require a dedicated Xvfb server. They verify either the
server process or a unique root marker before injecting input. For Flatpak UI
tests, set `DISPLAY` in the launcher's environment; `--env=DISPLAY` alone does
not select which host X11 socket Flatpak mounts. Use an isolated root marker
with `CAMPBASE_TEST_DISPLAY_TOKEN` for Flatpak input tests.

Live language changes use `i18n.Message` strings and the native text bindings in
`localization.py`. Use `ui.create` for translated widget properties, `ui.text`
for changing owned interface text, and `ui.selection` for translated preference
models. Keep user-entered titles, descriptions, labels and comments as literal
content; never infer translations from their visible wording.

Native dialog tests use `tests/gui_helpers.py` to wait for mapping, allocation
and frame delivery before interacting with a dialog. Headless CI uses Cairo
software rendering. Native drag tests retain real X11/XTest input and continuous
motion so GTK 4.14 can satisfy its drag-start timer as well as its distance
threshold; do not replace these with programmatic move calls or gesture retries.
