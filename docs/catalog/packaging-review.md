# Campbase packaging review

Checked on 2026-10-30 against the local 0.1.3 working tree. This is an internal
technical review, not a Flathub submission or text intended for its review thread.
The audit did not submit the application or request any Flathub exception.
The following results record checks performed before the GitHub 0.1.3 publication.

## Result

The application builds with the official Flatpak Builder and its desktop metadata
validates. The isolated exported repository does not yet pass the complete Flathub
linter because screenshot URLs and mirrored screenshot assets are missing.
The published 0.1.2 revision has failing CI runs. Corrections have now passed local
Ubuntu 24.04 native checks; a new GitHub run is still required after publication.

| Check | Result |
| --- | --- |
| Local unit suite | 164 tests passed |
| Six translated catalogs | Compiled catalogs included in the package |
| Desktop entry | Validated with `desktop-file-validate` |
| MetaInfo with official Flathub tooling | Pass; one pedantic informational item |
| Existing development manifest | Pass with a GNOME 51 runtime upgrade warning |
| Official Builder compile and export | Pass, including `appstreamcli compose` |
| Isolated repository lint | Two screenshot errors; GNOME 51 upgrade warning |
| Local source / whitespace | `git diff --check` passed |
| Public GitHub CI at `31872ec` | Historical runs failed; local corrections below await a new remote run |

The official tool used was `org.flatpak.Builder`, user-installed from Flathub,
commit `b4f1412db7e6b33c08671438909563d79a8b39b8d42d5fea93adaa21b584beec`.
Its linter reported `3.0.0.post915.dev0+ffc7635f`.
The isolated build is under `$HOME/.cache/campbase-packaging-audit/`.
The application installed for daily use was not replaced by this audit build.

## Permissions and host integration

The development manifest declares network, IPC, Wayland, fallback X11, DRI GPU
access and permission to talk to two session-bus services:

- `org.gnome.OnlineAccounts`: enumerate Nextcloud accounts, validate credentials
  and request their password for server connections.
- `org.gnome.Settings`: open the Online Accounts settings panel.

No broad home, host filesystem, camera, microphone or session-bus access is
requested in this manifest. Selected attachments and downloads use `Gtk.FileDialog`
and `Gio.File`; selected files are intended to be granted through the file chooser
portal. This audit does not substitute for an interactive portal test on a clean
second desktop. Installed permissions may additionally include user or global
Flatpak overrides; they are separate from the manifest under review.

Campbase currently requires a configured Nextcloud account in GNOME Online
Accounts for normal use. Demo mode does not require one. This host integration
needs review against Flathub's environment-locked and host-dependent application
policies. Do not assume an exception or admission is granted. Assess this before
spending time on a submission.

## Dependencies, licenses and payload

- Python and PyGObject / GTK / Adwaita come from the GNOME 50 SDK and platform.
- GNOME 50 builds successfully. The linter recommends GNOME 51; this is a warning,
  not the cause of the current repository validation failure. A runtime upgrade
  needs its own compile and native UI validation.
- Mistune is pinned to 3.4.0 both in `requirements.txt` and the development manifest.
  The wheel source has a SHA-256 checksum and its install uses no dependency
  resolution or package-index access.
- Mistune's included license is BSD-3-Clause, copyright Hsiaoming Yang. It is present
  under its installed `dist-info/licenses/LICENSE`. Campbase's GPL-3.0-or-later
  license and notice are installed under the application's shared license directory.
  The human-written distribution packaging still needs to ensure every module's
  license is installed under `$FLATPAK_DEST/share/licenses/$FLATPAK_ID` as required
  by Flathub. Do not mistake the presence of wheel metadata for that packaging step.
- Checked the compiled payload for local `account.json`, SQLite caches and private
  key / certificate file names; none were present. The application source, icons,
  six catalogs and license files are included. Screenshots use fictional content.

## Exact remaining linter results

The clean single-application exported repository reports:

- `metainfo-missing-screenshots`
- `appstream-screenshots-not-mirrored-in-ostree`
- Warning: `runtime-update-available-to-org.gnome.Platform-51`

The 18 screenshots are now committed at `c6010713791baf67de977dcf39bcfab0f51872c7`.
MetaInfo links the corresponding immutable image URLs and localized captions.
The two screenshot errors above describe the pre-publication audit build;
rebuild and repeat repository lint before a Flathub submission.

The older shared local repository also contains the retired application ID and a
build with AppStream composition disabled. Its errors are not evidence about the
new isolated build. The official build generated
`share/app-info/xmls/cat.ceskfreixas.Campbase.xml.gz` successfully.

## GitHub CI finding

Both latest public runs for `31872ec85f16ade0f53c409e4d0667a1ac4d42b5` are marked
failed. The inspected failed test log stops in `tests/native_drag_smoke.py:121`,
with `CAMPBASE_ARCHIVE_DROP=1`, at:

```python
assert w.dragged_card and w.dragged_card['id'] == 101
```

The GitHub environment is Ubuntu 24.04 (GTK 4.14.5 / libadwaita 1.5.0).
Local investigation and corrections, validated with that same distribution:

- GTK 4.14 has a 100 ms drag-start timer in addition to the movement threshold.
  The old test sent only one motion, sometimes before the timer expired, and
  then waited without sending any more motion. The corrected test continues
  moving within the same press; it does not retry the gesture or bypass GTK.
- Recompute native surface/root coordinates for each input event. A controlled
  relocation reproduces a failure with the old calculation and passes with
  the new one. CI now includes this relocation in its archive-drop case.
- Wait for a dialog to map, receive an allocation and deliver two frame callbacks
  before triggering its controls. Wait for the actual closing state before
  continuing, instead of assuming an animation finished in a fixed interval.
- Set an explicit 360 × 360 window minimum as required for Adwaita breakpoints.
- Refresh labels / board contents after the editing / deletion dialog closes,
  so focus restoration precedes replacement of its triggering controls.
- Put recovery ActionRows in a native ListBox, as their keyboard focus contract
  requires. The resource smoke now explicitly focuses a recovery row and was
  verified with `G_DEBUG=fatal-criticals` (no critical GTK diagnostics).
- Use the Cairo software renderer in headless CI, matching the isolated Flatpak
  validation renderer. Drag events, native preview, drop markers, queued moves,
  image paste and notification outside-click assertions remain enabled.

Local verification passed: all four active/archived source/destination drag
combinations under a one-half-CPU quota, including window relocation; an
additional drag-handle case; resource, board deletion, label and dialog-layout
smokes; and 164 unit tests. The rebuilt installed Flatpak also passed the native
resource smoke, and installed modules/styles plus all six catalogs match source.
A new remote CI result is not claimed. No generic remote rerun was requested.

GTK source explaining the timer:
https://github.com/GNOME/gtk/blob/4.14.5/gtk/gtkdragsource.c

Adwaita breakpoint minimum-size requirement:
https://gnome.pages.gitlab.gnome.org/libadwaita/doc/main/migrating-to-breakpoints.html

Run inspected: https://github.com/ceskfreixas/campbase/actions/runs/41032074501

## Human publication boundaries

The development manifest uses a local directory as its source and is AI-assisted.
It is not a submission-ready Flathub manifest. A human maintainer must independently
write the Flathub manifest using a published immutable source revision and handle
submission and review interactions, subject to the current policy. This report is
not a generated manifest, submission description or exception request.

The public history currently begins on 2026-10-28. Flathub requires meaningful
real-world development history and evaluates very recent projects conservatively.
Document genuine use and maintenance; do not manufacture or backdate history.
Domain ownership and the relationship between `ceskfreixas.cat` and Campbase also
remain publication checks; no DNS, website redirect or mail changes were made.

References:

- https://docs.flathub.org/docs/for-app-authors/requirements
- https://docs.flathub.org/docs/for-app-authors/linter
- https://github.com/flathub-infra/flatpak-builder-lint
- https://docs.flathub.org/docs/for-app-authors/metainfo-guidelines
