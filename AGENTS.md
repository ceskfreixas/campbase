# Campbase project guidance

Keep the app, documentation and release metadata under the Campbase name.
Preserve the original yellow square and tent icon unless a new design is approved.
The current version remains 0.1.0 during the initial development review.

## Every new version

- Update the version in `campbase/__init__.py`, `meson.build` and AppStream.
- Update `campbase/releases.py` with the new version and concise user-facing
  release notes. The About dialog must show the notes for the current version.
- Translate every new or changed message in all six catalogs: Catalan, Basque,
  Galician AGAL, Spanish, Aranese Occitan and English. Preserve placeholders.
- Compile the translations and verify that About, the version badge and release
  notes work in all six languages, including live language changes.
- Use `scripts/release_notes.py --language en` to export the same notes for
  GitHub. Update the GitHub release as part of publishing the requested new
  version; its tag, title and application version must agree.
- Run the release metadata checks and appropriate application tests. A local
  UI tweak does not by itself require a new version, Git commit or publication.

Keep user data and credentials private. Use synthetic data for automated tests.
