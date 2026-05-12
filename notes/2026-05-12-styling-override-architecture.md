# Styling Override Architecture — Design Space Map

**Project:** docs-to-blog (Google Doc -> daily pipeline -> static site)
**Question:** Where does the styling live, and how is it anchored to prose that the author keeps editing freely?
**Constraint:** Doc body should read as plain prose. Styling source-of-truth lives in the repo.

---

## 0. The core tension

The author wants two things that pull in opposite directions:

1. **Prose stays clean.** No `[callout]...[/callout]`, no HTML, no `{.class}` attributes, no "magic" punctuation. The doc reads like a doc.
2. **Styling is precise and durable.** "This paragraph is a yellow callout. This sentence is a pull-quote. This list renders as cards." And those overrides survive the author rewriting the paragraph tomorrow.

Every concrete design has to pick a position on **four mostly-independent axes**:

| Axis | What it decides | Range of options |
|---|---|---|
| **A. Anchoring** | How a style override "finds" the right paragraph after edits | content hash <-> heading+ordinal <-> fuzzy quote <-> LLM-assigned ID <-> Google Docs object ID |
| **B. Markup-in-body** | What the author types in the doc | none (zero) <-> invisible (bookmarks/comments) <-> minimal (`[tag]...[/tag]`) <-> rich (full inline classes) |
| **C. Sidecar format** | Where/how styling is written in the repo | YAML map <-> JSON with metadata <-> CSS with attr selectors <-> JSX/Astro components <-> rules DSL |
| **D. Reconciliation** | What keeps anchors aligned with the doc over time | none (deterministic only) <-> heuristic re-match <-> LLM diff-reconciler <-> human-in-the-loop PR |

The product surface is then **A x B x C x D**, ~5x4x5x4 = ~400 combinations. Most are nonsensical; ~5 are coherent. The rest of this doc maps it.

---

## 1. Anchoring: how a style finds its paragraph

This is the hardest sub-problem. It's the one Hypothes.is built a whole sub-field around ("fuzzy anchoring" - they ship three selectors at once and fall through them in order of reliability). [1]

### A1. Google Docs object IDs (`startIndex`/`endIndex` / element IDs)

The Docs API exposes structural element indices and, for some elements (named ranges, bookmarks, headings via tab IDs), stable internal IDs. [2]

- **+** Truly stable across pure edits to *other* paragraphs.
- **+** Free, no LLM needed.
- **-** `startIndex`/`endIndex` are **byte offsets**, not IDs - they shift on every prior edit, so they're only stable within a single export run, not across days.
- **-** Paragraphs themselves don't have user-stable IDs. Only `NamedRange`s and a few inline objects do.
- **-** Couples the repo to Docs-internals - if the author ever migrates off Docs, every anchor is junk.

Verdict: too volatile to be the *primary* anchor, but useful as a **secondary** anchor inside a single sync (e.g., "the 4th paragraph under the heading with element ID `h.abc123`").

### A2. Heading-slug + ordinal

`intro/3` = "the 3rd paragraph after the heading slugged `intro`". This is what most static-site generators effectively do with anchors.

- **+** Human-readable. The author can guess what an anchor points to.
- **+** Survives edits inside other sections completely.
- **-** Breaks when the author reorders paragraphs within a section or renames a heading.
- **-** Heading renames are common (the headline is the part people fiddle with most).
- **Mitigation:** treat heading slug as "slug at creation time, frozen", store renames in a slug-history file.

### A3. Content hash (sha1 of normalized paragraph text)

- **+** Zero ambiguity. The hash *is* the content.
- **-** Any edit - even a typo fix - invalidates the anchor. Useless as a *long-lived* identifier.
- **+** Excellent as a **verification** check: "was this paragraph edited since the last sync?"

Verdict: not an anchor on its own. A great **integrity probe** alongside another anchor.

### A4. Fuzzy quote selector (Hypothes.is-style)

Store `{prefix: "...", exact: "...", suffix: "..."}`. On reconciliation, run diff-match-patch fuzzy search. [1][3]

- **+** Robust to small edits anywhere in the doc.
- **+** Standardized (W3C Web Annotation Data Model).
- **+** Human-readable in the sidecar - you literally see the quoted prose.
- **-** Can be ambiguous if the same phrase appears twice.
- **-** Breaks when the paragraph is rewritten substantially.
- **-** Sidecar files get verbose (storing 200 chars of context per anchor).

Verdict: strongest *primary* anchor for prose-that-evolves. The closest match to "how a human would re-find that paragraph if it moved."

### A5. LLM-assigned semantic IDs (e.g., `claim-foundations-of-trust`)

Claude assigns a stable slug to each paragraph based on its meaning, not its position or text.

- **+** Most human-readable of all. The slug describes the paragraph's *role*.
- **+** Survives rewrites - if the paragraph still argues the same thing, the slug still applies.
- **-** Non-deterministic. Two runs can produce different slugs unless carefully prompted.
- **-** Needs reconciliation: if the author splits one paragraph into two, who gets the slug?
- **-** Adds an LLM call to every sync (cost + flake risk).

Verdict: viable but only when paired with deterministic fallback anchors (hash + ordinal). The LLM should *propose* slugs, but a deterministic system should hold them.

### A6. Invisible markup the API can see but the reader can't

Google Docs supports two "invisible" anchors that don't show as visible markup in the doc body:
- **Bookmarks** - point to a position, have a stable `id`. Author sees a small ribbon icon.
- **Comments / suggestions** - have a stable `id`, visible in margin but not in printable text.
- **Named ranges** - API-only, completely invisible to author.

- **+** Stable IDs that survive arbitrary edits to surrounding prose.
- **+** Bookmarks are author-creatable in the UI (Insert -> Bookmark) - they could *manually* tag paragraphs they care about, without polluting the body text.
- **-** Bookmarks are noisy in the editing UI; not all authors will use them.
- **-** Named ranges can only be created via the API, not the UI - so the author can't author them.

Verdict: a sleeper option. **Bookmarks as anchors** is the closest thing to "invisible markup" - the body reads clean, the author has a deliberate gesture for "this paragraph matters."

### Summary table

| Strategy | Stable across body edits? | Stable across rewrites? | Deterministic? | Author-friendly? |
|---|---|---|---|---|
| API object IDs | partial | partial | yes | no (invisible) |
| heading+ordinal | within section | no | yes | yes |
| content hash | no | no | yes | n/a |
| fuzzy quote | yes (small edits) | partial | yes | yes (you see the quote) |
| LLM semantic ID | yes | yes | no | yes |
| bookmarks | yes | yes | yes | partial |

**Composite recommendation:** carry **multiple selectors per anchor**, fall through. Primary: fuzzy quote OR bookmark ID. Secondary: heading-slug + ordinal. Verification: content hash. This is Hypothes.is's exact pattern, and it's the right one. [1]

---

## 2. Markup-in-body: what does the author type?

Ordered from purest to most explicit:

### B1. Zero markup (Option A in brief)

The author writes prose. An LLM in the sync pipeline *infers* which paragraphs should be callouts, pull-quotes, etc., guided by a `styling tab` prompt.

- **+** Honors the constraint maximally. Doc is unblemished prose.
- **-** Non-deterministic - same prose can be styled differently across runs.
- **-** Forces an LLM on the critical path of every build.
- **-** "Surprise" risk: the model decides a paragraph is a callout when the author didn't mean it.
- **Mitigation:** cache LLM decisions in the sidecar so a re-run with no doc edits is a no-op. The LLM only re-evaluates paragraphs whose hash changed.

### B2. Invisible-but-deliberate (bookmarks / comments)

Author hits `Insert -> Bookmark` (or attaches a comment like `style: callout`) to tag a paragraph. The doc body still reads clean - bookmarks render as a tiny ribbon icon in edit mode, invisible in print/export.

- **+** No body-text pollution.
- **+** Deterministic - the tag is explicit.
- **-** Slightly clunky UX (3-4 clicks to add a bookmark).
- **-** Google Docs comments are visible in the margin while editing (not in body, but on screen).

This is **the most interesting middle path** - it satisfies "no markup in body" literally, while keeping the system deterministic.

### B3. Minimal inline tags (Option B in brief)

`[callout]This paragraph is a callout.[/callout]` or `{::callout}` or `:::callout` (CommonMark directive syntax).

- **+** Fully deterministic, easy to grep, easy to author.
- **+** No LLM needed for tagging - only for content.
- **-** Violates the stated constraint ("doc should read as plain prose").
- **-** Tags are unstyled in the Google Doc - they look like literal text to the author.

The author already half-rejected this. But note: **the CommonMark `::: directive :::` block fences are the de-facto standard** for "structured semantic blocks in markdown without HTML." If they ever soften the constraint, this is where to land.

### B4. Convention-based ("rules-based") styling

No explicit tags. Instead, the author uses Docs-native styles (Heading 4, blockquote, "Title" style) and the pipeline maps those to CSS classes. Plus regex/structure rules:

- Any paragraph starting with `>` -> `class="pull-quote"`
- Any paragraph in italic and short (< 200 chars) standalone -> `class="aphorism"`
- Any heading 4 -> `class="callout-title"`, and the following paragraph -> `class="callout-body"`

- **+** Zero LLM, fully deterministic, fully prose-readable.
- **+** Reuses idioms the author already has (blockquotes etc.).
- **-** Limited vocabulary - hard to express "this *specific* paragraph is special."
- **-** Author has to learn the rules.

### B5. Rich inline (full HTML/MDX in body)

Strongly rejected. Mentioned only for completeness.

---

## 3. Sidecar styling formats

Where does the styling actually live in the repo?

### C1. YAML map

```yaml
# styles.yml
anchors:
  - id: intro-3
    quote: "We had been told for years..."
    class: callout
    variant: warning
  - id: chapter-2-aphorism
    quote: "The map is not the territory."
    class: pull-quote
```

- **+** Trivially Claude-editable, human-skimmable, supports comments.
- **+** Easy to diff in PRs.
- **-** Doesn't *do* anything by itself - needs a build step to apply.

### C2. JSON with style metadata

Same as YAML, less human-friendly, more tool-friendly. Use this if you need to consume the sidecar from many tools.

### C3. CSS with attribute selectors

The build step injects `data-id="intro-3"` onto every `<p>`. Then:

```css
/* styles.css */
[data-id="intro-3"] { background: lemonchiffon; font-style: italic; }
[data-id="chapter-2-aphorism"] { font-size: 1.4rem; ... }
```

- **+** Styling sidecar *is* CSS - no transform layer. [4]
- **+** Designers feel at home; no DSL to learn.
- **-** CSS file grows unboundedly (one rule per styled paragraph forever).
- **-** Harder to express non-visual semantics (e.g., "this is a footnote callout - render with a custom component").

### C4. TSX / Astro components keyed by ID

```tsx
// overrides/intro-3.tsx
export default ({children}) => <Callout variant="warning">{children}</Callout>;
```

Build step: if `overrides/<id>.tsx` exists, wrap that paragraph in the component.

- **+** Maximal expressive power. Any component, any layout.
- **+** Type-checked.
- **-** Heavy for "make this paragraph yellow."
- **-** One file per styled paragraph = directory bloat.
- **Mitigation:** allow a single `overrides.tsx` that exports a map of `id -> component`.

### C5. Rules DSL (one file)

```yaml
# rules.yml
- when: starts_with(">")
  class: pull-quote
- when: in_section("intro") and length < 200
  class: aphorism
- when: id == "chapter-2-aphorism"
  class: pull-quote
```

- **+** Combines per-paragraph overrides with reusable patterns.
- **+** One file to read for "how does this site look?".
- **-** Needs a small expression evaluator. Yet another DSL.

### Recommendation

For v1: **C1 (YAML map) + small CSS file for class definitions** is the sweet spot. The YAML holds the *mapping* (anchor -> class name), the CSS holds the *visual definition* (class -> appearance). They're decoupled, both diff well, and Claude can edit either.

Reserve C4 (TSX components) for the rare "this paragraph needs a real component" case.

---

## 4. The "styling tab" interface

### Does the Google Docs API expose tabs?

**Yes, fully, since Oct 2024.** [2] Key facts:
- `documents.get` accepts `includeTabsContent=true` to return all tabs (default is false, returns only first tab merged as legacy `document.body`).
- Tabs are accessed via `document.tabs[i].documentTab.body` instead of `document.body`.
- Each tab has its own `tabId` (stable across edits) and title.
- Tabs nest up to 3 levels deep via `tab.childTabs`.
- Apps Script and the REST API both support this.

So a sibling `x styling` tab inside the same doc is **first-class supported**.

### What should the styling tab contain?

Three sub-options:

**T1. Free-form prompt.** A paragraph of English: "Keep it calm and bookish. Pull-quote the aphorisms. Yellow background on warnings. Use a serif display font for chapter titles." Fed to Claude during sync.
- **+** Frictionless to author. Most "designer talking to designer" feel.
- **-** Non-deterministic. The LLM has to interpret it every run.

**T2. Structured tag dictionary.**
```
callout: yellow background, italic text, narrow column, small icon left
aphorism: large serif, centered, lots of whitespace
warning: red border, bold first sentence
```
Each entry becomes a CSS class definition (translated by Claude on first sync, then cached as actual CSS).
- **+** Self-documenting "styleguide" lives in the doc.
- **+** Stable - the *names* are deterministic, only the *interpretation* is LLM-driven.
- **-** Requires authoring discipline.

**T3. Hybrid.** Top section: free-form prompt for overall tone. Below: a list of named tags with English descriptions. Below that: a list of `anchor -> tag` decisions made by Claude on the last run, editable by the author (so the author can override "no, this isn't a callout").
- **+** Best of both. Author can correct mistakes in plain English.
- **-** Most complex to implement.

### If tabs didn't work (they do, but for completeness)

Alternatives:
- A second Google Doc, linked from the main doc.
- A fenced code block at the top of the main doc (` ```yaml ... ``` `) - the pipeline strips it.
- A `STYLING.md` in the repo, edited by the author directly (loses the "I never leave Google Docs" property).
- A footer section in the main doc below a sentinel like `---STYLING---` (pipeline truncates).

The Docs Tabs API makes all of these worse alternatives.

---

## 5. Per-sentence styling

Strictly harder than per-paragraph. Options:

### S1. Inline markers in body (rejected per constraint)

`{italic-emphasis}` or similar. Cleanly maps to `<span>` but pollutes body.

### S2. LLM splits paragraphs into sentences during sync; sentence anchors use fuzzy quotes

Pipeline does sentence segmentation (spaCy / cheap heuristic), assigns each sentence a sub-anchor (`paragraph-id#sentence-2`), and Claude or the author can attach styles to those.

- **+** Honors no-markup constraint.
- **-** Sentence segmentation is imperfect, especially on dialogue / abbreviations.
- **-** Sentence boundaries shift frequently as the author edits - anchors are flakier than paragraph anchors.

### S3. Author uses Google Docs *character formatting* as the marker

Author bolds, italicizes, or applies a custom character style ("Comic Sans Red") to a sentence. The pipeline reads `textRun.textStyle` and maps formatting -> CSS class. Effectively: **the author styles the sentence in Google Docs itself**, and we *promote* that to CSS in the build.

- **+** Maximum author affordance - they just use the editor.
- **+** Body stays prose-readable; bold/italic *is* part of normal prose.
- **+** No new anchors needed.
- **-** Vocabulary limited to what Docs character formatting can express.
- **-** Coupling - changing the visual style of a sentence requires editing the doc, not the repo.
- **Mitigation:** define a small set of "magic" character styles (Docs custom styles named `x-callout-emphasis`, `x-strikethrough`, etc.) that the pipeline maps to classes.

### S4. Defer

Ship v1 with paragraph-only. Add per-sentence later if needed. **This is probably right.**

---

## 6. Claude-as-reconciler workflow

A daily pipeline that re-aligns anchors after the author's edits.

### Inputs
1. Previous markdown (`content/prev.md`) - last sync's output.
2. New markdown (`content/new.md`) - just-exported from Docs.
3. Current sidecar (`styles.yml`) - anchors + class assignments.
4. Styling tab content (free-form / tag dictionary).

### Steps (deterministic-first, LLM-as-fallback)

**Phase 1 - Deterministic match (no LLM).**
- For each anchor in `styles.yml`, try to find its target in `new.md` using:
  1. Exact content match (hash unchanged) -> green, done.
  2. Fuzzy quote match (diff-match-patch, threshold = 0.7) -> green, update stored quote/hash.
  3. Heading+ordinal match -> yellow, flag for review.
- Report: `N green, M yellow, K orphans` (anchors with no match).

**Phase 2 - LLM reconciliation (only for K orphans + new paragraphs).**
- Pass Claude: the K orphan anchors (with their old quote, class, and surrounding context) + all new paragraphs that don't yet have an anchor.
- Ask: "For each orphan, identify the new paragraph that best continues its role (or mark it as deleted). For each new paragraph, propose whether it deserves a style based on the styling-tab prompt."
- Output: structured JSON `{matched: [{old_id, new_anchor}], deleted: [...], new_styled: [...]}`.

**Phase 3 - Apply.**
- Update `styles.yml` with the new anchors.
- For yellow matches, the LLM is asked to confirm (in batch).
- For confident greens, auto-commit.
- For yellow/orphan cases, open a PR for human review.

### Determinism props

- The LLM is **only** ever called for the residual (orphans + new content). Steady-state cost: ~$0 per sync.
- All LLM decisions are cached in the sidecar. Re-running the pipeline with no doc changes touches no LLM.
- LLM is given strict schemas (Pydantic / JSON Schema). Temperature 0.

### GitHub Action shape

```
.github/workflows/sync.yml
  schedule: daily at 06:00
  jobs:
    sync:
      - gdoc pull -> content/new.md
      - python reconcile.py
          --prev content/prev.md
          --new content/new.md
          --styles styles.yml
          --styling-tab <fetched>
      - if changes:
          if low-confidence: open PR with diff
          else: commit to main, trigger site rebuild
```

The "open PR vs auto-commit" decision is per-anchor: any yellow/orphan resolutions go into a PR. Pure additions and confirmed-green updates go straight to main.

This is the **right tradeoff** between trust and automation - the author wakes up to either (a) a freshly rebuilt site or (b) a single PR with N decisions to confirm.

---

## 7. Alternatives we haven't fully considered

### Z1. Pattern-only styling (no anchors)

Drop per-paragraph styling entirely. Express the entire visual system as rules over Docs-native structure: heading levels, blockquote style, character styles, list types. No sidecar IDs at all.

- **+** Maximally simple. No reconciliation problem because there are no anchors.
- **+** Doc-native authoring; no parallel state.
- **-** Capped expressiveness - can't say "*this specific paragraph* is special."
- **-** Forces the author to express semantics by manipulating Docs formatting, which the constraint half-allows.

Surprisingly good fit if the visual system is restrained. Many great blogs (Paul Graham, Patrick Collison) have *zero* per-paragraph variance.

### Z2. Styling-tab as both source-of-truth AND output

The styling tab is human-friendly *and* gets *written to* by Claude. After each sync, Claude updates the tab with `# Current decisions` block showing each anchor's slug and class. The author can edit that block; on next sync, edits propagate.

- **+** Author never leaves Google Docs.
- **+** Decisions are visible in the same place authoring happens.
- **-** Two writers (Claude + author) on the same tab - merge conflicts.
- **-** Tab content has to be parseable, which limits authoring freedom.

### Z3. CSS Custom Properties + Docs character styles

The author defines small named character styles in Docs ("Highlight A", "Highlight B"). The pipeline maps them to CSS custom properties (`--accent-a`, `--accent-b`). The repo defines what those evaluate to.

- **+** Author-side: zero new concepts beyond Docs's own style picker.
- **+** Repo-side: simple CSS file.
- **-** Limited to ~5-10 named styles (Docs's UI gets crowded).
- **Probably the cleanest "rules-based" subset.**

### Z4. Comment-thread as authoring channel for styling

The author writes a comment on a paragraph: `style: pull-quote, accent=warm`. The pipeline reads comments via the API, applies the styling, and resolves the comment after applying.

- **+** Comments are first-class invisible-but-explicit. Stable IDs. Author-friendly.
- **+** Conversation-like: the author can comment "make this look better" and Claude can reply with a proposal.
- **-** Comments visible in margin while editing (some authors find this noisy).
- **-** Resolved comments still consume API quota.

**This might be the strongest single option.** It uses an existing Docs affordance that already means "metadata about this passage" and never touches body text.

---

## 8. Design space map (axes)

```
A. ANCHORING            B. MARKUP IN BODY        C. SIDECAR FORMAT         D. RECONCILIATION
----------------        -----------------        ------------------        ------------------
A1 Docs object IDs      B1 zero (LLM infers)     C1 YAML map               D1 none (deterministic only)
A2 heading + ordinal    B2 invisible (bookmark   C2 JSON                   D2 fuzzy match (diff-match-patch)
A3 content hash            / comment / charstyle) C3 CSS attr selectors    D3 LLM reconciler (orphans only)
A4 fuzzy quote          B3 minimal :::tags       C4 TSX components         D4 LLM full-doc + human PR review
A5 LLM semantic IDs     B4 rules-based           C5 rules DSL
A6 bookmarks/comments   B5 rich (rejected)
```

### Incompatible combinations

| Combo | Why it doesn't work |
|---|---|
| B1 (zero markup) + D1 (no reconciliation) | If the LLM is the *only* source of style decisions, you can't skip the LLM on day 2. |
| A3 (content hash) as primary + B1 (zero markup) | Every edit invalidates the anchor, forcing re-decision every run. Cost explodes. |
| A1 (Docs object IDs) as *only* anchor | Indices shift on every edit; not stable across syncs. |
| C4 (TSX components per paragraph) + A5 (LLM semantic IDs as only anchor) | Components keyed by non-deterministic IDs = file churn nightmare. |
| B3 (`:::tag` markup) + the stated constraint | Author has already vetoed visible markup. |
| C3 (CSS attr selectors) + A4 (fuzzy quote as only anchor) | Can't put a quote in a CSS selector. Needs an ID layer. |

### Conflicts to surface to the user

- **"Zero markup" implies LLM-on-critical-path.** If determinism is also a hard requirement, something has to give: either accept invisible markup (bookmarks/comments/character-styles), or accept LLM in pipeline.
- **Fuzzy anchoring is the only thing that survives rewrites without LLM help.** If you don't want LLM reconciliation, you need fuzzy quote selectors. If you don't want fuzzy selectors, you need LLM reconciliation. Pick one.

---

## 9. Most promising 3-5 bundles

Each bundle is a coherent point in design space, opinionated about tradeoffs.

### Bundle 1: "Quiet Determinism" (A6 + B2 + C1 + D1)

Anchors: Google Docs bookmarks (author manually drops a bookmark named `intro-callout` on a paragraph).
Markup: invisible. Body is pure prose; bookmarks render as a tiny edge icon.
Sidecar: `styles.yml` mapping bookmark name -> class. Class definitions in `styles.css`.
Reconciliation: none. Bookmarks are stable IDs by API contract.
Styling tab: T2 (structured tag dictionary) - lists the available class names and what they mean.

**Use when:** the author values determinism > LLM magic, accepts 3 clicks per styled paragraph.
**Reject when:** the author wants the LLM to *decide* what gets styled.

### Bundle 2: "Fuzzy Sidecar" (A4 + B4 + C1 + D2)

Anchors: fuzzy quote selectors (prefix/exact/suffix) stored in YAML.
Markup: zero in body. Convention-based rules (`>` -> pull-quote etc.) handle the common cases.
Sidecar: `styles.yml` with `{quote, prefix, suffix, class}` entries for exceptions.
Reconciliation: diff-match-patch re-anchoring on each sync. No LLM.
Styling tab: T2 (tag dictionary) explains the available classes.

**Use when:** the author wants zero body markup AND no LLM in the pipeline.
**Reject when:** paragraphs get rewritten so heavily that fuzzy match fails routinely.

### Bundle 3: "LLM Reconciler" (A5 + A4 hybrid + B1 + C1 + D3)

Anchors: LLM-assigned semantic slug primary, fuzzy quote backup.
Markup: zero. LLM reads the styling-tab prompt and decides per paragraph.
Sidecar: `styles.yml` cached decisions; `prev.md` archived for diffing.
Reconciliation: orphan-only LLM pass with PR-on-low-confidence.
Styling tab: T3 hybrid (overall prompt + tag definitions + last-run decisions editable by author).

**Use when:** the author trusts Claude to make taste decisions, values "purest prose" most.
**Reject when:** the author wants line-by-line control or hates non-determinism.

### Bundle 4: "Docs-Native Styling" (Z3 / Z1 territory)

Anchors: none. Style is purely a function of Docs-native formatting (headings, blockquotes, character styles, list types).
Markup: invisible-by-virtue-of-being-formatting. Author uses Docs's own UI.
Sidecar: thin CSS file mapping `[data-style="highlight-a"]` etc. -> visual rules.
Reconciliation: not needed - no anchors to reconcile.
Styling tab: T1 (free-form prompt) for overall feel; rules file for mapping.

**Use when:** the visual system is restrained (~5-10 visual patterns total).
**Reject when:** the author wants "this specific paragraph is unique-snowflake-styled."

### Bundle 5: "Comments as Channel" (Z4 + A6 + C1 + D1)

Anchors: comment IDs (stable, API-exposed, invisible-in-body).
Markup: invisible. Author writes `style: callout warm` in a Docs comment on the paragraph.
Sidecar: `styles.yml` - mostly auto-generated by the sync from comments. Author rarely edits directly.
Reconciliation: trivial - comment IDs are stable. Only need to detect deleted/resolved comments.
Styling tab: T2 (tag dictionary explaining the comment-syntax vocabulary).

**Use when:** the author already uses comments for editorial workflow.
**Reject when:** comments are reserved for actual editorial dialogue and shouldn't be co-opted.

---

## 10. Recommendation for next step

Show the user **bundles 1, 2, 3, and 5** as the four serious points in design space. Bundle 4 is a "you might not need any of this" deflation - worth surfacing but probably too restrictive.

The actual fork in the road is between:
- **Bundle 2** ("Fuzzy Sidecar") - the no-LLM-in-pipeline option. Determinism wins.
- **Bundle 3** ("LLM Reconciler") - the maximum-magic option. Purity wins.

Bundles 1 and 5 are valuable variants: same core philosophy as Bundle 2 (no LLM in steady-state), but using Docs-native affordances (bookmarks, comments) instead of fuzzy text anchors. They're worth showing because they hint that **"invisible markup in Docs"** is a serious unexplored design direction - it satisfies the literal constraint while keeping the system deterministic.

If forced to pick one for v1: **Bundle 2 with a Bundle 5 escape hatch.** Fuzzy quote anchors for the common case, comment-driven overrides for the cases where fuzzy fails or the author wants explicit control.

---

## Sources

- [1] [Fuzzy Anchoring - Hypothesis](https://web.hypothes.is/blog/fuzzy-anchoring/) - the seminal post on multi-selector anchoring across document changes.
- [2] [Work with tabs - Google Docs API](https://developers.google.com/workspace/docs/api/how-tos/tabs) - confirms tabs API surface, `includeTabsContent`, nested tabs.
- [3] [google/diff-match-patch](https://github.com/google/diff-match-patch) - the library underneath fuzzy quote re-anchoring.
- [4] [CSS attribute selectors - MDN](https://developer.mozilla.org/en-US/docs/Web/CSS/Attribute_selectors) - the `[data-id="..."]` selector pattern.
- [5] [chopdiff](https://github.com/jlevy/chopdiff) - paragraph/sentence/chunk-level diff transforms for LLM apps; useful prior art for reconciliation.
- [6] [adeu (CriticMarkup for LLMs)](https://github.com/dealfluence/adeu) - extract/validate/commit model for safe LLM document edits; instructive for the "human PR gate" design.
- [7] [Semantic Markers - GoVISIBLE](https://govisible.ai/blog/semantic-markers-how-llms-parse-structured-content/) - how LLMs use heading and structure signals to infer document meaning.
- [8] [Astro MDX integration](https://docs.astro.build/en/guides/integrations-guide/mdx/) - prior art for component-keyed-by-name styling overrides.
- [9] [W3C Web Annotation Data Model](https://www.w3.org/annotation/) - the standard underlying multi-selector anchoring.
