# docs-to-blog

## What This Is

A pipeline that turns a Google Doc into a daily-synced static blog, where per-paragraph and per-span CSS styles are defined in plain prose — either in a `styling` tab inside the Google Doc or in a shared library doc — and Claude translates those prose definitions into real CSS. The author writes and styles entirely in Google Docs; the repo, CI, and Vercel handle the rest. Built for a single author who wants a literary personal blog without touching code.

## Core Value

The author edits the Google Doc; the published site reflects those edits the next morning, styled correctly, with no manual intervention required.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Pull doc body from Google Docs via `gdoc cat`; pull `styling` tab and library doc via Docs API directly
- [ ] Generate `styles/generated.css` from prose in the `styling` tab + library (Call 1, LLM-driven)
- [ ] Parse `<tag>text</tag>` span syntax in the doc body and emit `<span class="tag">text</span>` in the final HTML (P3)
- [ ] Implementation A: maintain `styles/anchors.yaml` for per-paragraph styling; Claude reviews every diff and updates anchors holistically (P4a)
- [ ] Implementation B: Claude re-decides paragraph styling every sync and maintains `styling/decisions.md` as the audit trail (P4b)
- [ ] GitHub Actions cron (default 60 min, configurable in `project.toml`) pulls, builds, and opens a PR on any change (P5)
- [ ] Every change lands as a discrete commit in a pending state; author approves before it publishes (P5)
- [ ] Vercel deploys `main` to production; each pending change gets a `/preview/<slug>/` build (P5/P7)
- [ ] `/updates` page on the deployed site lets the author accept, reject, or trigger a sync without opening GitHub (P7)
- [ ] Side-by-side comparison harness runs A and B against the same fixtures; pick a winner after dogfooding (P6)
- [ ] `README.md` walks a new author through setup in under 15 minutes

### Out of Scope

- Per-sentence styling — the span tag affordance covers this use case without per-sentence infrastructure
- Inline HTML / MDX components beyond recognised span tags — scope creep for v1; Astro MDX is a v2 upgrade
- Real-time webhook rebuilds — cron + Check Now covers the iteration loop; webhooks add Google Cloud complexity for marginal latency gain
- Custom Google Docs paragraph/character styles as styling inputs — named styles in Docs are a different API surface; prose-in-tab is simpler and more portable
- Unnamed/bare span wrappers — every styled span must name its style to keep the CSS mapping unambiguous
- Per-paragraph inline accept/reject on `/updates` — unit of review is the whole PR in v1
- Multi-author auth — shared password is sufficient for a personal blog
- Public preview hard-gating — unguessable slugs are acceptable for a personal blog; Vercel Auth is v2
- Side-by-side diffing on `/updates` — open two tabs in v1

## Context

The system is built around the insight that Google Docs is a better writing environment than any static-site CMS, but it has no native styling pipeline. The approach avoids any author-side tooling: the author writes prose, the pipeline does the rest. Two competing paragraph-styling implementations (A: fuzzy anchors + Claude reviews diff; B: Claude re-decides every sync) are built in parallel on separate branches so they can be dogfooded side by side before picking a winner in P6.

All external dependencies are already provisioned: the source Google Doc, the library Google Doc, OAuth credentials for `gdoc`, an Anthropic API key, a GitHub repo, and a Vercel project linked to that repo. The implementation must consume these as-is — no mocking, no stubs, non-zero exit if any is missing at runtime.

The `gdoc` CLI handles body export (rich markdown); the Docs API is called directly for tabs (the CLI's tab export is plain text only). Change detection uses the Drive `files.get(version)` integer — monotonic and cheap.

Known open question to verify before P3: whether Google Docs markdown export preserves `<tag>` syntax or escapes/strips it as HTML.

## Constraints

- **Tech stack**: Astro v5, TypeScript — chosen for per-paragraph styling via custom remark plugin; locked
- **LLM calls**: Every call is a bounded transform (inputs in, structured output out, no tool use mid-generation, deterministic validators, bounded retry) — non-negotiable architectural rule
- **Infrastructure**: Vercel hobby tier + GitHub Actions free tier + user's own Anthropic API key — no paid infra beyond what's already in place
- **Auth in CI**: `token.json` planted from base64 secret (`GDOC_TOKEN_JSON_B64` + `GDOC_CREDENTIALS_JSON_B64`) — OAuth refresh-token flow, no service account
- **Auto-merge**: Off by default for v1; opt-in per `project.toml` and only when Call 4 returns `auto_merge_ok = true` and no upstream call exhausted retries
- **Dependency**: `gdoc` CLI must be present and authenticated; `diff-match-patch` for fuzzy matching in Implementation A

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Astro v5 as website stack | Best per-paragraph styling story via custom remark plugin; clean markdown consumption; room to grow | — Pending |
| HTML-style paired tag syntax for spans (`<aside>…</aside>`) | Intrinsic to source, no anchoring needed, tag name = style name | — Pending |
| Prototype both paragraph-styling implementations (A and B) in parallel | Neither fuzzy-only nor Claude-only matching is trusted enough to pick without data from real edits | — Pending |
| Claude reviews every diff in both implementations (not just orphan fallback) | No silent auto-apply; every change is inspected | — Pending |
| `gdoc cat` for body, Docs API directly for tabs | gdoc CLI markdown export is rich; tab export via CLI is plain text only | — Pending |
| Drive `files.get(version)` for change detection | Monotonic integer, cheap to poll, no webhook infrastructure needed | — Pending |
| Vercel hobby for deploy, GitHub Actions for cron | One platform for static site + serverless functions; free runner has Python, git, HTTPS to Anthropic | — Pending |
| `/updates` page deferred to P7 (v1 review happens in GitHub PR UI) | Reduces scope of first shippable; orthogonal to A-vs-B decision | — Pending |
| Auto-merge off by default | First weeks of operation should have human eyes on every change | — Pending |
| `project.toml` as single config file | Doc URLs, cron interval, implementation toggle, auto-merge flag all in one committed file | — Pending |

---
*Last updated: 2026-05-12 after initial project setup*
