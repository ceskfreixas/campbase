# Campbase catalog preparation

This is a local review package for the application listing, not a Flathub
submission or an accepted listing. It covers English, Catalan, Spanish,
Galician AGAL, Basque and Aranese Occitan.

Open `index.html` to review the descriptions, requirements, screenshot captions
and three native screenshots per language. `copy.json` contains the listing
copy and the entirely fictional workshop content used for screenshots.
The descriptions are also included in `data/cat.ceskfreixas.Campbase.metainfo.xml`.

## Capturing the application

Use only a dedicated Xvfb display on `:98`, with a compositor for native rounded
corners, the Cairo renderer and Adwaita Sans 11. The capture helper records only
its own synthetic X11 surface; it never captures the desktop, opens a real
account, reads passwords or sends network requests. It creates a temporary
Store and uses Campbase's existing demo mode. The application layout is set to
three columns per row so the entire workshop is visible at 1000 × 700 pixels.
The application icon and native UI are unchanged. Screenshots are not retouched.

Run `scripts/capture_screenshots.py --language LANGUAGE --output DIRECTORY`
in the Campbase Flatpak with the checkout accessible, `DISPLAY=:98`,
`GDK_BACKEND=x11`, `GSK_RENDERER=cairo` and `CAMPBASE_SCREENSHOT_FIXTURE=1`.
The helper rejects ordinary desktop displays. Repeat for `en ca es gl eu oc`.
Then run `python3 scripts/preview_catalog.py` to rebuild the offline preview.

The screenshots contain no names, addresses, messages or other content from
real accounts. Their captions and interface language must stay matched.

## Remaining publication work

- Human review of the copy, especially the Basque and Aranese translations.
- Publish the screenshots in a source commit. Only then add immutable, direct
  image URLs pinned to that commit to the MetaInfo `screenshots` section.
  No remote image URLs are invented in this local draft.
- Establish a visible relationship between the domain and Campbase; domain
  verification uses a token supplied by Flathub later. Preserve existing
  website redirects and mail services.
- Have a human maintainer independently prepare the Flathub manifest and
  submission. The current development manifest and this listing preparation
  are AI-assisted. The Flathub policy forbids AI-assisted manifests and
  AI-generated submission/review interactions, and requires disclosure of
  generated material in the application and packaging. Human review alone
  does not remove the manifest restriction.
- Review GNOME Online Accounts host integration, server requirements, runtime,
  permissions, build/lint results and real-world development history before
  submission. Admission is not guaranteed.

References checked on 2026-10-30:

- https://docs.flathub.org/docs/for-app-authors/metainfo-guidelines
- https://docs.flathub.org/docs/for-app-authors/metainfo-guidelines/quality-guidelines
- https://docs.flathub.org/docs/for-app-authors/requirements#generative-ai-policy
