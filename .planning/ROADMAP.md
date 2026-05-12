# Roadmap: docs-to-blog

## Overview

Starting from an empty repo, we build a two-layer system: a Python sync pipeline that pulls from Google Docs, calls Claude for CSS generation and paragraph styling, and opens a PR for author review; and an Astro v5 site that builds statically from committed files. Phases 1–5 deliver the complete v1 pipeline — working blog, styled content, daily cron, author-approved PRs. Phases 6–7 add the A-vs-B comparison harness and the in-blog `/updates` review page once v1 is running on real content.

Phases 4a and 4b run in parallel on separate branches (`feat/impl-a-anchors`, `feat/impl-b-redecide`) and both merge to `main` before Phase 5 wires up CI.

## Phases

- [x] **Phase 1: Foundations** — Repo scaffold, `project.toml` schema, Astro site shell deployed to Vercel
- [x] **Phase 2: Fetch + CSS Pipeline** — `sync/fetch.py`, change detection, `sync/css_gen.py` (Call 1), normalised `styles/generated.css`
- [x] **Phase 3: Span Plugin** — Remark plugin: `<tag>text</tag>` → `<span class="tag">text</span>` in built HTML
- [ ] **Phase 4a: Impl A — Fuzzy Anchors** — `sync/para_style_a.py` (Call 2), `styles/anchors.yaml`, plugin reads anchors at build time
- [ ] **Phase 4b: Impl B — Re-decide Every Sync** — `sync/para_style_b.py` (Call 3), `styling/decisions.md` as live prompt input
- [ ] **Phase 5: CI/CD + PR Flow** — GitHub Actions cron, PR-per-change, Vercel preview, auto-merge opt-in (Call 4), README
- [ ] **Phase 6: A-vs-B Comparison Harness** — `tests/compare.py`, fixture corpus, stability/cost report, winner decision
- [ ] **Phase 7: /updates Review Page** — Astro `/updates` page, password auth, accept/reject/Check Now via `repository_dispatch`

## Phase Details

### Phase 1: Foundations
**Goal**: Working Astro site deployed to Vercel; `project.toml` schema validated at startup; repo structure in place for all downstream phases
**Depends on**: Nothing (first phase)
**Requirements**: CFG-01, SITE-01, SITE-04
**Success Criteria** (what must be TRUE):
  1. `astro build` succeeds and `astro check` reports zero errors
  2. Vercel deploys the built site on push to `main` and the URL is reachable
  3. `project.toml` with valid fields passes startup validation; missing fields produce field-level error messages
**Plans**: 2 plans

Plans:
- [x] 01-01: Astro v5 site scaffold — content collections, human-readable post URLs, `styles/generated.css` import in layout
- [x] 01-02: `project.toml` config schema, startup validator, and Vercel project link

---

### Phase 2: Fetch + CSS Pipeline
**Goal**: Sync script fetches doc body, styling tab, and library doc; exits early on no-op; generates and commits normalised `styles/generated.css`
**Depends on**: Phase 1
**Requirements**: SYNC-01, SYNC-02, SYNC-03, SYNC-04, SYNC-05, SYNC-06, CSS-01, CSS-02, CSS-03, CSS-04, CSS-05, CFG-02, ERR-01, ERR-02, ERR-03
**Success Criteria** (what must be TRUE):
  1. `sync/fetch.py` exports doc body via `gdoc cat`, reads styling tab and library doc via Docs API, and writes markdown to the content directory
  2. Running sync twice with no doc change exits 0 the second time without any file mutations
  3. Call 1 (CSS generation) produces a valid, normalised `styles/generated.css` with one rule per named style and retries ≤ 3; failure exits non-zero
  4. Any missing credential or `project.toml` field causes a non-zero exit with a descriptive message before any API call is made
**Plans**: 2 plans

Plans:
- [x] 02-01: `sync/fetch.py` — `gdoc cat` body export (sliced before styling tab), `gdoc cat --tab --plain` for tab/library content (v1 simplification — Docs API direct call deferred), Drive version check via google-api-python-client + gdoc OAuth token, early-exit no-op when neither source nor library version has advanced
- [x] 02-02: `sync/css_gen.py` — Call 1 bounded transform via Anthropic SDK direct, deterministic validators (tinycss2 parse + brace balance, tag coverage, class-name shape `[a-z][a-z0-9-]*`, no external @import), optional review pass, retry ≤ 3 with failure folded back, CSS normalisation (alphabetised properties, comments stripped), structured JSON logging. `sync/__main__.py` is the top-level entry point.

---

### Phase 3: Span Plugin
**Goal**: Remark plugin converts `<tagname>text</tagname>` in imported markdown to `<span class="tagname">text</span>` in the built HTML; span syntax escaping question resolved empirically
**Depends on**: Phase 2
**Requirements**: SPAN-01, SPAN-02, SPAN-03, SPAN-04, SITE-02, SITE-03
**Success Criteria** (what must be TRUE):
  1. A post containing `<aside>text</aside>` in the Google Doc renders `<span class="aside">text</span>` in the built HTML
  2. A span with no matching CSS class is still emitted (not stripped silently)
  3. Nested span tags render without mangling inner content
  4. `gdoc cat` span-escaping behaviour is documented with an empirical test result in `notes/`
**Plans**: 1 plan

Plans:
- [x] 03-01: `src/plugins/remark-spans.ts` — mdast visitor, span-tag → span-class transform, nested tag handling, bare-wrapper passthrough, `<tag>` escaping verification test

---

### Phase 4a: Impl A — Fuzzy Anchors
**Goal**: Per-paragraph styling via persistent `styles/anchors.yaml`; LLM reviews every diff; low-confidence matches flagged; remark plugin injects classes at build time
**Depends on**: Phase 3
**Requirements**: IMPL-A-01, IMPL-A-02, IMPL-A-03, IMPL-A-04, IMPL-A-05
**Branch**: `feat/impl-a-anchors`
**Success Criteria** (what must be TRUE):
  1. `styles/anchors.yaml` is committed and updated each sync; a minor paragraph edit does not orphan the anchor
  2. Call A returns a holistically updated `anchors.yaml`; low-confidence matches appear in `anchors_review.yaml`
  3. The remark plugin injects the mapped CSS class onto each matched paragraph's wrapper element in the built HTML
**Plans**: 1 plan

Plans:
- [x] 04a-01: `sync/para_style_a.py` — `diff-match-patch` fuzzy matching, position fingerprints, Call A bounded transform, `anchors.yaml` state, confidence threshold + `anchors_review.yaml`, plugin anchor-reading extension

---

### Phase 4b: Impl B — Re-decide Every Sync
**Goal**: Per-paragraph styling via full-body re-decision each sync; `styling/decisions.md` is a hard prompt input (not just a log); stability verified across two identical runs
**Depends on**: Phase 3
**Requirements**: IMPL-B-01, IMPL-B-02, IMPL-B-03, IMPL-B-04
**Branch**: `feat/impl-b-redecide`
**Success Criteria** (what must be TRUE):
  1. Call B receives the full doc body and `decisions.md` prior and returns a complete paragraph-to-class mapping
  2. Running sync twice on an unchanged doc produces identical class assignments both times
  3. `styling/decisions.md` gains a new dated entry each sync; the file is committed as part of the PR
**Plans**: 1 plan

Plans:
- [ ] 04b-01: `sync/para_style_b.py` — Call B bounded transform with `decisions.md` as prompt input, stability verification, plugin mapping-reading extension

---

### Phase 5: CI/CD + PR Flow
**Goal**: GitHub Actions cron runs the full pipeline; any doc change opens a PR with Vercel preview; auto-merge opt-in gated on Call 4; README enables 15-minute setup
**Depends on**: Phase 4a and Phase 4b (both merged)
**Requirements**: CI-01, CI-02, CI-03, CI-04, CI-05, CI-06, DEPLOY-01, DEPLOY-02, DEPLOY-03, CFG-03, ERR-04, DOCS-01, DOCS-02, DOCS-03
**Success Criteria** (what must be TRUE):
  1. The cron workflow runs hourly; on a doc change it opens exactly one PR (fixed `sync/pending` branch prevents duplicates)
  2. Each PR gets a Vercel preview URL posted as a PR comment; merging to `main` triggers a production deploy within 5 minutes
  3. Auto-merge fires only when `project.toml` sets `auto_merge = true` AND Call 4 returns `auto_merge_ok = true`; otherwise PR stays open
  4. A new author can follow `README.md` from zero to first published sync without reading any other file
**Plans**: 2 plans

Plans:
- [ ] 05-01: `.github/workflows/sync.yml` — secret planting, dependency install, cron schedule from `project.toml`, fixed `sync/pending` branch, PR creation, Call 4 auto-merge gate
- [ ] 05-02: `README.md` — 15-minute setup guide, secrets reference, `project.toml` field reference, A/B toggle docs

---

### Phase 6: A-vs-B Comparison Harness
**Goal**: Data-driven winner selection after both implementations have run on real content; side-by-side stability, cost, and correctness report
**Depends on**: Phase 5 (both implementations running in production)
**Requirements**: HARNESS-01, HARNESS-02, HARNESS-03
**Success Criteria** (what must be TRUE):
  1. `tests/compare.py` runs locally against committed fixtures without CI credentials
  2. The report shows per-paragraph class stability (run N vs N-1) and total LLM cost for each implementation
  3. Winner is selected and the losing branch is retired
**Plans**: 1 plan

Plans:
- [ ] 06-01: `tests/compare.py` harness, fixture corpus, stability/cost report generator, winner-selection decision

---

### Phase 7: /updates Review Page
**Goal**: Author can accept, reject, and trigger syncs from the deployed blog without opening GitHub
**Depends on**: Phase 5 (stable pipeline + known PR friction level)
**Requirements**: UPD-01, UPD-02, UPD-03, UPD-04, UPD-05
**Success Criteria** (what must be TRUE):
  1. `/updates` lists pending PRs with title, date, and Vercel preview link; requires shared password to access
  2. Author can merge or close a PR from `/updates` without opening GitHub
  3. "Check Now" button triggers an on-demand sync via `repository_dispatch`; LLM calls run in Actions, not in the Vercel function
**Plans**: 1 plan

Plans:
- [ ] 07-01: Astro `/updates` page, Vercel serverless API routes, `repository_dispatch` integration, shared-password auth middleware

---

## Progress

**Execution Order:**
1 → 2 → 3 → 4a ∥ 4b → 5 → 6 → 7

Phases 4a and 4b run in parallel on separate branches and both merge before Phase 5.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundations | 2/2 | Complete | 2026-05-12 |
| 2. Fetch + CSS Pipeline | 2/2 | Complete | 2026-05-12 |
| 3. Span Plugin | 1/1 | Complete | 2026-05-12 |
| 4a. Impl A — Fuzzy Anchors | 1/1 | Complete | 2026-05-12 |
| 4b. Impl B — Re-decide | 0/1 | Not started | - |
| 5. CI/CD + PR Flow | 0/2 | Not started | - |
| 6. A-vs-B Harness | 0/1 | Not started | - |
| 7. /updates Page | 0/1 | Not started | - |
