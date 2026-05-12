# Project Research Summary

**Project:** docs-to-blog — Google Docs → LLM-styled static blog pipeline
**Domain:** Static site generation with LLM-driven styling automation and Google Docs as CMS
**Researched:** 2026-05-12
**Confidence:** HIGH

## Executive Summary

This is a bespoke personal publishing pipeline where the author writes in Google Docs and the blog updates automatically via a nightly cron. The core differentiator is prose-defined styling: the author describes visual styles in plain English in a Google Doc tab, and an LLM translates that prose into real CSS at sync time — no CSS authorship required. Per-paragraph styling (finer grain than any off-the-shelf Docs→blog tool) is achieved via a custom Astro remark plugin, with two competing implementation strategies that will be evaluated via A/B dogfooding before one is retired.

The recommended approach is a two-layer system: a Python sync pipeline (`sync/`) that pulls from Google Docs, calls Claude for CSS generation and paragraph styling, and commits the results as a PR for author review; and an Astro v5 TypeScript site that performs a pure static build from committed files with no runtime LLM dependencies. The pipeline is triggered by GitHub Actions cron; Vercel deploys on merge. This separation is the key architectural decision — LLM calls happen exactly once per content change, not on every Vercel build.

The main risks are operational rather than architectural: `<tag>` span syntax may be silently escaped by `gdoc cat` (must verify before P3), OAuth refresh tokens expire after 6 months of inactivity (must fail loudly, not silently), and LLM CSS output is non-deterministic across runs (must normalise before writing). None of these are blockers — all have clear mitigations — but each must be addressed at the right phase or it will cause silent failures that are hard to diagnose later.

## Key Findings

### Recommended Stack

See [STACK.md](STACK.md) for full detail.

The stack is largely locked by project decisions. Astro v5 + TypeScript for the site side (first-class unified/remark integration makes per-paragraph CSS injection straightforward); Python 3.13 + `uv` for the pipeline side (gdoc CLI is Python, Anthropic SDK is first-class Python, `tomllib` is stdlib). The two stacks communicate only through committed files on disk — no shared code, no imports across the boundary.

**Core technologies:**
- **Astro 5 + TypeScript**: Static site generator — locked; per-paragraph CSS injection via unified/remark at build time
- **Python 3.13 + uv**: Sync pipeline — locked; `gdoc` CLI, Anthropic SDK, `tomllib` stdlib for config
- **anthropic SDK (≥0.40)**: All LLM calls — bounded transforms with Pydantic validation and max-N retry
- **google-api-python-client + google-auth-oauthlib**: Docs API for tabs and library doc; OAuth refresh-token flow
- **diff-match-patch + PyYAML**: Implementation A only — fuzzy anchor matching and YAML state persistence
- **GitHub Actions + Vercel hobby**: CI scheduling and deployment — free tier, no infra to manage

### Expected Features

See [FEATURES.md](FEATURES.md) for full detail with dependency graph and prioritization matrix.

**Must have (P1 — table stakes and differentiators):**
- Google Docs body sync via `gdoc cat` — pipeline foundation
- CSS generation from prose styling tab + library doc (Call 1) — the core differentiator
- Span tag parsing → `<span class="tag">` HTML emission — literary inline styling
- Per-paragraph styling: either Implementation A (anchors) or B (re-decide) — finer grain than any competitor
- GitHub Actions cron + PR-per-change review flow — author approves before publish
- Vercel prod deploy + per-PR preview — author sees output before merging
- Change detection no-op (Drive version integer) — silent cron must not create noise
- README 15-minute setup — without this, the pipeline is unusable

**Should have (P2 — add after validation):**
- A-vs-B comparison harness — principled winner selection after real dogfooding data
- `/updates` review page — replace GitHub PR UI with an in-blog review surface
- Auto-merge opt-in (Call 4 safety gate) — unattended publishing after trust is established

**Defer (v2+):**
- Real-time webhook rebuilds — hourly sync is sufficient for a personal blog
- Astro MDX components — span tags cover literary blog needs; MDX is a clean upgrade path
- Multi-author support — explicit v1 out-of-scope

### Architecture Approach

See [ARCHITECTURE.md](ARCHITECTURE.md) for full system diagram, data flow, and anti-patterns.

The system has three layers: Google Docs (source), `sync/` Python pipeline (transform), and the Astro site (render). The pipeline writes markdown, CSS, and anchor/decision files to disk; Astro reads them at build time. Every LLM call follows the bounded-transform pattern: fixed inputs, Pydantic output schema, deterministic validator, max-3 retry. CSS is generated once and committed — never regenerated at Vercel build time.

**Major components:**
1. **`sync/fetch.py`** — `gdoc cat` for body; Docs API for tabs/library; Drive version check for no-op detection
2. **`sync/css_gen.py`** (Call 1) — prose styling definitions → normalised `styles/generated.css`
3. **`sync/para_style_a.py` / `para_style_b.py`** (Call 2/3) — paragraph → CSS class assignment, two competing strategies
4. **`sync/auto_merge.py`** (Call 4) — final gate returning `auto_merge_ok: bool`
5. **`src/plugins/remark-spans.ts`** — build-time mdast transform: `<tag>text</tag>` → `<span class="tag">text</span>`
6. **`.github/workflows/sync.yml`** — cron trigger, secret planting, PR creation, optional auto-merge

### Critical Pitfalls

See [PITFALLS.md](PITFALLS.md) for full detail with recovery strategies and phase mapping.

1. **`<tag>` syntax silently escaped by `gdoc cat`** — verify with a real doc before writing P3 parser code; fall back to Docs API structural JSON if escaping occurs
2. **OAuth token expiry kills cron silently** — treat any non-zero `gdoc`/API exit as a hard workflow failure; never swallow auth errors as "no change"
3. **LLM CSS output is non-deterministic** — normalise (sort properties, strip comments, run prettier) before writing `styles/generated.css`; change detection diffs the normalised form
4. **Impl A fuzzy anchor drift** — include paragraph position fingerprints; flag low-confidence matches to `anchors_review.yaml`; ask Claude explicitly whether the paragraph matches the stored anchor
5. **Duplicate PRs from stateless cron** — use a fixed `sync/pending` branch so a push to an existing branch updates the PR rather than creating a new one

## Implications for Roadmap

### Phase 1: Foundations and Configuration
**Rationale:** Everything depends on having `project.toml` schema, repo structure, OAuth credentials in place, and the Astro skeleton running. No pipeline code is useful without a working site to deploy to.
**Delivers:** Repo scaffold, `project.toml` config schema, Astro v5 site shell on Vercel, OAuth credentials planted in GitHub Secrets
**Addresses:** Setup documentation, readable URLs, Vercel deploy
**Avoids:** Doc IDs in committed config (Pitfall 7) — `README.md` warning and secrets convention established here

### Phase 2: Google Docs Fetch + Change Detection
**Rationale:** Body sync and version-based change detection are the pipeline's entry gate. Nothing downstream runs until this layer is solid and the no-op path is verified.
**Delivers:** `sync/fetch.py` — `gdoc cat` body export, Docs API tab/library pull, Drive version check with early exit
**Addresses:** Google Docs body sync, change detection no-op
**Avoids:** OAuth silent failure (Pitfall 2) — hard failure on any auth error established here

### Phase 3: CSS Generation Pipeline
**Rationale:** CSS must exist before paragraph styling has any visible effect. Also the right phase to verify the `<tag>` span escaping question and implement CSS normalisation.
**Delivers:** `sync/css_gen.py` (Call 1), normalised `styles/generated.css`, span syntax verification result
**Addresses:** CSS generation from prose, shared style library doc, span tag support (verification only)
**Avoids:** Non-deterministic CSS diffs (Pitfall 3) — normalisation from day one; `<tag>` escaping discovery (Pitfall 1) — verified before P4 parser work begins

### Phase 4a: Implementation A — Fuzzy Anchors
**Rationale:** One implementation must ship. Impl A (persistent anchors) is lower token cost per sync and more auditable. Build it first on `feat/impl-a-anchors` (current branch).
**Delivers:** `sync/para_style_a.py` (Call 2), `styling/anchors.yaml` state, `remark-spans.ts` plugin reading anchors, confidence threshold logging
**Addresses:** Per-paragraph styling
**Avoids:** Fuzzy anchor drift (Pitfall 4) — position fingerprints and low-confidence flagging built in from the start

### Phase 4b: Implementation B — Re-decide Every Sync
**Rationale:** Build the alternative on `feat/impl-b-redecide` to enable P6 data-driven comparison. The `decisions.md` prior must be a hard prompt input, not just a log.
**Delivers:** `sync/para_style_b.py` (Call 3), `styling/decisions.md` as live prompt input, stability verification (two identical runs)
**Addresses:** Per-paragraph styling (alternative approach)
**Avoids:** Impl B style thrash (Pitfall 8) — prior-decision constraint in prompt from day one

### Phase 5: CI/CD — GitHub Actions Cron + PR Flow
**Rationale:** Wire the full pipeline into Actions only after all sync components are individually tested. The cron is the last integration point; do it last to avoid debugging CI and logic simultaneously.
**Delivers:** `.github/workflows/sync.yml`, duplicate PR guard (fixed `sync/pending` branch), auto-merge opt-in gate (Call 4), PR description with human summary
**Addresses:** GitHub Actions cron, PR review flow, auto-merge opt-in
**Avoids:** Duplicate PRs (Pitfall 5), silent OAuth failure (Pitfall 2 — hard failure in workflow), Vercel function timeout (Pitfall 6 — LLM calls stay in Actions, not Vercel functions)

### Phase 6: A-vs-B Comparison Harness
**Rationale:** After both implementations have run on real content for a few weeks, the harness generates the data needed to pick a winner and delete the loser.
**Delivers:** `tests/compare.py` harness, committed fixtures, side-by-side cost/stability/correctness report, winner decision
**Addresses:** A-vs-B implementation harness
**Avoids:** Subjective winner selection — the data decides

### Phase 7: /updates Review Page
**Rationale:** Add when GitHub PR UI friction becomes real, not before. Requires Vercel serverless functions and a `repository_dispatch` integration.
**Delivers:** `/updates` Astro page with password auth, accept/reject/sync triggers via `repository_dispatch`
**Addresses:** `/updates` review page
**Avoids:** Vercel function timeout (Pitfall 6) — "Check Now" routes through `repository_dispatch`, not a direct LLM call

### Phase Ordering Rationale

- **Fetch before CSS before styling:** Feature dependency graph drives this order — paragraphs can't be styled until CSS exists; CSS can't be generated until the doc body is fetched.
- **Verify `<tag>` escaping in P3, not P4:** The span parser is the riskiest unknown. Discovering it in P3 (CSS phase) means the fallback (Docs API structural JSON) can be incorporated before the parser is written, not after.
- **CI in P5, not P1:** Wiring Actions before the pipeline modules exist creates a debugging surface that obscures which layer is failing. Build locally-testable modules first.
- **A/B branches before comparison harness:** P6 needs real production data from both; it can't be built until both are running.
- **`/updates` last:** It depends on the full pipeline being stable and the author having experienced the PR flow enough to know whether it's actually friction.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 3 (CSS generation):** `<tag>` preservation in `gdoc cat` output is an open question — verify empirically before planning the parser implementation
- **Phase 5 (CI):** GitHub Actions `repository_dispatch` usage for the "Check Now" trigger needs a concrete implementation pattern; verify against Actions docs during planning
- **Phase 7 (`/updates`):** Vercel serverless function auth patterns (simple `Authorization` header vs. Vercel's own middleware) — worth a quick lookup during planning

Phases with standard patterns (research-phase can be skipped):
- **Phase 1 (Foundations):** Astro scaffold and Vercel integration are well-documented and deterministic
- **Phase 2 (Fetch):** `gdoc cat` and `google-api-python-client` usage patterns are well-established
- **Phase 6 (Comparison harness):** Pure Python test harness against committed fixtures — no novel integrations

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Core technologies locked by project decision; supporting libraries confirmed against project.toml and CLAUDE.md conventions |
| Features | HIGH | Scope tightly defined in PROJECT.md with explicit out-of-scope decisions; no ambiguity about v1 vs. v2+ |
| Architecture | HIGH | Two-layer (pipeline/site) separation is well-established pattern; bounded-transform LLM pattern is project-mandated |
| Pitfalls | HIGH | Pitfalls are derived from known API behaviours (gdoc export, OAuth expiry, Vercel timeouts) — not speculation |

**Overall confidence:** HIGH

### Gaps to Address

- **`<tag>` span escaping:** Whether `gdoc cat` preserves `<aside>text</aside>` or escapes it is unconfirmed. Handle during P3 planning with an empirical test before writing parser code.
- **`gdoc cat` markdown stability:** The exact markdown dialect emitted by `gdoc cat` (heading levels, list formatting, inline code) is not fully characterised. Write a fixture test in P2 against a real doc to pin the format before downstream parsing depends on it.
- **Impl A vs. Impl B winner:** Cannot be known until dogfooding data exists. P6 is the resolution; the roadmap must accommodate both branches staying active through P5.

## Sources

### Primary (HIGH confidence)
- `PROJECT.md` — authoritative requirements, stack decisions, implementation constraints
- `CLAUDE.md` global conventions — Python toolchain (uv, tomllib, Python 3.13), credential handling
- `project.toml` — confirmed `diff-match-patch` dependency, `fuzzy_threshold`, `auto_merge_orphans`, `max_cost_usd`

### Secondary (MEDIUM confidence)
- Astro v5 docs — unified/remark plugin integration, content collections, Node compatibility
- Google Docs API reference — `documents.get` with `includeTabsContent`, `drive.files.get(version)` semantics
- Anthropic Python SDK docs — `client.messages.create`, structured output patterns, `temperature=0` for bounded transforms
- Google OAuth 2.0 docs — refresh token expiry policy for unverified apps (6-month inactivity)
- Vercel hobby tier limits — 10-second function timeout (documented on pricing page)

### Tertiary (LOW confidence — needs empirical validation)
- `gdoc cat` markdown export behaviour re: `<tag>` HTML syntax — assumed to escape based on Google's Export API sanitisation behaviour; **must verify in P3**
- `diff-match-patch` degradation on short/similar strings — documented library behaviour; actual threshold for this doc's content unknown until tested

---
*Research completed: 2026-05-12*
*Ready for roadmap: yes*
