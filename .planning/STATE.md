# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-12)

**Core value:** The author edits the Google Doc; the published site reflects those edits the next morning, styled correctly, with no manual intervention required.
**Current focus:** Phase 6 — A-vs-B Comparison Harness (Phase 5 complete on this branch)

## Current Position

Phase: 5 of 7 (CI/CD + PR Flow) — complete on `feat/impl-a-anchors`
Plan: 2 of 2 in current phase
Status: Complete on this branch (Implementation A side only — B branch ships its own copy)
Last activity: 2026-05-13 — Phase 5 complete; `sync/diff_review.py` (Call 4) bounded transform with 1 retry + tolerant JSON extraction + schema validators; wired into `sync/__main__.py` after css_gen + para_style_a with upstream-retry-exhaustion tracking; verdict written to `.sync-verdict.json` (gitignored); `.github/workflows/sync.yml` cron + workflow_dispatch + fixed `sync/pending` branch + Vercel auto-deploy via GitHub integration + auto-merge gate; `README.md` 15-minute setup guide; actionlint clean; 78 pytest + 21 vitest cases all green

Progress: [██████░░░░] 71%

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
| 5. CI/CD + PR Flow | 2 | — | — |

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
- P5: Call 4 (diff_review) uses 1 retry only (per PLAN §7.2) — on failure it defaults `auto_merge_ok=false` and surfaces the parse issue as a concern; no validator-exhaustion crash because this is the gate, not a transform.
- P5: Auto-merge gate combines three booleans: `project.toml [sync].auto_merge` (author opt-in) AND Call 4's `auto_merge_ok` AND `NOT upstream_retry_exhausted` (CI-06). The combined verdict is persisted to `.sync-verdict.json` (gitignored) so the workflow only reads one bool.
- P5: Single fixed `sync/pending` branch prevents duplicate PRs across cron ticks. Existing branch → force-push + edit existing PR + drop a comment with the new run ID; missing branch → create + open. PR body always carries the latest verdict.
- P5: The cron expression lives in two places — `project.toml [sync].cron` (consumed by the pipeline) and `.github/workflows/sync.yml` `schedule.cron` (consumed by GH Actions at workflow-load time). README documents the requirement to keep them in sync.

### Pending Todos

None yet.

### Blockers/Concerns

None.

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-05-13
Stopped at: Phase 5 complete on `feat/impl-a-anchors`. `sync/diff_review.py` is the Call 4 bounded transform — single Claude call, tolerant JSON extraction, deterministic schema validation, 1 retry, defaults `auto_merge_ok=false` on parse exhaustion (17 pytest cases). `sync/__main__.py` runs Call 4 after css_gen + para_style_a, tracks whether either upstream call hit a needs-attention state (CI-06), and writes `.sync-verdict.json` for the workflow to consume. `.github/workflows/sync.yml` is the daily cron: restores gdoc OAuth from base64 secrets to `~/.config/gdoc/accounts/default/token.json` per preflight's path, installs uv + node + gdoc CLI + Python + JS deps, runs `uv run python -m sync`, captures `sync-output.log`, force-pushes to a fixed `sync/pending` branch, edits-or-creates the PR with the verdict in the body, gates auto-merge on `project.toml [sync].auto_merge` ∧ `safe_to_auto_merge`. Vercel's GitHub integration handles preview deploys (PRs) and production deploys (merges to main) — no custom deploy step. `README.md` is the 15-minute setup guide (forks, secrets, project.toml reference, A-vs-B toggle, troubleshooting). `actionlint` clean. 78 pytest + 21 vitest all green. Smoke run via `gh workflow run sync.yml --ref feat/impl-a-anchors` deferred until post-push (the branch isn't on origin yet).
Resume file: None
