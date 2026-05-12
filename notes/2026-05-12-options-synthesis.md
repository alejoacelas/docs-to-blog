# Docs-to-Blog System: Option Bundles

**Synthesis of four research threads** (gdoc capabilities, stack survey, styling architecture, automation model). See `notes/` for the underlying reports.

This document does three things:
1. Lists **constraints discovered** that eliminate certain approaches.
2. Lists **what's locked in** as the shared foundation across all bundles.
3. Presents **7 concrete bundles** spanning the design space, with explicit trade-offs.

---

## 1. Discarded by research

These are off the table:

| Discarded | Reason |
|---|---|
| **Next.js + MDX** | MDX trips on stray `<` and `{` in generated markdown — wrong tool for non-authored content. |
| **Hugo** | Goldmark runs in Go; no JS plugin host for the sidecar-styling plugin we need. |
| **Docusaurus / MkDocs** | Docs-shaped routing, MDX-only paths. Fighting the framework to do a "blog that grows." |
| **Cloudflare Workers / Vercel Cron as the *runner*** | V8 sandbox can't exec the `gdoc` Python binary or run `git`. (Still usable as v2 webhook receivers.) |
| **`anthropics/claude-code-action` on `schedule:`** | Open p1 bug (Issue #814): OIDC token exchange 401s on scheduled triggers. Use the `claude` CLI directly instead. |
| **`gdoc cat --tab T` for content export** | Tab-scoped export goes through a different code path that emits plain text only — no markdown structure. Only the whole-doc export gives proper markdown. |
| **Content-hash-only anchoring** | Breaks on every typo fix. Useful as an integrity probe, not as the primary anchor. |
| **Per-sentence styling for v1** | Sentence boundaries are too volatile to anchor cheaply. Defer to v2. |
| **Drive `changes.watch` webhooks for v1** | Real-time push notifications work, but daily cron is enough for now. Overengineering. |
| **Service-account auth for gdoc** | gdoc CLI bundles its own OAuth client, doesn't read service-account JSON. Could be added by bypassing gdoc, but unnecessary — refresh-token-in-secret works. |
| **Pure-LLM "regenerate everything daily"** | Non-deterministic, hard to debug, expensive, results drift day-to-day. Not what the user wants. |

## 2. Locked in (shared foundation)

Every bundle below uses these:

- **Source-of-truth doc:** lives in Google Drive. Pulled with `gdoc` CLI (`gdoc cat <url>`) by default — falls back to direct Docs API only if a bundle specifically needs footnote-ID stability or paragraph-level access.
- **Change detection:** Drive `files.get` `version` integer field. Monotonic, cheap to poll. Sync only when bumped.
- **Footnote handling:** `gdoc cat` markdown export → Pandoc-style `[^n]`. Stable across runs *only if* footnotes aren't reordered; for true cross-day stability, call Docs API directly and serialize ourselves. (Defer this — `gdoc` is fine for v1.)
- **Runner:** GitHub Actions on `schedule: "3 9 * * *"` (configurable). Token planted from a `GDOC_TOKEN_JSON_B64` secret. The job pulls, diffs, optionally invokes `claude -p --bare ...`, commits, and pushes.
- **Site build & deploy:** GitHub Pages or Cloudflare Pages, triggered by the commit. Static-site assumption — no runtime rendering needed.
- **Sidecar styling lives in repo** as `styles/<doc-slug>.{yaml,json,css}` — version-controlled, PR-reviewable.
- **Custom remark plugin** (~30 lines) reads the sidecar at build time and attaches `data.hProperties.className` to matching paragraphs. Stack-portable.
- **No required body markup.** Bundles that allow it treat it as an escape hatch, not the default.
- **Per-paragraph styling only in v1.** Per-sentence deferred.

---

## 3. The seven bundles

Bundles are ordered roughly from "least magic" to "most magic." Pick one — or pick two to prototype in parallel and compare.

### Bundle 1 — **Heading+Ordinal Sidecar** (MVP, no LLM)

**Stack:** Astro v5, plain Node fallback.
**Anchoring:** `{heading-slug}__p{n}` — e.g. `introduction__p3` = third paragraph after `## Introduction`.
**Styling control surface:** YAML file in repo only. No `x styling` tab.
**Pipeline LLM:** none.

**How the author works:**
- Edits the Google Doc freely.
- To style a paragraph: edits `styles/main.yaml` in the repo:
  ```yaml
  introduction__p3:
    class: callout
    bg: yellow
  ```
- CSS for `callout` lives in the repo's stylesheet.

**Trade-off:** Simplest possible. But inserting a paragraph in the middle of a section silently shifts every later ordinal — yesterday's `__p3` styling now hits yesterday's `__p4`. Author must re-check after big inserts.

**Effort to build:** ~1 day.

---

### Bundle 2 — **Fuzzy Sidecar** (Hypothes.is-style anchors, no LLM)

**Stack:** Astro v5.
**Anchoring:** Multi-selector — `{quote: "first 30 chars...last 30 chars", heading: "Introduction", ordinal: 3, hash: "sha1"}`. At build time, fall through selectors in order; report orphans.
**Styling control surface:** YAML in repo.
**Pipeline LLM:** none.

**How the author works:** same as Bundle 1, but the YAML entries store a quoted snippet alongside the heading/ordinal. Build script fuzzy-matches the snippet against the new markdown using `diff-match-patch`.

**Trade-off:** Robust against typo fixes, small edits, reorderings within a section. Verbose sidecar (~200 chars per anchor). Still breaks on paragraph rewrites — but the build reports "orphaned anchor: ..." instead of silently mis-applying styling.

**Effort to build:** ~2-3 days.

---

### Bundle 3 — **Fuzzy Sidecar + Claude PR-on-Orphan** (recommended v1 per styling agent)

**= Bundle 2 + a `claude -p` step that runs only when fuzzy matching produces orphans.**

When the daily sync sees an orphan anchor:
- `claude -p --bare --max-turns 5 "Reconcile <orphan-anchor> against new markdown. Update styles/main.yaml."`
- Result is committed to a branch, opens a PR for human review.
- Auto-merge on high-confidence diffs (optional).

**Trade-off:** All of Bundle 2's benefits plus self-healing on edits. Costs ~$0.05–0.50/day in Anthropic API depending on doc size and how often orphans appear. Human stays in the loop via PR review.

**Effort:** Bundle 2 effort + 1 day to wire `claude` invocation + PR opening.

**This is the styling-architecture agent's top recommendation.**

---

### Bundle 4 — **`x styling` Doc Tab + Tag Markup**

**Stack:** Astro v5.
**Anchoring:** in-body markers `[callout]...[/callout]` injected by the author.
**Styling control surface:** A second tab in the Google Doc titled `x styling` (lowercase). Contains:
  - A free-form prose section "Global style for this page"
  - Tag definitions: `callout: yellow background, italic text, smaller font`
**Pipeline LLM:** Claude at build time turns the prose styling tab into CSS rules + Astro components.

**How the author works:**
- In doc body: wraps `[callout]Important note here[/callout]` around paragraphs that should be styled.
- In `x styling` tab: defines what each tag means.
- Generated CSS gets committed to repo.

**Trade-off:** This is the option the user proposed in chat — even though they said "no body markup," they then suggested `[tag]` markers as a viable approach. Most "Notion-like" UX. Single source of truth (the doc). But requires Claude to interpret prose styling and generate CSS — least deterministic of all bundles. Author can break the site by writing ambiguous tag descriptions.

**Effort:** ~4-5 days.

---

### Bundle 5 — **Comments-as-Channel** (zero body markup)

**Stack:** Astro v5. **Source pull:** direct Docs API (not gdoc CLI — needed to read comments).
**Anchoring:** Google Docs comments. Author selects a paragraph, comments `style: callout` (or `class: callout-yellow`).
**Styling control surface:** comments in doc + `styles.yaml` in repo defining what `callout` means.
**Pipeline LLM:** none.

**How the author works:**
- Doc body stays 100% clean prose.
- To style a paragraph: highlight it → Insert comment → type `style: callout`.
- Comments have stable IDs and persistent anchors to text ranges via the Docs API.

**Trade-off:** Truly zero body markup. The comment ID is the most robust anchor available. But comments are *visible* in the editing UI (margin bubbles), can be cluttery on a heavily-styled page. Author needs to remember not to "resolve" the comments. Requires bypassing gdoc CLI to read comment metadata via Drive `comments.list`.

**Effort:** ~3 days.

---

### Bundle 6 — **Bookmarks-as-Anchors** (zero body markup, invisible)

**Stack:** Astro v5. **Source pull:** direct Docs API.
**Anchoring:** Google Docs bookmarks (Insert → Bookmark). Each bookmark has a stable `id`.
**Styling control surface:** repo YAML mapping bookmark ID → class.
**Pipeline LLM:** none.

**How the author works:**
- In doc: place cursor in paragraph → Insert → Bookmark. Tiny ribbon icon appears.
- In repo: `bookmark-id-abc123 → class: callout`
- Body reads 100% clean. Ribbon icon is the only UI artifact.

**Trade-off:** Stable IDs the API exposes natively. Closest to "invisible markup that survives all edits." But bookmarks are a niche Docs feature; the UI is clunky (Insert menu, no keyboard shortcut, no easy way to list bookmarks). YAML uses opaque IDs unless we maintain a human-name mapping.

**Effort:** ~3 days.

---

### Bundle 7 — **Custom Named Paragraph Styles** (zero body markup, invisible-ish)

**Stack:** Astro v5. **Source pull:** direct Docs API.
**Anchoring:** Google Docs custom paragraph styles. The author creates a custom style called "callout" via Format → Paragraph styles → Custom; applies it to a paragraph.
**Styling control surface:** repo CSS mapping style name → CSS rules.
**Pipeline LLM:** none.

**How the author works:**
- In doc: select paragraph → assign custom paragraph style "Callout" (one click after setup).
- Repo: `.callout { ... }`
- Body reads as the styled paragraph already (yellow bg etc. in the doc itself).

**Trade-off:** Closest match between doc-as-WYSIWYG and final site. Author sees styled doc, gets styled site. But custom paragraph styles in Google Docs are awkward (Heading 1–6 are reserved; "Title" and "Subtitle" exist; custom ones via the Styles dropdown are limited and not first-class). Some users find it confusing. The API exposes `namedStyleType` for built-in styles only; custom styling is per-run formatting that we'd need to fingerprint.

**Effort:** ~4 days — most fragile mapping layer.

---

## 4. Side-by-side

| # | Anchoring | Body markup | Sidecar | LLM in pipeline | Robustness | UX | Effort |
|---|---|---|---|---|---|---|---|
| 1 | heading+ordinal | none | YAML | no | low | simple | 1d |
| 2 | fuzzy multi-selector | none | YAML | no | medium-high | simple | 2-3d |
| 3 | fuzzy + Claude orphan-PR | none | YAML | only on orphan | high | self-healing | 3-4d |
| 4 | inline `[tag]` | yes (minimal) | doc-driven, generated | yes (every build) | low (depends on LLM) | Notion-like | 4-5d |
| 5 | doc comments | none | YAML + comments | no | high | clean but visible bubbles | 3d |
| 6 | doc bookmarks | none (ribbon icon) | YAML | no | high | invisible but niche UI | 3d |
| 7 | doc custom styles | none (visible styling) | CSS | no | medium | WYSIWYG | 4d |

## 5. Recommendation

If you want **one bundle to implement first**, my pick is **Bundle 3 (Fuzzy Sidecar + Claude PR-on-Orphan)**. It's the only one that:
- Satisfies "zero required body markup"
- Stays deterministic on the common case (fuzzy match finds the paragraph)
- Has a real self-healing story for the hard case (Claude reconciles in a PR)
- Has a clear build-from-Bundle-2 stepping stone
- Doesn't bet the project on Google Docs UI features (bookmarks, custom styles, comments) the author may dislike

If you want **multiple bundles in parallel** to compare, the most interesting trio is:
- **Bundle 3** (fuzzy + Claude) — the safe pick
- **Bundle 4** (`x styling` tab + tag markup) — the most Notion-like, your original instinct
- **Bundle 5** (comments-as-channel) — the cleanest zero-markup option

Bundles 1, 2, 6, 7 are useful as fallback positions or research curiosities, but I wouldn't lead with them.

---

## 6. Open questions for you before implementation

1. **One doc per page, or many sections per doc?** Affects sidecar file layout.
2. **Who owns the doc — just you, or shared with editors?** Affects whether the "comments" or "bookmarks" interfaces work (collaborators may not understand them).
3. **Is the daily cron timing OK, or do you want "rebuild when I save the doc" via Drive webhooks?** v1 is daily; webhooks are v2.
4. **For Bundle 3: auto-merge Claude's reconciliation PRs, or always review?** Affects how trustworthy the system needs to be on day one.
5. **For Bundle 4: are you OK with the doc body containing `[callout]...[/callout]` markers?** You said "no markup" but also "maybe minimal tag markup is OK." This is the contradiction to resolve.
