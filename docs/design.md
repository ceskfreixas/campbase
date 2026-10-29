# Design and protocol notes

## References studied

- [Basecamp Card Tables](https://updates.37signals.com/post/new-in-basecamp-card-tables)
  and [current Card Tables help](https://5.basecamp-help.com/article/1063-card-tables):
  triage above the workflow, cards as units of work, and a detailed card editor.
- [Nextcloud Deck for Android](https://github.com/stefan-niedermann/nextcloud-deck),
  including its official screenshots: a board-focused sidebar, simple column
  navigation, card titles, labels, due dates and comments.
- [Deck's documented API](https://github.com/nextcloud/deck/blob/main/docs/API.md).

These are behavioral and visual references, not bundled code, icons or artwork.
Campbase is implemented independently and uses the system's native Adwaita widgets.

## Local design decisions

- The optional first-column section is a full-width upper area.
- Its cards wrap automatically, with a 252-pixel minimum card size.
- Ordinary workflow columns are shown below and adapt to narrower windows.
- Done/Fet stays a normal column. Archiving is a separate card property.
- Cards have no default completion checkbox.
- Compact content height, rather than a fixed triage height, controls spacing.
- The sidebar lists boards; its startup visibility is configured independently
  from toggling it during the current session. The startup board can be fixed or
  follow the last selection, with a safe fallback if it is unavailable.
- Column colors and project descriptions/icons are local presentation metadata.
- Column tints use the original stripe color at 8% alpha; the stripe is unchanged.
- Card previews omit descriptions; the detailed editor renders native text tags.
- The sidebar toggle reflects its actual state; F5 triggers manual sync.
- UI strings have six gettext catalogs with English fallback; Python identifiers and protocol fields are English.

## Synchronization details

The REST base path is `/index.php/apps/deck/api/v1.0`. Comments use the OCS path
`/ocs/v2.php/apps/deck/api/v1.0`. Basic authentication uses a Nextcloud application
password retrieved on demand from GNOME Online Accounts after EnsureCredentials. Only the selected GOA account identifier is persisted. HTTPS is required outside loopback tests,
and credentialed requests do not follow redirects.

The destination stack ID must occur in the reorder URL, not only in its body.
[Deck issue 7933](https://github.com/nextcloud/deck/issues/7933) documents the route
parameter precedence. The response is an array; Campbase verifies both the returned
identity/destination and a subsequent read before treating a move as confirmed.

The single worker refreshes authentication, drains pending operations in order,
then reads one complete snapshot. An idle cycle reads that snapshot once. New
card creation first checks the destination board with a lightweight read; a
failed preflight remains an unsent draft. Cache replacement is atomic. Successful creates remap temporary
IDs in dependent queued operations. Each confirmed operation updates the local
cache before leaving the outbox. Interrupted creates are marked for review on
restart, preventing a blind duplicate POST.

Edits compare only the fields the user changed against the editor's base values.
Other remote fields are preserved. A conflict leaves the local draft in the
outbox and requires an explicit decision.

Automatic synchronization can be disabled; new card edits then remain in the
outbox until explicit sync. Board management can refresh the snapshot without
sending those edits. Periodic intervals are configurable from 30 to 600 seconds
(default 45). Queued requests are coalesced without turning a read-only refresh
into permission to send an automatic write after automatic sync is disabled.

## Scope of 0.1.0

One account; board/column creation and column renaming; card creation, edits,
movement, ordering, archiving and restoration; board label creation and card membership; native rich
Markdown descriptions; embedded image uploads and offline previews; due dates;
comments and author-only comment deletion; per-column archive visibility and
explicit archived-card deletion; synchronized project names and local project descriptions/icons.
General attachment management, label renaming/deletion, a dedicated
trash view and additional languages are follow-ups.

Images are uploaded using multipart API v1.1 with `type=file`, an empty `data`
field (required by some server versions), and a binary `file` field. Deterministic
filenames and an attachment-list lookup avoid retry duplicates. Creating a card
with images persists its real ID before uploads start; subsequent failures retry
an update rather than creating another card. Later offline edits have local image
URIs rebased to confirmed server URLs. Authenticated previews are restricted to
the account origin and cached under an account-specific key. Underline is stored
as `<u>`; other clients may not render it. No WebKit or executable HTML is used.

Labels use the board details API and dedicated `assignLabel` / `removeLabel`
card endpoints. Membership edits merge only the explicitly toggled IDs, preserving
unrelated mobile changes and tolerating partially successful retries. New cards
checkpoint their real ID before assigning labels or uploading images. New label
creation is an explicit online board operation; an exact title/color match is
reused if a previous response was lost.

Language changes update bound UI properties, accessible labels, menu items,
response labels and string models in place. Selection notifications are guarded
during model updates. Editor buffers and their undo/selection state are retained;
plain user content is never reverse-translated. The original desktop locale is
kept separately so returning to Automatic does not reuse an overridden locale.
Fixed workflow layouts use a homogeneous grid with 1–6 columns per row; only
Automatic uses the width-dependent flow layout. Card minimum widths are relaxed
and card metadata can wrap inside fixed columns. Column headers share one
compact horizontal layout: color, expanding title, count and menu.


## Collaboration

Board ACLs use the Deck API `POST /boards/{id}/acl`, with separate edit, share and
manage permissions. Candidates come from the local OCS Sharee API with remote
lookup disabled. Permission changes and access removal are explicit online
operations; uncertain results are re-read before success is shown. No test writes
to a real board or notifies a real user.

Assignments use the dedicated `assignUser` and `unassignUser` card endpoints.
Only explicitly toggled user IDs are changed, preserving concurrent assignments
and group/team entries. New cards checkpoint their real ID before assignments,
labels or images are sent. Assignment drafts survive restarts and manual mode.

The OCS user profile supplies the canonical UID rather than assuming the GOA
login address is the user's Deck identifier. Comments show server actor metadata
and local timestamps. Profile avatars load from Nextcloud with native initials
as fallback. A separate two-worker loader, four-second timeout, same-origin
checks, size limits and private cache keep avatar reads out of the sync queue. The member picker inserts
Nextcloud's username mention syntax (quoted when required); display names are presentation only.

Known mentions use UTF-8 Pango attribute ranges with Adwaita's current accent
color in the composer, comments and inbox previews. Text remains literal and
selectable; emails and partial usernames are not parsed as mentions. The header
shows participant avatars, with names and the responsible person's role in
tooltips; board membership and responsibility remain explicit in sharing.

Creation through Campbase records authorship locally. Historical creation can be
recognized conservatively from Deck activity's explicit creation icon and exact
object parameters, independent of translated wording. Missing activity is never
replaced with a guessed creator; server ownership is labeled as ownership.

The notification inbox combines Deck-only Nextcloud notifications, available
Deck activity and unread-comment counts from the board snapshot. Optional OCS
reads have shorter timeouts, a separate error state and a one-minute polling
limit; they cannot clear the card outbox. A separate serialized inbox worker
keeps refresh and deletion ordered without delaying card synchronization. Opening
the inbox shows cached entries immediately and reuses recent feed reads; explicit
refresh bypasses the polling limit. Missing optional services back off for an hour,
and the profile is cached for an hour. Account switching drains old inbox work
before replacing account-bound state. Opening a notification dismisses only that Deck notification;
activity read marks are local. Links navigate to cached boards/cards where
possible and external fallback links are restricted to the account origin.

Notification navigation uses object IDs, rich parameters and Deck deep links,
independently of the displayed language. Comment IDs open their matching page
and scroll to the comment; assignment, due-date, label and sharing notices focus
their corresponding sections. Missing cached destinations trigger a read-only
workspace refresh. Missing comments are reported without guessing or sending
pending edits. Inbox hover covers the entire row, including its delete area.

Workspace reads use at most four parallel GET requests, each with a thread-local
HTTP opener. Active and archived boards/cards are merged into one complete
snapshot; a failed read never replaces the saved workspace with partial data.
Outbox writes and their confirmation reads remain serialized.

Project presentation metadata is shared by the header and sidebar. The header
centers project identity opposite actions and their count/participant-avatar line.
The About description, available languages and source link are on a Details page,
following Adwaita's About-dialog information hierarchy.

Dates preserve an existing timestamp when unedited. Selected dates expose a local
hour/minute row; transport converts to UTC before Deck persists a timezone-less
database value. This avoids a one-hour/two-hour shift from local offsets. Confirmation and
conflict checks compare full instants, including time and equivalent offsets.


Confirmed self-assignments, own comments and self-mentions create local inbox
entries even when Nextcloud suppresses notifications to the acting user. The
assignment entry and outbox completion commit in one SQLite transaction. Comment
entries require a confirmed server ID. Stable event keys prevent duplicate entries
on retries; read marks persist and account changes clear the local inbox.

Column name and device-local color are separate dialogs. Archive visibility uses
a general setting plus explicit per-column overrides. Changing the general
setting atomically clears current and legacy overrides across all boards; new
column exceptions can then be created from their show/hide actions. Overrides
reset on account changes. Archived
cards appear below active cards in a separated, subdued section. Both sections
use the same insertion behavior: dropping in the active area restores an archived
card, while dropping in the archive keeps it archived. Native column menus use a show/hide action.
Restore and trash buttons appear together on hover or keyboard focus, with
restoration using the same offline queue as the card editor. The archive heading
contains the bulk action, scoped to the visible search results.
Their deletion is an explicit online operation with a captured ID list, fresh
archive/column checks, pending-edit guards, confirmation and cancellable progress.
Only confirmed removals leave the cache; partial failures preserve other cards
and unrelated drafts. Authors can delete their own comments through Deck's
author-checked endpoint; failures preserve the displayed comment and composer.

Owned sidebar boards expose a trash button on hover or keyboard focus. Deletion
requires explicit confirmation and a fresh canonical owner check, and refuses
pending edits on that board. Only server-confirmed deletion removes its cached
snapshot and preferences; unrelated boards and drafts remain intact.
Board deletion confirmation initially focuses Cancel. Archived-card and board
trash buttons use the Adwaita destructive style; notification dismissal remains neutral. Column
headers do not display authorship tooltips. The main menu separates pending changes
from the standard Preferences/Shortcuts/About group. Accelerator labels come from
native GMenu attributes and survive live language changes.
Card and account dialogs follow their natural content height,
with scrollable content at the available window size and consistent form margins.

Archive visibility updates only the affected column section, counter and menu;
the current cards and scroll position remain in place. Active card tiles expose
drag and archive controls as siblings of the card button, reserving their space
and sharing the existing move/archive queues. Drag handles preserve pointer
coordinates in the full-card preview. Card editor identity appears as a footer
avatar, with confirmed creation provenance distinguished from Deck ownership.
Assignee avatars and hover controls share the same trailing slot on active and
archived tiles, crossfading over 150 ms without moving the title. Active controls
are ordered archive, then drag. The footer tooltip uses Author for confirmed
creation records and Responsible for Deck ownership. Sharing dialogs use the
same 24 px form margins and adapt their height to the content.

Visible archive sections remain available when empty and accept active-card
drops. Archive destinations use a direct confirmed card update;
retries recognize a move already committed after a lost response. A single drag
commits at most one operation. The header's Assigned to me filter compares the
canonical Nextcloud UID and combines with search and archive visibility. The
filter is grouped beside the board actions, with a person/check icon.

The latest move/archive action records its inverse atomically with the outbox
entry. Undo runs on the same serialized worker: an unsent action with no later
dependent edits is removed locally; attempted or confirmed actions enqueue a
compensating operation. Temporary card IDs are remapped after creation. Undo
changes only position/archive state, preserves other edits and refuses a card
that has moved elsewhere. Account changes clear the saved inverse.

Deck's reorder endpoint rejects archived cards. Moves into an archive use the
ordinary card update endpoint, retaining the archive state when it already
matches. The fresh card supplies all unrelated content, including its explicit
completion value. A durable insertion plan reuses gaps in integer order values
and shifts only colliding neighbours; unaffected cards cause no extra requests.
Changed neighbours are checked against their stack, archive state and original
or already-applied order. Moves back into the active area first use the dedicated
unarchive endpoint, then active-only reorder. Previously saved restore/reorder/
archive checkpoints remain resumable. All paths tolerate a lost write response.

Status-only changes update the header without rebuilding the board. A changed
snapshot waits for an open column menu to close before replacing its widgets.
Mouse/programmatic focus does not hide assignees; hover and visible keyboard
focus reveal the contextual controls. The comment counter sits beside the card
title, keeping the server's raw commentsCount separately from classified totals. Confirmed
comment additions/deletions adjust the cached total; a complete first page can
refresh it, while paginated notification results never replace it with page size.

Workspace rebuilding captures the visible card and its viewport offset before
removing old widgets. Restoration runs after allocation, coalesces consecutive
refreshes and falls back to the previous clamped position if the card disappeared.
Board/filter navigation starts at the top. Wheel, scrollbar and keyboard input
cancel a pending restoration; explicit notification navigation takes precedence.
During dragging the vertical adjustment is held at its initial value, including
while insertion markers change layout. There is no automatic edge scrolling.

Comment reactions use the existing OCS create-comment endpoint with parentId,
an allowlisted emoji and an exact mention of the original author. They remain
ordinary comments on the server, preserving interoperability and native mention
notifications without an administrator-installed extension. Campbase groups only
exact emoji/author replies with a server-confirmed replyTo parent; arbitrary
text remains visible. Other Deck clients count these replies; Campbase excludes
them from its card counter. Each user can remove their
own reaction by deleting their own reply; no other user's reaction is deleted.
A lost write response triggers a read, never an automatic second POST. Reaction
notifications navigate to the parent and highlighted reaction group, even when
the parent appears only as the reply's embedded object on a paginated page.
The selector sits below the author's delete control, with six fixed choices.

Notifications alone attaches a capture-phase click controller to its parent
window while presented. A primary click outside the dialog content closes it
and claims the event, preventing the underlying board from acting on that click.
A child confirmation dialog takes precedence. The controller is removed on close.

Comment classification reads run on a separate two-worker pool, with at most two
pending jobs. Only visible cards with comments are read, with 200 comments per
page. Results are cached for five minutes, invalidated immediately when the raw
total changes, and updated locally after confirmed comment/reaction writes.
Card moves and unrelated lastModified changes do not trigger new count requests.
Repeated status updates coalesce before reading the cache. Failures back off for
one minute; account/board changes and closure cancel remaining pages and discard
old results. A complete page count must match the expected raw total before it
can be cached. Until classification is known, no misleading combined total is
shown. Pagination still cannot provide an atomic server snapshot; a net-zero
change in comment/reaction membership is reconciled by the next cache refresh.
Snapshot, outbox and count projection use one SQLite read transaction, and an
already-read snapshot is passed through to rendering instead of decoded twice.

### Board links and optional communication services

The sharing dialog copies the authenticated Deck web route
`/index.php/apps/deck/board/{boardId}`, preserving a Nextcloud subdirectory.
Copying a link performs no request and does not change an ACL, create a public
share, or invite its recipient. The recipient still needs board access.

Federated board sharing requires Deck 1.18 or newer and the server's federation
configuration; Deck 1.17.x does not support it. This preview's member search
remains limited to users on the same server.

Private and group messaging would require an enabled Nextcloud Talk service.
Campbase does not currently integrate Talk or emulate private messages through
board comments. On managed installations, adding or updating those services is
controlled by the Nextcloud provider.

The support link resolves the current UI language at activation time, including
when the About dialog remains open during a language change.
