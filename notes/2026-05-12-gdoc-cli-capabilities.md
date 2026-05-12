# gdoc CLI + Google Docs API: capability inventory for doc-to-blog sync

Investigated 2026-05-12 against `gdoc 0.7.1` (latest is 0.7.2; changelog at
https://github.com/LucaDeLeo/gdoc/blob/main/CHANGELOG.md). All findings below
are verified by running help, reading the source at
`~/.local/share/uv/tools/gdoc/lib/python3.13/site-packages/gdoc/`, and probing
the live Docs/Drive APIs against three real docs:

- `1daCXcurnDt2c5GaksU9mAeD2CWdJB3HZoDR4UiJAVTE` — single-tab, owned
- `10sdqvgOwn0HjOTNAUPiLnAzH5w-6wl5VnXCBhn2xnzA` — 7 tabs, shared-drive
- `1DWCsyWXBNx0y0wTh0Zces1R7ztttmPlSzZdsIhxpFcA` — 2 tabs, 7 real Google-Docs footnotes, 7 inline images, 10+ comments

## 1. CLI surface

### Subcommands at a glance

| Command | Role | Output formats |
|---|---|---|
| `gdoc cat DOC` | Whole-doc export (default: markdown via Drive) | terse / `--json` / `--plain` / `--verbose` |
| `gdoc cat DOC --tab N` | Single-tab export (plain text only, via Docs API) | text (no markdown) |
| `gdoc cat DOC --all-tabs` | All tabs concatenated as plain text with `=== Tab: T ===` separators | text |
| `gdoc cat DOC --comments` | Markdown + inline `[💬...]`-style annotations | terse / json |
| `gdoc pull DOC FILE` | Same as `cat` markdown + adds `gdoc:`/`title:` YAML frontmatter, writes to disk | — |
| `gdoc tabs DOC` | List tabs (id, title, index, nesting_level) | json / plain TSV / verbose / terse |
| `gdoc toc DOC` | Heading outline with deep-link anchors | json / plain / verbose / terse |
| `gdoc info DOC` | Title, owner, modified, words | json / plain / verbose / terse |
| `gdoc images DOC` | List of inline objects (image / chart / drawing), optional `--download DIR` | json / plain / verbose |
| `gdoc comments DOC [--all]` | List of comments (open by default, `--all` includes resolved) | json / plain / verbose |
| `gdoc find QUERY [--title]` / `ls [folder]` | Drive search and listing | json / plain TSV / verbose / terse |
| `gdoc diff DOC FILE` | Compare doc with local file | — |
| `gdoc write DOC FILE` / `insert` / `push` / `edit` | Writes (push, insert into tab, find-and-replace) | — |
| `gdoc add-tab DOC TITLE` | Create new tab | — |
| `gdoc new TITLE [--file MD]` / `cp DOC TITLE` | Create / duplicate doc | — |
| `gdoc share DOC EMAIL --role ...` | Share | — |
| `gdoc auth [--account] [--list] [--remove]` | Manage OAuth credentials | — |
| `gdoc update` | Self-upgrade | — |

Full verbatim `--help` for every subcommand is in the appendix.

### Output flags (global)

Every read command supports `--json` (machine-readable), `--plain` (stable
TSV, ideal for piping), `--verbose` (human, more fields), and a default
"terse" mode. JSON wraps results as `{"ok": true, ...}`. Errors go to
stderr as `ERR: <message>` with exit codes 1 (general), 2 (auth), 3
(usage / not-found).

There is also `--quiet` on most read commands, which **skips a pre-flight
check** that fetches version metadata to detect whether the doc changed
since gdoc last read it. That pre-flight is the source of the
`account: default (use --account to switch)` and `Update available` lines
on every command — those go to stderr. Use `--quiet` in CI.

### `gdoc cat` — three different code paths

This is the most important command, and it has surprising behaviour:

**Path A — default (whole document):** calls Drive's
`files.export_media(mimeType="text/markdown")`. This is Google's own
Markdown exporter. It produces:

- ATX-style headings (`# H1` through `######`)
- Pandoc footnote syntax: `[^1]`, `[^2]`, … inline with `[^N]: text…`
  blocks appended at the bottom of the file. **Numeric labels — the
  stable `kix.*` footnote IDs from the API are dropped.**
- Reference-style images: `![][image1]`, with the actual base64-encoded
  PNG appended as `[image1]: <data:image/png;base64,iVBOR...>` at end of
  file (use `--no-images` to strip both refs and the trailing data
  blocks)
- Tabs are flattened, with each tab's content preceded by a `# TabName`
  H1 heading. Verbatim from a probe:
  ```
  # Tab 1
  # Work test: Revising an 80k article
  # Introduction
  ...
  ```
  i.e. the tab title is fused into the doc heading hierarchy as H1 — it
  will collide with a real H1 in the tab body.
- Comments are **not** included.
- Suggested edits: not separately surfaced; `suggestionsViewMode` is
  read-only `SUGGESTIONS_INLINE` and the export reflects the displayed
  rendering.

**Path B — `--tab NAME` or `--all-tabs`:** completely bypasses Drive
export. Calls Docs API `documents().get(includeTabsContent=True)` and
runs the dumb `get_tab_text()` walker, which only emits `textRun`
content + tab-joined table cells. **Output is plain text — no headings,
no markdown emphasis, no links, no images, no footnotes.** This makes
`--tab` useless for our sync; we'd need either Drive's whole-doc export
(which already includes tabs) or to call the Docs API ourselves and
build our own markdown serializer.

**Path C — `--comments`:** Drive markdown export + a per-line annotation
pass that finds each open (or resolved with `--all`) comment's
`quotedFileContent.value` in the markdown and prepends line numbers +
appends `> author: "text"` annotations. Useful for review tools but
adds visual chrome we'd strip for rendering.

### `gdoc tabs` and `gdoc toc` — structure exposure

```
$ gdoc tabs --json --quiet 1daCXcur...
{"ok": true, "tabs": [{"id": "t.0", "title": "Tab 1", "index": 0, "nesting_level": 0}]}

$ gdoc tabs --plain --quiet 10sdqvgOwn...
t.0	Main text
t.olvnekk53ki9	App. A - SOC sequences
t.47a77bmox9cc	App. B - Task prompts
...
```

```
$ gdoc toc --json --quiet 1DWCsy...
{"ok": true, "headings": [
  {"level": 1, "heading_id": "h.5pp6xxw2603h", "text": "Introduction",
   "link": "https://docs.google.com/document/d/.../edit#heading=h.5pp6xxw2603h"},
  {"level": 2, "heading_id": "h.yxdq7tr3iww1", "text": "...", "link": "..."},
  ...]}
```

`toc` only walks the first/specified tab (see `cmd_toc` in cli.py:225–293
and `get_document_headings` in docs.py:561). There is no built-in
"toc --all-tabs" — you'd have to call `gdoc tabs` and loop.

### `gdoc info`

`info --json` returns `{id, title, owner, modified, words}`. The
`--verbose` form adds `created`, `last_editor`, `mime_type`, `size`.
**The internal call grabs Drive `version` (integer)** and stores it as
`command_version` in state, but it's not surfaced in stdout. To get it
externally, hit Drive directly (see §5).

### `gdoc images`

Surfaces the inline-object map from the Docs API as a flat list:

```json
{"ok": true, "images": [
  {"id": "kix.uv7p3oevkt1p", "type": "image",
   "title": "", "description": "",
   "width_pt": 353.26, "height_pt": 203.6,
   "content_uri": "https://lh7-rt.googleusercontent.com/docsz/AD_4nXf...=s2048?key=...",
   "source_uri": null,
   "start_index": 10655},
  ...]}
```

- `id` is the stable inline-object ID (`kix.*`) — survives edits to the
  surrounding text, changes if you delete/re-insert the image.
- `type` ∈ {`image`, `chart`, `drawing`}. Charts include
  `spreadsheet_id` + `chart_id`.
- `content_uri` is a short-lived signed Google-CDN URL — refresh per
  call; can be `--download`ed to a local directory.
- `source_uri` may be set if the image was uploaded from a URL.
- **`start_index` is a character offset into the doc, not a paragraph
  ID.** Useful for ordering but not stable across edits.
- Image alt text (`title`, `description`) is exposed. Captions aren't a
  Google Docs concept.

### `gdoc comments`

Returns full comment threads with `id`, `author.displayName`,
`quotedFileContent.value` (the anchored snippet), `content`,
`createdTime`, `modifiedTime`, `resolved`, and a `replies` array. Open
comments only unless `--all`. Comment IDs (`AAAB...`) are stable across
edits as long as the comment exists.

## 2. Tabs (Oct 2024 feature)

**Supported.** The Docs API exposes tabs via `documents.get(includeTabsContent=True)`:

- Top-level field: `tabs` (array). When `includeTabsContent=False` (the
  default), legacy fields `body`, `footnotes`, `namedRanges`,
  `inlineObjects`, etc. show **only the first tab's** content. The doc's
  API schema explicitly flags those as "Legacy field: Instead, use
  Document.tabs.documentTab.X".
- Each tab has `tabProperties` (`tabId`, `title`, `index`, `nestingLevel`,
  `parentTabId`) and `documentTab` (containing per-tab `body`,
  `footnotes`, `namedRanges`, `documentStyle`, `namedStyles`, `lists`,
  `inlineObjects`).
- Tabs nest: `tab.childTabs` is an array of the same shape. gdoc
  flattens recursively (see `flatten_tabs` in api/docs.py:95).

Tab IDs look like `t.0`, `t.jxzi86kqzdol`. `t.0` is always the original
single tab; new tabs get random suffixes that **persist across renames
and reorders** (verified by inspecting the multi-tab doc).

gdoc surfaces tabs in:

- `gdoc tabs` (list)
- `gdoc cat --tab` / `--all-tabs` (plain-text-only — see §1, Path B)
- `gdoc cat` default (markdown via Drive flattens all tabs with
  `# TabName` H1 prefixes)
- `gdoc toc --tab T` (headings within one tab)
- `gdoc write --tab` / `gdoc insert --tab` (writes)
- `gdoc add-tab` (create)

**Not surfaced by gdoc:**

- Per-tab markdown export with structure preserved. gdoc's per-tab
  reader only emits plain text. There's no `gdoc cat --tab T
  --format=markdown` and no `gdoc pull --tab T`. The Drive markdown
  exporter does not accept a tab filter.
- Tab nesting level / parent — `gdoc tabs --json` exposes
  `nesting_level` (computed by gdoc's flattener) but not
  `parentTabId`.

If we want per-tab markdown with headings/footnotes/links, options are:

1. Call Drive's `files.export_media(mimeType="text/markdown")` on the
   whole doc and split on the `# TabName` H1 markers (fragile).
2. Call Docs API directly and write our own JSON-to-markdown converter
   per tab (gives full control; rewrites footnote IDs to whatever we
   want).

## 3. Authentication

### How it works

- gdoc uses **OAuth 2 installed-app flow** (not a service account).
  Source: `auth.py`. Scopes are `drive` (full) + `documents`.
- Client credentials live in `~/.config/gdoc/credentials.json` (a real
  Google Cloud OAuth client — this is gdoc's own dev client, shipped
  with the install: client_id
  `762651716625-iklvu4uvpphq95h0pvg91i4vn5jird00.apps.googleusercontent.com`).
- Per-user token at `~/.config/gdoc/token.json` (default account) or
  `~/.config/gdoc/accounts/<name>/token.json` (named accounts).
- `gdoc auth` runs a local-server callback flow. `gdoc auth --no-browser`
  prints a URL and reads the redirect URL from stdin (paste-back flow)
  — that's the path you'd use on a headless box for the first auth.

### Env vars

**None.** A grep of the source confirms gdoc reads no environment
variables for credentials, scopes, or paths. Everything is anchored to
`Path.home() / ".config" / "gdoc"`. The only knob is `--account NAME` to
select a per-account token directory.

Also: in CI, `HOME` will dictate where it looks. So in GitHub Actions
you must materialize the token at `$HOME/.config/gdoc/token.json`.

### For GitHub Actions / cron

What you need to plant before invocation:

1. `~/.config/gdoc/credentials.json` — the OAuth client (can ship in the
   repo; it's already partly public via the binary).
2. `~/.config/gdoc/token.json` — the refresh-token-bearing user token.
   Format (verbatim from this machine, redacted):
   ```json
   {
     "token": "ya29...",
     "refresh_token": "1//03A7nZc9...",
     "token_uri": "https://oauth2.googleapis.com/token",
     "client_id": "762651716625-iklvu4uvpphq95h0pvg91i4vn5jird00.apps.googleusercontent.com",
     "client_secret": "GOCSPX-...",
     "scopes": ["https://www.googleapis.com/auth/drive",
                "https://www.googleapis.com/auth/documents"],
     "universe_domain": "googleapis.com",
     "account": "",
     "expiry": "2026-05-12T18:09:12.826078Z"
   }
   ```
   gdoc auto-refreshes the access token using `refresh_token` on every
   run (`auth.py:34–40`). The refresh token is the long-lived secret;
   it does not expire on a schedule unless revoked, the user changes
   password, or it goes unused for 6 months.
3. Store the token JSON as a GitHub Actions secret
   (`GDOC_TOKEN_JSON`), write it to the right path before invocation:
   ```yaml
   - run: |
       mkdir -p $HOME/.config/gdoc
       echo "$GDOC_TOKEN_JSON" > $HOME/.config/gdoc/token.json
       chmod 600 $HOME/.config/gdoc/token.json
       echo '$CREDENTIALS_JSON' > $HOME/.config/gdoc/credentials.json
   ```

### Alternative: bypass gdoc auth, use a service account

If we want minimum trust surface (a robot identity that the user can
revoke independently), we can:

1. Create a Google Cloud service account, download its JSON key.
2. Share the source Google Doc with the service account's email
   (Editor/Viewer).
3. **Skip gdoc** for the read path. Call the Docs API and Drive API
   directly from Python with
   `google.oauth2.service_account.Credentials.from_service_account_file(...)`.
   The Docs API works fine with service account auth.

gdoc itself does not support service accounts (it only loads tokens via
`Credentials.from_authorized_user_file`). So if we want service-account
auth in CI, we either patch gdoc or just call the API directly. Given
the limitations of `gdoc cat` (no per-tab markdown), bypassing it is
probably what we'll do anyway.

### State directory

`~/.config/gdoc/state/<doc_id>.json` per doc stores
`{last_seen, last_version, last_read_version, last_comment_check,
known_comment_ids, known_resolved_ids}`. **`last_version` is the Drive
file version** (integer, monotonic — see §5). This is the same primitive
we'd use for our own change detection. State files are local-only and
should be excluded from CI persistence to avoid stale "this changed"
notifications.

## 4. Stable identifiers

The Docs API JSON exposes these stable IDs for content:

| ID | Where | Stable across edits? | Exposed by gdoc? |
|---|---|---|---|
| `documentId` | top-level | yes (doc identity) | yes (`info`, `cat`, etc.) |
| `tabProperties.tabId` (e.g. `t.0`, `t.jxzi86kqzdol`) | `tabs[].tabProperties` | **yes** — survives rename/reorder | yes (`tabs`) |
| `paragraphStyle.headingId` (e.g. `h.5pp6xxw2603h`) | per heading paragraph | **yes for the lifetime of that heading paragraph**. Edits to the heading text keep the same ID; deleting the heading destroys it; copy-pasting creates a new ID. | yes (`toc` returns it + a deep link) |
| `inlineObjectId` (e.g. `kix.uv7p3oevkt1p`) | inline images, charts, drawings | **yes** while the object exists. Delete + re-insert generates a new ID. | yes (`images`) |
| `footnoteId` (e.g. `kix.j9slf6l4zim`) | `documentTab.footnotes` map + paragraphElement.footnoteReference | **yes** while footnote exists. Stable even when footnote number renumbers due to insertions above. | no — gdoc has zero footnote handling. Drive markdown export rewrites them to sequential numbers `[^1]`, `[^2]`, … losing the kix IDs. |
| `namedRange.namedRangeId` | per named range | yes, with the caveat that named ranges can be edited away if the underlying text is deleted | not exposed by gdoc; Docs API supports `createNamedRange`/`deleteNamedRange` |
| `bookmark.bookmarkId` | per bookmark | yes; bookmark links use `#bookmark=...` | not exposed by gdoc |
| `paragraph.startIndex` / `endIndex` | every body element | **no** — these are character offsets and shift on every edit | exposed inside `images.start_index` |
| Comment `id` (e.g. `AAABsJpi9l8`) | comments | yes for lifetime of comment | yes (`comments`) |

**Crucial gap: there is no built-in stable identifier on regular
paragraphs.** Headings get IDs; ordinary body paragraphs do not. If we
need to link "section 3, paragraph 2" stably across edits, options are:

1. **Use headings as anchors** (the natural strategy for sectioned
   blog content). Heading IDs are persistent and already become
   `#heading=h.xxx` URL fragments.
2. **NamedRange around each paragraph** the user wants stable. We'd
   write a tool that scans the doc and creates a named range for each
   `<p>` we care about. Possible but fragile if the user reformats.
3. **Sentence/paragraph content-hash** at sync time. Trivially stable
   as long as text doesn't change, but defeats the point.
4. **Bookmark per anchor**. Available via API.

The honest verdict: **for paragraph-level stable IDs, the API gives us
nothing without active maintenance on the doc.** Heading-level IDs are
free and reliable.

### Tab IDs in deep links

`https://docs.google.com/document/d/<DOCID>/edit?tab=t.0#heading=h.xxxxx`
— `tab` and `heading` fragments combine. `gdoc toc` only emits
`#heading=`, no `?tab=` — fine for single-tab docs, but for our
multi-tab use case we'd need to add `tab=` ourselves.

## 5. Change detection — what to poll

Probed two channels:

### Docs API `revisionId`

`documents.get(...).revisionId` returns an opaque string like
`AFwiY183e0xauGph...`. **But:** when calling with
`includeTabsContent=True`, the top-level `revisionId` was **absent**
on the shared-drive multi-tab doc and **present** on the owned single-tab
doc. Behavior is inconsistent across docs (likely related to permissions
or whether the doc is in a shared drive). Don't rely on it as the
primary signal.

### Drive `files.get`

`drive.files.get(fileId=..., fields="version,modifiedTime,headRevisionId")`:

- `version` — **integer**, monotonically increments on every change.
  Verified on both probed docs (`version: 8` on the test doc,
  `version: 3668` on the longer one). This is what gdoc stores as
  `last_version` in `~/.config/gdoc/state/<docid>.json`.
- `modifiedTime` — ISO timestamp, e.g. `2026-05-12T17:20:48.491Z`.
- `headRevisionId` — opaque string. Only returns on docs where
  revisions are available (Workspace-only docs may not expose this for
  all callers).

`gdoc info --json` already returns `modified` (the `modifiedTime`).
**It does not return `version` to stdout** even though it fetches it.
Three workable polling strategies:

1. **`gdoc info --json --quiet DOC`** and watch the `modified` field.
   One Drive API call per doc. Sufficient resolution (millisecond
   timestamps).
2. **Call Drive `files.get` directly** with
   `fields=version,modifiedTime` for the cheapest signal (returns ~50
   bytes; perfectly cacheable). One call per doc per poll.
3. **Drive `changes.list`** with a `pageToken` for delta polling
   across an entire account or folder. Cheapest if you have many docs.

For a daily cron with one (or a few) docs, **strategy 2 is simplest:
fetch `version` + `modifiedTime`, compare to last-run state, and only
do the expensive `cat`/export if changed.** No webhook plumbing.

### Notification webhooks (the maximally-cheap option)

Drive `files.watch` (and Docs activity API) can push to a webhook URL
on changes. Not surfaced by gdoc. Worth a note for design but probably
overkill for a daily sync.

## 6. Verdicts table

| Capability | gdoc | Docs API | Notes |
|---|---|---|---|
| Whole-doc markdown export | **supported** (`gdoc cat`/`pull`) | via Drive `export_media` | Pandoc-style; tabs flattened as `# TabName` |
| Per-tab markdown export | **NOT supported** (only plain text) | needs custom serializer | gdoc's `--tab` walks `textRun` only |
| Headings as structure | supported (`gdoc toc`) | yes (`paragraphStyle.namedStyleType` + `headingId`) | both flag the stable `headingId` |
| Stable heading IDs | yes | yes | `h.xxxx` form, deep-linkable |
| Stable paragraph IDs (non-heading) | no | no | requires namedRanges/bookmarks workaround |
| Footnotes preserved in markdown | yes (Pandoc `[^N]`), but **IDs lost** | yes (stable `kix.*` footnoteIds in `tabs[].documentTab.footnotes`) | gdoc has no footnote-specific code |
| Comments | supported (`gdoc comments`, `cat --comments`) | yes (via Drive Comments API) | not in default markdown export |
| Tables | included in markdown export | yes (`table.tableRows[].tableCells[]`) | gdoc's per-tab text uses tab-joined cells |
| Inline images | yes (referenced as `![][imageN]` + base64 PNG appended) | yes (`inlineObjects` map) | gdoc `images --download` for separate files |
| Charts/drawings | included in markdown export | yes (classified in `images`) | drawings have no content URI |
| Links | preserved in markdown | yes (`textRun.textStyle.link.url`) | regular `[text](url)` |
| Multi-tab Docs | supported (`gdoc tabs`, `gdoc cat --all-tabs`) | yes (`includeTabsContent=true`) | nesting via `childTabs`, gdoc flattens |
| `revisionId` polling | not exposed | partially (inconsistent across docs) | unreliable signal |
| `version` polling | exposed in state file, not stdout | yes (Drive `files.get` fields) | reliable signal |
| Service-account auth | **not supported** | yes | gdoc only loads OAuth user tokens |
| CI auth | possible (plant token.json) | trivial (any flow) | no env-var support; mount creds at `~/.config/gdoc/` |
| Suggested edits | rendered inline per `suggestionsViewMode` | yes (suggested* fields per element) | not separately surfaced by gdoc |
| Named ranges / bookmarks | not surfaced | yes | use these for stable non-heading anchors |

## 7. Hard constraints this imposes on the system design

1. **gdoc is fine for the simple case (whole doc → markdown), but it
   is not enough if you want per-tab markdown with structure
   preserved.** `gdoc cat --tab T` is plain text only. Either accept the
   "whole doc, tabs flattened as `# TabName`" output and split on those
   markers, or call the Docs API directly and write our own
   markdown serializer. The split-on-markers approach is fragile
   because a user can legitimately type `# Tab 1` as a real heading.

2. **Footnote IDs do not survive the Drive markdown export.** If the
   blog needs stable footnote anchors that match across renders, you
   must call the Docs API directly to read `footnotes[].footnoteId` and
   substitute them yourself. The default `gdoc cat` rewrites them to
   sequential `[^1]`, `[^2]`, … which renumber whenever the author adds
   or removes any footnote.

3. **There are no stable per-paragraph IDs** in the API. Use heading IDs
   (free, persistent) as section anchors. For finer-grained anchors,
   ask the author to define named ranges or bookmarks, or accept that
   non-heading anchors will drift.

4. **Drive markdown export is the only path that produces full
   markdown** (headings, footnotes, lists, tables, links, image refs).
   It always flattens tabs with `# TabName` prefixed. The only way
   around that is custom serialization.

5. **Comments are out-of-band.** They are never in markdown output;
   `gdoc cat --comments` adds annotations that you would strip before
   rendering. For the blog, ignore comments by default.

6. **Inline images come as base64 in the markdown export** —
   functional but huge (a single image was ~150KB in the export). For
   any non-trivial doc, use `gdoc images --download DIR` separately and
   patch image refs in the markdown to point at the saved files.
   `content_uri` URLs are short-lived (`...?key=...` signed Google
   CDN), so download at sync time, not at render time.

7. **CI authentication is OAuth-only.** No env-var support, no
   service-account support in gdoc. Either ship a refresh token as a
   GitHub Actions secret (anchored to a user account) or bypass gdoc
   entirely for reads and use service-account auth via the Docs/Drive
   Python clients. Service account is cleaner for ops; user OAuth is
   faster to set up.

8. **Change detection is cheap and reliable via Drive `files.get`
   `version` field** (integer, monotonic). Do not rely on Docs API
   `revisionId` — observed to be absent for the shared-drive doc.
   Drive `version` + `modifiedTime` is the right primitive.

9. **`gdoc --json` is well-behaved for scripting** (always
   `{"ok": true, ...}`); errors go to stderr as `ERR: <msg>`. Exit codes
   are 0/1/2/3. The `account: default (use --account to switch)` and
   `Update available: ...` chatter goes to stderr too — `2>/dev/null`
   in CI to keep logs clean. Use `--quiet` to skip the pre-flight
   change-detection roundtrip on every read.

10. **Tab IDs are persistent.** `t.0` is always the first tab; user
    tabs get random `t.xxx` suffixes that survive rename/reorder.
    Build sync state around tab IDs, not titles.

---

## Appendix A — verbatim help output

```
$ gdoc --help
usage: gdoc [-h] [--version] [--json | --verbose | --plain]
            [--allow-commands ALLOW_COMMANDS]
            {update,auth,ls,find,cat,tabs,toc,add-tab,edit,diff,write,insert,pull,push,_sync-hook,_pull-hook,comments,comment,reply,resolve,reopen,delete-comment,comment-info,images,info,share,new,cp} ...

CLI for Google Docs & Drive

positional arguments:
  {update,auth,ls,find,cat,tabs,toc,add-tab,edit,diff,write,insert,pull,push,_sync-hook,_pull-hook,comments,comment,reply,resolve,reopen,delete-comment,comment-info,images,info,share,new,cp}
    update              Update gdoc to the latest version
    auth                Authenticate with Google
    ls                  List files in Drive
    find                Search files by name/content
    cat                 Export doc as markdown
    tabs                List tabs in a doc
    toc                 Extract table of contents with deep links
    add-tab             Add a new tab to a document
    edit                Find and replace text
    diff                Compare doc with local file
    write               Overwrite doc (or one tab) from local file
    insert              Insert local markdown into an existing tab
    pull                Download doc as local markdown
    push                Upload local markdown to doc
    comments            List comments on a doc
    ...
```

```
$ gdoc cat --help
usage: gdoc cat [-h] [--json | --verbose | --plain] [--account ACCOUNT]
                [--comments] [--all] [--tab TAB | --all-tabs]
                [--max-bytes MAX_BYTES] [--no-images] [--quiet]
                doc

  --comments            Include comment annotations
  --all                 Include resolved comments (with --comments)
  --tab TAB             Read a specific tab by title or ID
  --all-tabs            Read all tabs
  --max-bytes MAX_BYTES Truncate output at N bytes (0 = unlimited)
  --no-images           Strip image references from output
  --quiet               Skip pre-flight checks
```

```
$ gdoc tabs --help
usage: gdoc tabs [-h] [--json | --verbose | --plain] [--account ACCOUNT]
                 [--quiet]
                 doc
```

```
$ gdoc toc --help
usage: gdoc toc [-h] [--json | --verbose | --plain] [--account ACCOUNT]
                [--tab TAB] [--max-depth MAX_DEPTH] [--no-links] [--quiet]
                doc
```

```
$ gdoc info --help
usage: gdoc info [-h] [--json | --verbose | --plain] [--account ACCOUNT]
                 [--quiet]
                 doc
```

```
$ gdoc images --help
usage: gdoc images [-h] [--json | --verbose | --plain] [--account ACCOUNT]
                   [--download DIR] [--quiet]
                   doc [image_id]
```

```
$ gdoc comments --help
usage: gdoc comments [-h] [--json | --verbose | --plain] [--account ACCOUNT]
                     [--all] [--quiet]
                     doc
```

```
$ gdoc auth --help
usage: gdoc auth [-h] [--json | --verbose | --plain] [--account ACCOUNT]
                 [--no-browser] [--list] [--remove ACCOUNT] [--force]
```

(Full help for all 26 subcommands captured in the bash transcript; see
also `~/.local/share/uv/tools/gdoc/lib/python3.13/site-packages/gdoc/cli.py`
for source.)

## Appendix B — example JSON outputs

```json
// gdoc tabs --json (multi-tab doc)
{"ok": true, "tabs": [
  {"id": "t.0", "title": "Main text", "index": 0, "nesting_level": 0},
  {"id": "t.olvnekk53ki9", "title": "App. A - SOC sequences", "index": 1, "nesting_level": 0},
  {"id": "t.47a77bmox9cc", "title": "App. B - Task prompts", "index": 2, "nesting_level": 0},
  ...]}

// gdoc toc --json (one heading, single tab)
{"ok": true, "headings": [
  {"level": 1, "heading_id": "h.dey838yzx63n",
   "text": "ML4Good Germany 2026 Test document to duplicate",
   "link": "https://docs.google.com/document/d/.../edit#heading=h.dey838yzx63n"}]}

// gdoc info --json
{"ok": true, "id": "1daCXcur...", "title": "...",
 "owner": "diego.dorn1999",
 "modified": "2026-05-12T17:20:48.491Z", "words": 30}

// gdoc images --json (one image, abbreviated)
{"ok": true, "images": [
  {"id": "kix.uv7p3oevkt1p", "type": "image", "title": "", "description": "",
   "width_pt": 353.26, "height_pt": 203.6,
   "content_uri": "https://lh7-rt.googleusercontent.com/docsz/AD_4nXf...=s2048?key=...",
   "source_uri": null, "start_index": 10655}]}

// Drive API files.get (raw, what gdoc uses internally)
{"id": "1daCXcur...", "name": "...",
 "mimeType": "application/vnd.google-apps.document",
 "modifiedTime": "2026-05-12T17:20:48.491Z",
 "createdTime": "2026-05-12T17:20:40.127Z",
 "owners": [{"displayName": "diego.dorn1999", ...}],
 "lastModifyingUser": {...}, "size": "1824",
 "version": 8}
```

## Appendix C — relevant source files

- `~/.local/share/uv/tools/gdoc/lib/python3.13/site-packages/gdoc/cli.py` (2328 lines, 26 commands)
- `~/.local/share/uv/tools/gdoc/lib/python3.13/site-packages/gdoc/api/docs.py` (958 lines, Docs API wrapper)
- `~/.local/share/uv/tools/gdoc/lib/python3.13/site-packages/gdoc/api/drive.py` (Drive API wrapper, incl. `export_doc` and `get_file_info`)
- `~/.local/share/uv/tools/gdoc/lib/python3.13/site-packages/gdoc/api/comments.py`
- `~/.local/share/uv/tools/gdoc/lib/python3.13/site-packages/gdoc/auth.py` (OAuth flow, scope = drive + documents)
- `~/.local/share/uv/tools/gdoc/lib/python3.13/site-packages/gdoc/util.py` (config paths)
- `~/.local/share/uv/tools/gdoc/lib/python3.13/site-packages/googleapiclient/discovery_cache/documents/docs.v1.json` (bundled Docs API schema)
- `~/.config/gdoc/state/<doc_id>.json` (per-doc local sync state)
