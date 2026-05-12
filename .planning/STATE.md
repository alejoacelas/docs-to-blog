# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-12)

**Core value:** The author edits the Google Doc; the published site reflects those edits the next morning, styled correctly, with no manual intervention required.
**Current focus:** Phase 4a — Impl A: Fuzzy Anchors

## Current Position

Phase: 4a of 7 (Impl A — Fuzzy Anchors)
Plan: 0 of 1 in current phase
Status: Ready to plan
Last activity: 2026-05-12 — Phase 3 complete; remark-spans plugin rewrites `<tag>text</tag>` → `<span class="tag">text</span>` end-to-end through Astro's markdown pipeline; gdoc escape behaviour empirically verified and unescaped in `sync/fetch.py`; 13 vitest cases + 9 pytest cases all green; hello.md smoke build renders the canonical aside as a span

Progress: [████░░░░░░] 42%

## Performance Metrics

**Velocity:**
- Total plans completed: 4
- Average duration: — min
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1. Foundations | 2 | — | — |
| 2. Fetch + CSS Pipeline | 2 | — | — |
| 3. Span Plugin | 1 | — | — |

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
Stopped at: Phase 3 complete — `sync/fetch.py` unescapes gdoc's `\<tag\>` markdown export (pytest 9/9), `src/plugins/remark-spans.ts` rewrites mdast html nodes to spans (vitest 13/13), `astro.config.mjs` wires the plugin, `hello.md` renders `<aside>` as `<span class="aside">` in the built HTML, empirical evidence in `notes/2026-05-12-gdoc-span-escaping.md`. Ready to start Phase 4a (Impl A — Fuzzy Anchors).
Resume file: None
