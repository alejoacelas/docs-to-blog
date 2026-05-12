# Stack Research

**Domain:** Google Docs → static blog pipeline (LLM-driven CSS generation, per-paragraph styling, CI/CD sync)
**Researched:** 2026-05-12
**Confidence:** HIGH (core web stack locked by project decision; pipeline stack derived from CLAUDE.md conventions and project constraints)

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Astro | 5.x | Static site generator + custom remark plugin for per-paragraph styling | Only SSG with a first-class remark pipeline that runs at build time per node — makes per-paragraph CSS class injection trivial via unified/remark. **Locked by project decision.** |
| TypeScript | 5.x | Astro site + remark plugin | Required by Astro 5; strict mode catches plugin type errors at compile time rather than silently producing bad HTML. **Locked by project decision.** |
| Python | 3.13 | Pipeline scripts: pull, CSS generation, anchor reconciliation, PR open | The gdoc CLI is Python, the Anthropic SDK is first-class Python, and tomllib (stdlib) reads project.toml with zero dependencies. Pre-installed per CLAUDE.md. |
| uv | latest | Python dependency management and script runner | Declared in CLAUDE.md as the only approved Python tool. Handles lockfiles, inline PEP 723 metadata for standalone scripts, and `uv run` for CI. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| anthropic (Python SDK) | ≥0.40 | LLM calls for CSS generation (Call 1) and anchor reconciliation (Calls 2–4) | Every sync pipeline invocation. Use `client.messages.create` with `response_format` / structured output. |
| diff-match-patch | 20230430 | Fuzzy text matching for Implementation A anchor resolution | Required only in Implementation A (`styles/anchors.yaml` flow). The 0.8 threshold is already in `project.toml`. |
| google-api-python-client | 2.x | Docs API calls to fetch `styling` tab and library doc | The `gdoc` CLI exposes tab content as plain text only; the API client is needed to get structured tab content. |
| google-auth-oauthlib | 1.x | OAuth2 token refresh from `token.json` planted in CI | Companion to `google-api-python-client`. Handles refresh-token flow; reads the same `token.json` that `gdoc` uses. |
| tomllib | stdlib (3.11+) | Read `project.toml` in pipeline scripts | No install needed. Prefer stdlib over `tomli`; Python 3.13 is pre-installed. |
| PyYAML | 6.x | Read/write `styles/anchors.yaml` in Implementation A | Only in Implementation A. Use `yaml.safe_load` / `yaml.safe_dump`; never `yaml.load`. |
| remark-parse / remark-stringify | 11.x | AST traversal in the custom Astro remark plugin | Bundled transitively by Astro 5; pin explicitly in `package.json` to avoid version drift if Astro upgrades. |
| unified | 11.x | Unified processor used by the remark plugin | Same as above — pin alongside remark. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| gdoc CLI | Export Google Doc body as rich markdown (`gdoc cat <url>`) | Must be pre-authenticated (`token.json`). In CI: planted from `GDOC_TOKEN_JSON_B64` secret. Verify `gdoc --version` in pre-flight. |
| GitHub Actions | Cron trigger, pull → build → PR pipeline | Free tier; runner has Python 3.13, Node 20, git. `cron` expression in `project.toml [sync].cron`. |
| Vercel CLI / Vercel GitHub integration | Deploy `main` to production; preview builds per PR | Hobby tier. Auto-deploys on push to `main`. PR preview URLs follow `/preview/<slug>/` convention. |
| eslint + @typescript-eslint | TypeScript linting for the Astro site and remark plugin | Run in CI before build. Use `@typescript-eslint/recommended-type-checked` ruleset. |
| prettier | Code formatting for `.ts`, `.astro`, `.md` files | Add `prettier-plugin-astro` for `.astro` file support. |
| pytest | Unit tests for pipeline scripts (CSS generation validator, anchor resolver) | Use `uv run pytest`. Fixtures should use real sample markdown, not mocks. |

## Installation

```bash
# Astro site (run in repo root)
yarn create astro@latest --template minimal
yarn add -D typescript @astrojs/check

# Remark plugin dependencies (pin explicitly)
yarn add remark-parse remark-stringify unified

# Dev tooling
yarn add -D eslint @typescript-eslint/parser @typescript-eslint/eslint-plugin prettier prettier-plugin-astro

# Pipeline (Python — use uv)
uv add anthropic
uv add "google-api-python-client>=2"
uv add google-auth-oauthlib
uv add PyYAML          # Implementation A only
uv add diff-match-patch  # Implementation A only

# tomllib is stdlib in Python 3.11+; no install needed
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Astro 5 | Next.js 15 | If the blog needed React components, ISR, or server-side auth on most pages. Static output with a remark plugin is awkward in Next. |
| Astro 5 | Eleventy 3 | If TypeScript was not a requirement and the remark ecosystem was not needed. Eleventy is simpler but has no built-in unified integration. |
| Python pipeline scripts | TypeScript pipeline (Node) | If the entire codebase had to be one language. Node has the Anthropic SDK too, but gdoc CLI is Python and `tomllib` stdlib makes TOML parsing free. |
| google-api-python-client | googleapis Node.js client | Only if the pipeline moved to TypeScript. The Python client and the gdoc CLI share the same `token.json`; mixing languages for auth is friction. |
| diff-match-patch | fuzzywuzzy / rapidfuzz | rapidfuzz is faster for large corpora. For paragraph-length strings in a personal blog, diff-match-patch's patch-based semantics are better than ratio-only matching. |
| PyYAML | ruamel.yaml | Use ruamel.yaml only if round-trip comment preservation in `anchors.yaml` becomes important. For v1, PyYAML is simpler. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| pip / pip3 directly | CLAUDE.md prohibition; no lockfile, no reproducibility in CI | `uv add` / `uv run` — lockfile-based, fast, enforced by project convention |
| Service account JSON for Google auth | Not provisioned; project uses OAuth refresh-token flow | `token.json` + `credentials.json` via `google-auth-oauthlib` |
| Gatsby | Webpack-based; custom remark plugins are possible but the plugin API is more complex than Astro's unified integration; GraphQL layer adds overhead | Astro 5 |
| Hugo | Go templates, not TypeScript; no unified/remark integration; per-paragraph CSS injection requires hacks | Astro 5 |
| Webpack / CRA | Not applicable to Astro, but avoid adding webpack-based tooling to the site side | Vite (bundled in Astro 5) |
| langchain / llamaindex | Heavy abstractions for what are simple bounded transforms — adds version churn risk, obscures the bounded-transform architecture | Direct Anthropic SDK calls |
| tool_use / function_calls mid-generation | Prohibited by project constraint: every LLM call is inputs-in / structured-output-out | Structured output (`response_format`) or JSON-mode with validator |
| npm (in the Astro site) | Project uses Yarn; mixing package managers corrupts the lockfile | `yarn` for all JS operations |

## Stack Patterns by Variant

**Implementation A (anchors.yaml + Claude diff review):**
- Add `diff-match-patch` and `PyYAML` to Python dependencies
- Pipeline: `gdoc cat` → diff against last snapshot → Claude (Call 2) proposes anchor updates → validator checks YAML schema → write `anchors.yaml` → Astro build reads anchors
- The remark plugin reads `anchors.yaml` at build time to assign CSS classes to paragraphs by fuzzy-matched anchor text

**Implementation B (Claude re-decides every sync):**
- No `diff-match-patch` or `PyYAML` needed
- Pipeline: `gdoc cat` → Claude (Call 2) assigns class to every paragraph → write `styling/decisions.md` as audit trail → Astro build reads decisions
- Simpler dependency graph; higher token cost per sync

**Both implementations share:**
- Call 1: prose styling tab → `styles/generated.css` (deterministic, always re-run)
- GitHub Actions cron for scheduling
- Vercel for deployment
- Same Astro site and remark plugin entry point (branch switch changes which YAML/MD file the plugin reads)

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| astro@5.x | node@20+ | Astro 5 requires Node ≥18.17.1; pin Node 20 in Actions `actions/setup-node`. |
| astro@5.x | unified@11.x, remark-parse@11.x | Astro 5 ships unified 11 internally; pinning the same major avoids dual-copy issues. |
| google-api-python-client@2.x | google-auth-oauthlib@1.x | Must be same-major; mixing 1.x client with 0.x auth causes token refresh failures. |
| anthropic@0.40+ | Python 3.13 | Confirmed compatible. Use `client.messages.create` (not the legacy `Completion` API). |
| diff-match-patch@20230430 | Python 3.13 | Pure Python; no C extension; no compatibility issues. |

## Sources

- Project PROJECT.md — stack locked (Astro v5, TypeScript), pipeline constraints (bounded LLM transforms, OAuth token.json, uv)
- CLAUDE.md global conventions — Python toolchain (uv, Python 3.13, tomllib stdlib, PyYAML over alternatives)
- project.toml — confirmed `diff-match-patch` dependency, `fuzzy_threshold` config, `auto_merge_orphans` flag, `max_cost_usd` constraint
- Astro docs (knowledge) — unified/remark plugin integration, Node compatibility requirements
- Anthropic SDK docs (knowledge) — Python SDK structured output patterns for bounded transforms

---
*Stack research for: Google Docs → static blog pipeline (Astro v5, TypeScript site + Python sync pipeline)*
*Researched: 2026-05-12*
