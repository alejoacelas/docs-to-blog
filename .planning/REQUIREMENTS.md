# Requirements: docs-to-blog

**Defined:** 2026-05-12
**Core Value:** The author edits the Google Doc; the published site reflects those edits the next morning, styled correctly, with no manual intervention required.

## v1 Requirements

### Sync

- [ ] **SYNC-01**: Running the sync script with a valid `project.toml` exports the Google Doc body as rich markdown via `gdoc cat` and writes it to the content directory
- [ ] **SYNC-02**: The sync script reads the `styling` tab from the Google Doc via the Docs API (not `gdoc cat`) and returns its plain-text content
- [ ] **SYNC-03**: The sync script reads the shared library doc via the Docs API and returns its plain-text content
- [ ] **SYNC-04**: If the Drive `files.get(version)` integer is unchanged from the last recorded value, the sync script exits 0 without creating a PR or commit
- [ ] **SYNC-05**: If the Drive version has advanced, the sync script proceeds with the full pipeline and records the new version on success
- [ ] **SYNC-06**: The sync script exits non-zero and prints a descriptive error if `gdoc`, the Anthropic API key, the OAuth token, or the `project.toml` is missing or invalid at startup

### CSS Generation

- [ ] **CSS-01**: Given prose style definitions from the `styling` tab and the library doc, the LLM call (Call 1) produces a valid `styles/generated.css` file with one rule per named style
- [ ] **CSS-02**: Call 1 is a bounded transform: structured input in, CSS text out, no tool use mid-generation, deterministic output validator runs after each attempt, retries ≤ 3
- [ ] **CSS-03**: If Call 1 fails all retries, the sync script exits non-zero and does not open a PR
- [ ] **CSS-04**: `styles/generated.css` is committed as part of the sync PR, not generated at Vercel build time
- [ ] **CSS-05**: Library doc styles and `styling`-tab styles are merged before Call 1; tab styles take precedence on name collision

### Span Styling

- [ ] **SPAN-01**: The Astro remark plugin recognises `<tagname>text</tagname>` syntax in the imported markdown and emits `<span class="tagname">text</span>` in the rendered HTML
- [ ] **SPAN-02**: Span tags with no matching CSS class in `generated.css` are still emitted as `<span class="tagname">` (no silent strip)
- [ ] **SPAN-03**: Bare/unnamed span wrappers (no tag name) are passed through as plain text without an error
- [ ] **SPAN-04**: Nested span tags (e.g., `<aside><em>text</em></aside>`) render correctly without mangling the inner content

### Per-Paragraph Styling — Implementation A (Anchors)

- [ ] **IMPL-A-01**: `styles/anchors.yaml` maps paragraph fingerprints to CSS class names; the file is committed and tracked in git
- [ ] **IMPL-A-02**: On each sync, the LLM call (Call A) receives the full anchors diff and returns an updated `anchors.yaml` as structured output
- [ ] **IMPL-A-03**: Fuzzy matching via `diff-match-patch` resolves paragraph identity across minor edits before passing the diff to Call A
- [ ] **IMPL-A-04**: Call A is a bounded transform with retries ≤ 3; failure exits the sync non-zero without opening a PR
- [ ] **IMPL-A-05**: The remark plugin reads `anchors.yaml` at build time and injects the mapped class onto each matched paragraph's wrapper element

### Per-Paragraph Styling — Implementation B (Re-decision)

- [ ] **IMPL-B-01**: On each sync, the LLM call (Call B) receives the full current doc body and returns a complete paragraph-to-class mapping as structured output
- [ ] **IMPL-B-02**: Call B appends a dated entry to `styling/decisions.md` recording the mapping it produced; this file is committed as part of the PR
- [ ] **IMPL-B-03**: Call B is a bounded transform with retries ≤ 3; failure exits the sync non-zero without opening a PR
- [ ] **IMPL-B-04**: The remark plugin reads the Call B output at build time and injects mapped classes onto paragraph wrapper elements

### Site Build

- [ ] **SITE-01**: `astro build` produces a static site where every blog post is reachable at a human-readable URL derived from the doc title or slug
- [ ] **SITE-02**: `styles/generated.css` is included in every page's `<head>`; per-paragraph classes resolve against it
- [ ] **SITE-03**: The Astro remark plugin applies both span-tag conversion and paragraph-class injection in a single pass over the markdown AST
- [ ] **SITE-04**: The built site passes `astro check` (TypeScript + Astro diagnostics) with zero errors

### CI / PR Flow

- [x] **CI-01**: A GitHub Actions workflow runs on a cron schedule (default 60 min, overridable in `project.toml`) and executes the full sync pipeline
- [x] **CI-02**: If the sync detects a change, the workflow opens a pull request with the updated content, CSS, and paragraph-styling artefacts as separate commits *(deviation: ROADMAP plan 05-01 supersedes — all artefacts land in a single commit so a fixed `sync/pending` branch can be force-pushed cleanly across cron ticks; per-file commits would require a more complex orchestration that doesn't reflect how a human reviews the diff)*
- [x] **CI-03**: Each PR targets `main`; its branch name includes a timestamp or slug so concurrent PRs do not collide *(deviation: ROADMAP plan 05-01 supersedes — fixed `sync/pending` branch + `concurrency.group: sync-pipeline` prevents collisions instead; only one open sync PR ever exists)*
- [x] **CI-04**: The workflow plants `GDOC_TOKEN_JSON_B64` and `GDOC_CREDENTIALS_JSON_B64` secrets as `token.json` and `credentials.json` before invoking `gdoc`
- [x] **CI-05**: The GitHub Actions runner installs `gdoc` and all Python/Node dependencies before running the sync; the workflow fails fast with a clear message if any install step fails
- [x] **CI-06**: The workflow does not auto-merge by default; auto-merge is only enabled when `project.toml` sets `auto_merge = true` AND Call 4 returns `auto_merge_ok = true` AND no upstream LLM call exhausted its retries

### Deploy

- [x] **DEPLOY-01**: Merging a PR to `main` triggers a Vercel production deploy; the live blog reflects the merged content within 5 minutes of merge *(handled by Vercel GitHub integration; no workflow step needed — verify post-merge)*
- [x] **DEPLOY-02**: Each open sync PR receives a Vercel preview deployment at a unique URL containing the PR branch slug *(handled by Vercel GitHub integration on every push to `sync/pending`)*
- [x] **DEPLOY-03**: The Vercel preview URL is posted as a PR comment or status check so the author can review before merging *(Vercel's GitHub App posts the preview URL as a deployment status; no custom step needed)*

### Configuration

- [ ] **CFG-01**: `project.toml` is the single config file; it contains at minimum: source doc URL, library doc URL, cron interval, implementation toggle (`impl = "A"` or `"B"`), and `auto_merge` flag
- [ ] **CFG-02**: The sync script validates all required `project.toml` fields at startup and exits non-zero with field-level error messages if any are missing
- [x] **CFG-03**: Changing `cron_interval` in `project.toml` and committing the change causes the GitHub Actions schedule to update on the next workflow run *(README documents the two-place requirement: GH Actions reads `schedule.cron` from `sync.yml` at load time, so the workflow file's expression must be edited in lockstep with `project.toml`'s)*

### Error Handling & Observability

- [ ] **ERR-01**: Every LLM call logs its prompt token count, response token count, and attempt number to stdout
- [ ] **ERR-02**: If an LLM call exhausts retries, the sync logs the final error response and exits non-zero; no partial artefacts are committed
- [ ] **ERR-03**: The sync script logs the Drive version integer it observed and whether it triggered a sync or a no-op on each run
- [x] **ERR-04**: GitHub Actions workflow logs are sufficient to diagnose a failure without SSH access to the runner *(every pipeline step emits structured JSON logs to stdout; `sync-output.log` + `.sync-verdict.json` uploaded as workflow artifacts on every run for 14 days)*

### Documentation

- [x] **DOCS-01**: `README.md` contains a step-by-step setup guide that a new author can follow to go from zero to first published sync in under 15 minutes
- [x] **DOCS-02**: `README.md` lists every required GitHub secret and `project.toml` field with type, example value, and where to obtain it
- [x] **DOCS-03**: `README.md` documents how to switch between Implementation A and B via `project.toml`

---

## v2 Requirements

### Updates Page

- **UPD-01**: A `/updates` page on the deployed site lists pending sync PRs with title, date, and preview link
- **UPD-02**: The author can approve (merge) a pending PR from the `/updates` page without opening GitHub
- **UPD-03**: The author can reject (close) a pending PR from the `/updates` page
- **UPD-04**: The `/updates` page has a "Check Now" button that triggers an on-demand sync outside the cron schedule
- **UPD-05**: Access to `/updates` requires a shared password configured in `project.toml`; unauthenticated requests receive a 401

### Auto-Merge Safety Gate

- **AUTOM-01**: When `auto_merge = true`, the pipeline runs a final LLM call (Call 4) that receives the full diff and returns `auto_merge_ok = true/false` as structured output
- **AUTOM-02**: Call 4 returns `auto_merge_ok = false` if any upstream call exhausted retries during this sync run
- **AUTOM-03**: Auto-merge only fires after Call 4 returns `auto_merge_ok = true`; if it returns false, the PR remains open for manual review

### A-vs-B Comparison Harness

- **HARNESS-01**: A comparison script accepts a fixture directory of markdown files and runs both Implementation A and B against them, producing a side-by-side report of class assignments
- **HARNESS-02**: The report includes per-paragraph stability metrics (class assigned in run N vs run N-1) and total LLM call cost for each implementation
- **HARNESS-03**: The harness can be run locally without GitHub Actions credentials

### Security & Access

- **SEC-01**: Vercel preview URLs use unguessable branch slugs; no hard auth gate required for v2 (Vercel Auth is v3+)

---

## Out of Scope

| Feature | Reason |
|---------|--------|
| Real-time webhook rebuilds | Requires Google Cloud Pub/Sub infrastructure; hourly cron + Check Now (v2) covers the use case with far less complexity |
| Custom Google Docs named paragraph/character styles as styling input | Completely different API surface requiring Docs structural parsing; prose-in-tab achieves the same outcome more portably |
| Unnamed/bare span wrappers producing styled output | Anonymous spans have no resolvable class name; requiring `<tagname>` makes the CSS mapping deterministic |
| Per-paragraph inline accept/reject on `/updates` | Whole PR is the coherent review unit in v1; granular accept/reject adds UI complexity without proportionate value |
| Multi-author support | Concurrent writes to `anchors.yaml` / `decisions.md` create consistency problems the v1 design doesn't need to solve |
| Side-by-side diff on `/updates` | Doubles UI work; open two tabs (Google Doc + Vercel preview) is sufficient in v1 |
| Astro MDX components beyond span tags | MDX compilation step requires author JSX knowledge; span tags cover literary blog needs; Astro MDX is a clean v2 upgrade path |
| Public preview hard-gating (Vercel Auth) | Unguessable slugs are sufficient for a personal blog; revisit if content sensitivity increases |
| Per-sentence styling infrastructure | `<tagname>text</tagname>` span syntax covers this use case; dedicated per-sentence infrastructure is over-engineering |

---

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| SYNC-01 | Phase 2 | Pending |
| SYNC-02 | Phase 2 | Pending |
| SYNC-03 | Phase 2 | Pending |
| SYNC-04 | Phase 2 | Pending |
| SYNC-05 | Phase 2 | Pending |
| SYNC-06 | Phase 2 | Pending |
| CSS-01 | Phase 2 | Pending |
| CSS-02 | Phase 2 | Pending |
| CSS-03 | Phase 2 | Pending |
| CSS-04 | Phase 2 | Pending |
| CSS-05 | Phase 2 | Pending |
| SPAN-01 | Phase 3 | Pending |
| SPAN-02 | Phase 3 | Pending |
| SPAN-03 | Phase 3 | Pending |
| SPAN-04 | Phase 3 | Pending |
| IMPL-A-01 | Phase 4a | Pending |
| IMPL-A-02 | Phase 4a | Pending |
| IMPL-A-03 | Phase 4a | Pending |
| IMPL-A-04 | Phase 4a | Pending |
| IMPL-A-05 | Phase 4a | Pending |
| IMPL-B-01 | Phase 4b | Pending |
| IMPL-B-02 | Phase 4b | Pending |
| IMPL-B-03 | Phase 4b | Pending |
| IMPL-B-04 | Phase 4b | Pending |
| SITE-01 | Phase 1 | Pending |
| SITE-02 | Phase 3 | Pending |
| SITE-03 | Phase 3 | Pending |
| SITE-04 | Phase 1 | Pending |
| CI-01 | Phase 5 | Complete |
| CI-02 | Phase 5 | Complete (single-commit deviation per ROADMAP 05-01) |
| CI-03 | Phase 5 | Complete (fixed-branch deviation per ROADMAP 05-01) |
| CI-04 | Phase 5 | Complete |
| CI-05 | Phase 5 | Complete |
| CI-06 | Phase 5 | Complete |
| DEPLOY-01 | Phase 5 | Complete (Vercel GH integration; verify post-merge) |
| DEPLOY-02 | Phase 5 | Complete (Vercel GH integration) |
| DEPLOY-03 | Phase 5 | Complete (Vercel deployment status) |
| CFG-01 | Phase 1 | Pending |
| CFG-02 | Phase 2 | Pending |
| CFG-03 | Phase 5 | Complete (two-place edit documented in README) |
| ERR-01 | Phase 2 | Pending |
| ERR-02 | Phase 2 | Pending |
| ERR-03 | Phase 2 | Pending |
| ERR-04 | Phase 5 | Complete |
| DOCS-01 | Phase 5 | Complete |
| DOCS-02 | Phase 5 | Complete |
| DOCS-03 | Phase 5 | Complete |

**Coverage:**
- v1 requirements: 47 total
- Mapped to phases: 47
- Unmapped: 0 ✓

---
*Requirements defined: 2026-05-12*
*Last updated: 2026-05-12 after initial definition*
