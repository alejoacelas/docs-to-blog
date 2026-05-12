# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-12)

**Core value:** The author edits the Google Doc; the published site reflects those edits the next morning, styled correctly, with no manual intervention required.
**Current focus:** Phase 5 — CI/CD + PR Flow

## Current Position

Phase: 5 of 7 (CI/CD + PR Flow)
Plan: 0 of 2 in current phase
Status: Ready to plan (after Phase 4b merges)
Last activity: 2026-05-12 — Phase 4a complete; `sync/anchors.py` data model + paragraph parser + diff-match-patch fuzzy matcher; `sync/para_style_a.py` Call 2 reconciler (bounded transform + validators + review pass + 3-attempt retry); `src/plugins/remark-anchors.ts` injects classes on `<p>` wrappers from anchors.yaml; pipeline wired into `sync/__main__.py`; first smoke run produced one valid anchor on the napkin paragraph at $0.014 Call 2 cost; built HTML carries `<p class="aside">`; 61 pytest + 21 vitest cases all green

Progress: [█████░░░░░] 57%

## Performance Metrics

**Velocity:**
- Total plans completed: 6
- Average duration: — min
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1. Foundations | 2 | — | — |
| 2. Fetch + CSS Pipeline | 2 | — | — |
| 3. Span Plugin | 1 | — | — |
| 4a. Impl A — Fuzzy Anchors | 1 | — | — |

**Recent Trend:** No data yet

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Pre-roadmap: Two paragraph-styling implementations (A: fuzzy anchors, B: re-decide) built in parallel on separate branches; winner selected in Phase 6 after dogfooding data
- Pre-roadmap: `gdoc cat` for body export; Docs API directly for tab content (CLI tab export is plain text only)
- Pre-roadmap: LLM CSS output must be normalised before commit to prevent non-deterministic diffs
- P1: Astro v5 reserves the `slug` frontmatter field; posts use Astro's auto-derived slug from filename instead of a custom field. URLs remain `/<filename-without-extension>`.
- P2: For v1 simplicity, the styling tab is read via `gdoc cat --tab <title> --plain` (plain-text export from the CLI) rather than a direct Docs API call. This satisfies SYNC-02 ("returns its plain-text content"); a Docs-API path can be added later if richer formatting is needed.
- P2: Body markdown is sliced before the first `# {styling_tab_title}` heading. Default `gdoc cat` returns rich markdown for all tabs concatenated; `--tab <title>` strips formatting. The slice plus a leading-H1 tab-title strip is the v1 way to isolate the body in rich markdown.
- P2: `.sync-state.json` is committed so the no-op short-circuit works across CI runs. Schema: `{"doc_version": int, "library_version": int}`.
- P2: Deterministic-validator failure exits non-zero; review-pass-only failure commits the last good attempt with `needs_attention=true` per PLAN §7.1 step 6.
- P2: Production model is `claude-sonnet-4-6` (alias). Pricing $3/MTok input + $15/MTok output. Cost cap is `[anchoring].max_cost_usd`, default $1.00 per sync.
- P3: `gdoc cat` markdown export escapes every angle bracket as `\<` / `\>`. Unescape happens in `sync/fetch.py` (narrow regex on `[a-z][a-z0-9-]*`-shaped tagnames only) before the markdown is written to disk, so the remark plugin sees canonical `<tag>` syntax and doesn't have to know about gdoc's quirks. See `notes/2026-05-12-gdoc-span-escaping.md`.
- P3: Remark already splits `<aside>x</aside>` inside a paragraph into three flat siblings (open-html, text, close-html). The plugin rewrites those html-node values rather than parsing strings — simpler, naturally handles nesting, and lets unbalanced opens/closes pass through verbatim with no error.
- P3: Plugin uses raw mdast `html` nodes (not MDX). Astro's default markdown pipeline already enables `allowDangerousHtml` + `rehypeRaw`, so the emitted `<span class="...">` survives to the rendered page.
- P4a: Anchor identity is `(quote.exact, heading, ordinal, hash)` per PLAN §6.A. Quote-substring is the load-bearing identity check at build time; hash drift only logs a warning since yaml may pre-date the latest typo fix.
- P4a: diff-match-patch's `Match_Threshold` semantics ("0 = exact, 1 = anything") inverts the project.toml convention ("closer to 1.0 = stricter"). The fuzzy matcher inverts on the way in so the config field reads naturally.
- P4a: At-most-one-anchor-per-paragraph is enforced by the validator — `(heading, ordinal)` is the unique key. Two classes on the same paragraph would be a v2 affordance.
- P4a: Astro 5's content layer caches rendered HTML in `node_modules/.astro/data-store.json`. Its cache digest doesn't reach into `anchors.yaml`, so the sync pipeline eagerly invalidates the cache after every reconciler write — otherwise the next `astro build` would serve stale HTML missing the new classes.

### Pending Todos

None yet.

### Blockers/Concerns

None.

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-05-12
Stopped at: Phase 4a complete — `sync/anchors.py` holds the Anchor/Quote/Paragraph dataclasses, hash function, markdown paragraph parser, and diff-match-patch fuzzy matcher (20 pytest cases). `sync/para_style_a.py` runs Call 2 as a bounded transform: assembles inputs, calls Claude once, runs five deterministic validators (parse, class known, quote substring, ordinal reachable, hash match, no duplicate position), optional review pass, three retries with failure folded back, hard-fail on validator exhaustion per IMPL-A-04 (18 pytest cases). `src/plugins/remark-anchors.ts` reads anchors.yaml at build time and attaches `data.hProperties.className` to matched paragraphs (8 vitest cases). Astro's content-layer cache (`node_modules/.astro/data-store.json`) is invalidated after every reconciler write. Smoke run against the real Google Doc produced one anchor (`aside` on the napkin paragraph) at $0.014 Call 2 cost; `<p class="aside">` lands in the built HTML. Ready for Phase 4b (parallel branch) and Phase 5 (CI/CD).
Resume file: None
