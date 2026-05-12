# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-12)

**Core value:** The author edits the Google Doc; the published site reflects those edits the next morning, styled correctly, with no manual intervention required.
**Current focus:** Phase 3 — Span Plugin

## Current Position

Phase: 3 of 7 (Span Plugin)
Plan: 0 of 1 in current phase
Status: Ready to plan
Last activity: 2026-05-12 — Phase 2 complete; daily sync entry point (`uv run python -m sync`) fetches doc body + styling tab + library, probes Drive version (no-op short-circuit works), regenerates `styles/generated.css` via Anthropic SDK direct, all validators in place, smoke run on the real source doc succeeded at ~$0.037

Progress: [██░░░░░░░░] 28%

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

### Pending Todos

None yet.

### Blockers/Concerns

- **[Pre-P3]** Whether `gdoc cat` preserves `<tag>text</tag>` syntax or escapes it is unconfirmed. Must verify empirically before writing the span parser in Phase 3.

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-05-12
Stopped at: Phase 2 complete — daily sync entry point pulls doc + styling tab + library, probes Drive version (no-op exits 0 in <1s), regenerates `styles/generated.css` via Anthropic SDK direct (sonnet-4-6) with validators + bounded retry; tests pass; smoke run hit real services at ~$0.037. Ready to start Phase 3 (Span Plugin).
Resume file: None
