# Feature Research

**Domain:** Google Docs → static blog pipeline with LLM-driven CSS generation
**Researched:** 2026-05-12
**Confidence:** HIGH — scope is tightly defined in PROJECT.md with explicit out-of-scope decisions

## Feature Landscape

### Table Stakes (Users Expect These)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Google Docs body sync | Core premise — without this nothing works | MEDIUM | `gdoc cat` for rich markdown export; Docs API for tabs |
| CSS generation from prose | Core premise — prose style definitions → real CSS | MEDIUM | Call 1 (LLM bounded transform); reads styling tab + library doc |
| Published static site | A blog needs to render in a browser | LOW | Astro v5, deployed to Vercel hobby tier |
| Change detection (no-op on no change) | Cron running 24/7 must not create noise | LOW | Drive `files.get(version)` integer; skip PR if version unchanged |
| Readable URLs and navigation | Expected of any blog | LOW | Astro routing handles this natively |
| Span style support (`<tag>text</tag>`) | Authors expect inline emphasis/callout affordance | MEDIUM | Custom remark plugin; open question: does gdoc markdown export preserve raw `<tag>` syntax? |
| Pending-PR review flow | Author must approve before publish — no surprise deploys | MEDIUM | GitHub Actions opens PR; Vercel preview per slug; author merges |
| Setup documentation | Without it, the 15-min setup promise is broken | LOW | `README.md` with step-by-step; all secrets listed |

### Differentiators (Competitive Advantage)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Prose-defined styles in a Google Doc tab | Author never writes CSS; styles described in plain English | HIGH | The whole LLM pipeline (Call 1) exists to make this work |
| Per-paragraph styling via anchors or re-decision | Finer grain than most Docs→blog tools which only support block-level markdown | HIGH | The A-vs-B parallel prototypes; custom remark plugin for paragraph-level class injection |
| Shared style library doc | Styles reusable across multiple docs without copy-paste | MEDIUM | Docs API pull of library doc; merged with tab styles before CSS generation |
| Auto-merge opt-in with LLM safety gate | Unattended publishing with a built-in sanity check | MEDIUM | Call 4 returns `auto_merge_ok`; only merges when all upstream calls succeeded without retry exhaustion |
| `/updates` review page | Author reviews changes from the blog itself, not GitHub | HIGH | P7 — serverless function, simple password auth, accept/reject/sync triggers |
| A-vs-B implementation harness | Enables principled choice between fuzzy-anchor and re-decision approaches via real data | HIGH | P6 — runs both against same fixtures to compare stability, LLM cost, and correctness |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Real-time webhook rebuilds | "Why wait an hour?" | Requires Google Cloud Pub/Sub or Apps Script infrastructure; marginal latency gain for a personal blog where morning sync is fine | Cron at 60 min + Check Now button on `/updates` page (P7) |
| Per-paragraph inline accept/reject | Granular control over what lands | Adds significant UI complexity; the whole PR is a coherent unit (CSS + content + anchors all change together) | Review the whole PR; revert individual paragraphs in the Doc if needed |
| Custom Google Docs named styles as styling input | "I already styled it in Docs" | Named paragraph/character styles are a completely different API surface; exporting them faithfully requires Docs API structural parsing, not markdown | Prose descriptions in the `styling` tab — simpler and portable across any Doc |
| Multi-author support | "What if I want a co-author?" | Shared mutable state (anchors.yaml, decisions.md) with concurrent writers is a consistency problem that v1 doesn't need to solve | Single author in v1; shared password for `/updates` is sufficient |
| Unnamed bare span wrappers | "Why must every span have a name?" | Anonymous spans can't be mapped to CSS classes; ambiguous intent, impossible to style consistently | Require `<tagname>text</tagname>` — tag name IS the class name, zero lookup needed |
| Side-by-side diff on `/updates` | "Show me what changed" | Doubles the UI work; layout is tricky for prose-heavy content | Open two tabs — Google Doc and Vercel preview; v2 upgrade if friction is real |
| MDX components beyond span tags | "I want custom interactive elements" | MDX adds a build-time compilation step and requires author to know JSX component API | Astro MDX is a clean v2 upgrade if needed; span tags cover 90% of literary blog needs |

## Feature Dependencies

```
[Span style support]
    └──requires──> [Docs body sync]
                       └──requires──> [gdoc CLI + OAuth credentials]

[CSS generation from prose]
    └──requires──> [Docs API access for styling tab + library]
    └──requires──> [Anthropic API key + LLM call harness]

[Per-paragraph styling (Impl A or B)]
    └──requires──> [CSS generation from prose]
    └──requires──> [Docs body sync]

[Pending-PR review flow]
    └──requires──> [GitHub Actions cron]
                       └──requires──> [Per-paragraph styling (Impl A or B)]
                       └──requires──> [Vercel project linked to repo]

[Auto-merge opt-in]
    └──requires──> [Pending-PR review flow]
    └──requires──> [Call 4 safety gate]

[/updates review page]
    └──requires──> [Vercel serverless functions]
    └──requires──> [Pending-PR review flow]
    └──enhances──> [Auto-merge opt-in] (adds Check Now trigger)

[A-vs-B comparison harness]
    └──requires──> [Implementation A (anchors.yaml)]
    └──requires──> [Implementation B (decisions.md)]

[Implementation A] ──conflicts──> [Implementation B]  (same branch cannot run both)
```

### Dependency Notes

- **Span support requires body sync:** There's no span parsing without the markdown export; verify `<tag>` preservation before P3 build.
- **CSS generation requires both API surfaces:** styling tab is Docs API only (gdoc CLI tab export is plain text); library doc is also Docs API. Two separate pulls before Call 1.
- **Per-paragraph styling requires CSS:** Paragraph classes have no effect until CSS is generated and injected into the Astro build.
- **GitHub Actions cron requires the full pipeline:** The cron is the last step; everything upstream must be stable before wiring it together.
- **Impl A conflicts with Impl B on a branch:** They share the same sync entrypoint but diverge at the paragraph-styling call; `project.toml` `implementation` flag toggles which path runs. They live on separate branches until P6 picks a winner.
- **/updates enhances auto-merge:** The Check Now button on `/updates` is the on-demand trigger that makes auto-merge useful outside the hourly cron window.

## MVP Definition

### Launch With (v1)

- [x] Google Docs body sync via `gdoc cat` — nothing works without content
- [x] CSS generation from prose in styling tab + library doc (Call 1) — the core differentiator
- [x] Span tag parsing and `<span class="tag">` emission — literary inline styling is a day-one author expectation
- [x] Either Implementation A or B for per-paragraph styling — one must ship; pick winner post-dogfood
- [x] GitHub Actions cron (60 min default) opening PRs on change — the "next morning" delivery promise
- [x] Vercel production deploy on `main` merge + preview per PR slug — author needs to see output before approving
- [x] `README.md` 15-minute setup — without this, the repo is unusable by anyone (including future self)

### Add After Validation (v1.x)

- [ ] A-vs-B side-by-side comparison harness (P6) — add after both impls have run for a few weeks on real content; the data determines the winner
- [ ] `/updates` review page (P7) — add when GitHub PR UI friction becomes real; not needed to validate the pipeline itself
- [ ] Auto-merge opt-in — add after `/updates` is live and author is confident in the LLM safety gate

### Future Consideration (v2+)

- [ ] Vercel Auth hard-gating on preview URLs — unguessable slugs are fine for a personal blog; revisit if content sensitivity increases
- [ ] Real-time webhook rebuilds — revisit only if hourly sync creates a documented workflow problem
- [ ] Astro MDX components — revisit if author needs interactive elements beyond span-level styling
- [ ] Multi-author support — revisit if the blog gains co-authors

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Google Docs body sync | HIGH | MEDIUM | P1 |
| CSS generation from prose (Call 1) | HIGH | MEDIUM | P1 |
| Span tag parsing + HTML emission | HIGH | MEDIUM | P1 |
| Per-paragraph styling (Impl A or B) | HIGH | HIGH | P1 |
| GitHub Actions cron + PR flow | HIGH | MEDIUM | P1 |
| Vercel deploy (prod + preview) | HIGH | LOW | P1 |
| README 15-min setup | MEDIUM | LOW | P1 |
| Change detection (no-op on no change) | MEDIUM | LOW | P1 |
| A-vs-B comparison harness | MEDIUM | HIGH | P2 |
| `/updates` review page | MEDIUM | HIGH | P2 |
| Auto-merge opt-in | LOW | MEDIUM | P2 |
| Shared style library doc | MEDIUM | LOW | P1 — already in scope of Call 1 |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

## Competitor Feature Analysis

This is not a commercial product competing for market share — it's a bespoke pipeline for one author. The relevant comparison is against the tools an author might otherwise reach for.

| Feature | Ghost/Substack (hosted CMS) | Jekyll/Hugo + Netlify CMS | Our Approach |
|---------|---------------------------|--------------------------|--------------|
| Writing environment | Proprietary editor | Markdown files in git | Google Docs — better writing UX than either |
| Styling authorship | Theme marketplace or CSS file | CSS/Sass file | Prose in a Google Doc tab — zero code |
| Publish flow | Save → publish immediately | Commit → CI → deploy | Edit Doc → cron → PR → merge → deploy |
| Per-paragraph styles | Limited (block types only) | Limited (markdown headings/lists) | First-class via anchors or re-decision |
| Sync automation | Built-in | Manual commit required | GitHub Actions cron |
| Author review before publish | Optional drafts | Manual branch/PR | Mandatory PR; author approves |
| LLM-assisted styling | None | None | Core differentiator |

## Sources

- PROJECT.md — authoritative requirements and decisions
- Astro v5 docs — confirms per-paragraph class injection via remark plugin is the right approach
- Google Docs API docs — confirms tabs require direct API call (not gdoc CLI), `files.get(version)` is the right change detection primitive
- Ghost, Substack, Jekyll, Hugo — qualitative comparison based on known feature sets

---
*Feature research for: Google Docs → static blog pipeline*
*Researched: 2026-05-12*
