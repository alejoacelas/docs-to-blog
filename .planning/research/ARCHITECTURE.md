# Architecture Research

**Domain:** Static site generation pipeline with LLM-driven styling, Google Docs as CMS
**Researched:** 2026-05-12
**Confidence:** HIGH

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      Google Docs (Source)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐    │
│  │  Doc Body    │  │ Styling Tab  │  │  Library Doc       │    │
│  │ (gdoc cat)   │  │ (Docs API)   │  │  (Docs API)        │    │
│  └──────┬───────┘  └──────┬───────┘  └─────────┬──────────┘    │
└─────────┼─────────────────┼────────────────────┼───────────────┘
          │                 │                    │
┌─────────▼─────────────────▼────────────────────▼───────────────┐
│                    sync/ Python Pipeline                         │
│                                                                  │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐    │
│  │   Fetcher    │   │  CSS Gen     │   │  Para Styler     │    │
│  │ (gdoc + API) │   │  (Call 1)    │   │  (Call 2/3/4)    │    │
│  └──────┬───────┘   └──────┬───────┘   └──────────┬───────┘    │
│         │                  │                       │            │
│  ┌──────▼───────────────────▼───────────────────────▼───────┐  │
│  │              File Writer / Git Committer                  │  │
│  │  content/posts/*.md  styles/generated.css  anchors.yaml   │  │
│  └───────────────────────────┬───────────────────────────────┘  │
└──────────────────────────────┼──────────────────────────────────┘
                               │ git push → PR
┌──────────────────────────────▼──────────────────────────────────┐
│                     GitHub + Vercel                              │
│  ┌──────────────────┐        ┌────────────────────────────────┐ │
│  │  GitHub Actions  │        │  Vercel                        │ │
│  │  cron (60 min)   │        │  main → production             │ │
│  │  PR per change   │        │  PR branch → /preview/<slug>/  │ │
│  └──────────────────┘        └────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                               │ astro build
┌──────────────────────────────▼──────────────────────────────────┐
│                    Astro v5 Site (TypeScript)                     │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐ │
│  │ Remark Plugin│  │  Blog Pages  │  │  styles/generated.css  │ │
│  │ span → class │  │  (Astro)     │  │  (LLM-generated)       │ │
│  └──────────────┘  └──────────────┘  └───────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Implementation |
|-----------|----------------|----------------|
| Fetcher | Pull doc body via `gdoc cat`; pull tabs/library via Docs API; detect changes via `files.get(version)` | Python, `google-api-python-client` |
| CSS Generator (Call 1) | Translate prose style definitions → `styles/generated.css` | Bounded LLM call, structured output |
| Para Styler — Impl A | Fuzzy-match paragraphs to `anchors.yaml`; Claude reviews every diff holistically | Python + `diff-match-patch`, Call 2 |
| Para Styler — Impl B | Claude re-decides all paragraph classes from scratch each sync; writes `styling/decisions.md` audit trail | Python, Call 3 |
| Auto-merge Gate (Call 4) | Final LLM review returning `auto_merge_ok = true/false` | Bounded LLM call, JSON output |
| Remark Plugin | At Astro build time: parse `<tag>text</tag>` spans in markdown → `<span class="tag">text</span>` in HTML | TypeScript, unified/remark |
| GitHub Actions cron | Trigger sync on schedule; open PR on any change | YAML workflow, configurable interval |
| Vercel | Deploy `main` to prod; deploy PR branches to `/preview/<slug>/` | Vercel hobby, linked to repo |

## Recommended Project Structure

```
/
├── project.toml               # doc URLs, cron interval, impl toggle, auto-merge flag
├── sync/                      # Python pipeline — runs in CI, can run locally
│   ├── fetch.py               # gdoc cat + Docs API tab/library fetch + version check
│   ├── css_gen.py             # Call 1: prose → generated.css
│   ├── para_style_a.py        # Call 2: fuzzy anchors + Claude diff review (Impl A)
│   ├── para_style_b.py        # Call 3: Claude re-decides from scratch (Impl B)
│   ├── auto_merge.py          # Call 4: final gate returning auto_merge_ok
│   ├── llm.py                 # shared bounded-transform LLM client (retry, validate)
│   └── main.py                # orchestrator: fetch → css → para → commit → PR
├── content/
│   └── posts/                 # markdown files emitted by sync pipeline
│       └── *.md
├── styles/
│   ├── generated.css          # LLM output from Call 1 — committed, not gitignored
│   └── base.css               # hand-authored resets / typography baseline
├── styling/
│   ├── anchors.yaml           # Impl A: paragraph → style class mapping
│   └── decisions.md           # Impl B: audit trail of every sync decision
├── src/
│   ├── pages/
│   │   ├── index.astro        # blog index
│   │   └── [...slug].astro    # per-post page
│   ├── plugins/
│   │   └── remark-spans.ts    # <tag>text</tag> → <span class="tag">text</span>
│   └── layouts/
│       └── Post.astro         # wraps post content, injects generated.css
├── .github/
│   └── workflows/
│       └── sync.yml           # cron + manual dispatch; plants token.json from secret
└── tests/
    ├── fixtures/              # canonical markdown + expected HTML/CSS outputs
    └── compare.py             # P6 side-by-side harness: runs A and B on same fixture
```

### Structure Rationale

- **`sync/`:** Keeps the Python pipeline self-contained and separately runnable. Each LLM call is its own module so it can be tested and iterated in isolation.
- **`styles/` vs `styling/`:** `styles/` holds build artifacts (CSS); `styling/` holds the pipeline's mutable state files (anchors, decisions). This makes it easy to see what the LLM produced vs what it's tracking.
- **`src/plugins/`:** Co-locates the remark plugin with the Astro source it extends, not in `sync/` — it runs at build time, not sync time.
- **`tests/fixtures/`:** Fixtures are committed snapshots so the P6 comparison harness is deterministic and reproducible across branches.

## Architectural Patterns

### Pattern 1: Bounded LLM Transform

**What:** Every LLM call is a pure function — fixed inputs, structured output schema, deterministic validator, max-N retry. No tool use, no streaming decisions, no open-ended generation.
**When to use:** Every single LLM call in this project.
**Trade-offs:** Slightly more upfront schema design; massively easier to debug, retry, and test. The alternative (free-form generation) produces outputs that break downstream consumers silently.

**Example:**
```python
# sync/llm.py
def bounded_call(
    prompt: str,
    schema: type[BaseModel],
    *,
    retries: int = 3,
) -> BaseModel:
    for attempt in range(retries):
        raw = anthropic_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        try:
            return schema.model_validate_json(raw.content[0].text)
        except ValidationError:
            if attempt == retries - 1:
                raise
    raise RuntimeError("unreachable")
```

### Pattern 2: Commit-as-unit-of-review

**What:** The sync pipeline writes all changed files (markdown, CSS, anchors) and commits them atomically. The commit is the reviewable artifact — the author approves the whole commit via GitHub PR, not individual file changes.
**When to use:** Everywhere the pipeline writes files to the repo.
**Trade-offs:** Coarser review granularity than per-file accept/reject; accepted by design for v1 because per-paragraph inline review (P7) is deferred. Advantage: simpler pipeline, no partial-apply state to manage.

**Example:**
```python
# sync/main.py
def commit_and_push(changed_files: list[Path], slug: str) -> None:
    subprocess.run(["git", "add", *changed_files], check=True)
    subprocess.run(["git", "commit", "-m", f"sync: {slug}"], check=True)
    subprocess.run(["git", "push", "origin", f"sync/{slug}"], check=True)
    gh_pr_create(branch=f"sync/{slug}", title=f"Sync: {slug}")
```

### Pattern 3: Parallel-branch A/B Prototyping

**What:** Implementation A (fuzzy anchors) and Implementation B (Claude re-decides) live on separate branches (`feat/impl-a-anchors`, `feat/impl-b-redecide`). The `project.toml` `implementation` key selects which runs in CI. The P6 comparison harness in `tests/compare.py` runs both against shared fixtures.
**When to use:** When neither approach can be trusted without production data — build both instead of guessing.
**Trade-offs:** Doubles the para-styling code surface. Worth it because the winner will be kept and the loser deleted; the comparison data is the deciding artifact, not code review opinions.

## Data Flow

### Sync Pipeline Flow

```
GitHub Actions cron trigger
    ↓
fetch.py: gdoc cat → raw markdown + Docs API → styling prose + version int
    ↓ (version unchanged? → exit 0, no PR)
css_gen.py (Call 1): styling prose → styles/generated.css
    ↓
para_style_{a|b}.py (Call 2/3): markdown paragraphs → paragraph class assignments
    ↓
auto_merge.py (Call 4): all changes → { auto_merge_ok: bool }
    ↓
main.py: write files → git commit → git push → gh pr create
    ↓ (auto_merge_ok && no retries exhausted?)
gh pr merge (opt-in only)
```

### Build-time Flow

```
Vercel / local: astro build
    ↓
Astro reads content/posts/*.md
    ↓
remark-spans plugin: <tag>text</tag> → <span class="tag">text</span>
    ↓
Post.astro layout: injects styles/generated.css + base.css
    ↓
Static HTML output → deploy
```

### Key Data Flows

1. **Prose → CSS:** Author writes "the aside style has a light grey background and italic text" in the styling tab; Call 1 reads this prose plus the library doc and emits `.aside { background: #f5f5f5; font-style: italic; }` into `styles/generated.css`. This file is committed — it's auditable and doesn't regenerate on every build.
2. **Paragraph → class (Impl A):** Sync computes a diff of the markdown. Claude receives the full `anchors.yaml` plus the diff and returns an updated `anchors.yaml`. The fuzzy matcher (`diff-match-patch`) handles paragraph reordering so Claude only sees genuine content changes.
3. **Paragraph → class (Impl B):** Claude receives all paragraphs and the full `styling/decisions.md` history and returns fresh class assignments plus an updated decisions log. No persistent anchor state; the LLM is the truth store.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1 author, 1 doc | Current design is correct — no adjustments needed |
| Multi-doc (same author) | Add `docs` array to `project.toml`; sync loop iterates; no structural change |
| Multi-author | Add per-author OAuth tokens; scope is explicitly out for v1 |
| High-frequency edits | Reduce cron interval in `project.toml`; pipeline is stateless so parallelism is free |

### Scaling Priorities

1. **First bottleneck:** LLM API latency / cost if sync runs too frequently. Fix: version-check gate exits early when `files.get(version)` hasn't changed — zero API calls for no-op syncs.
2. **Second bottleneck (Impl B only):** Call 3 prompt grows with doc length because all paragraphs are re-evaluated. Fix: chunk by section if needed, or switch to Impl A after P6 dogfooding.

## Anti-Patterns

### Anti-Pattern 1: Regenerating CSS at Build Time

**What people do:** Run the LLM CSS-generation call inside the Astro build (e.g., in a Vite plugin or `astro:build:start` hook).
**Why it's wrong:** Vercel builds run on every push, including non-content PRs. LLM calls in the build path add latency, cost, and a non-deterministic failure mode to every deploy.
**Do this instead:** Generate `styles/generated.css` once in the sync pipeline and commit it. Astro's build is a pure static transform — no LLM calls, no external API dependencies.

### Anti-Pattern 2: Using `gdoc` CLI for Tab Content

**What people do:** Use `gdoc cat --tab styling` to pull the styling tab content.
**Why it's wrong:** The `gdoc` CLI's tab export is plain text only — it strips formatting. The prose styling definitions need to be read as rich text to be unambiguous.
**Do this instead:** Use the Google Docs API directly (`documents.get` with `suggestionsViewMode=PREVIEW_WITHOUT_SUGGESTIONS`) to fetch tab content. Use `gdoc cat` only for the body, where its rich markdown output is the advantage.

### Anti-Pattern 3: Open-ended LLM Generation Without Schema Validation

**What people do:** Prompt Claude to "output the CSS" and parse the response with a regex or string split.
**Why it's wrong:** Any model update, any edge case in the prompt, any unusual style name will silently produce malformed output that only surfaces as a broken site.
**Do this instead:** Define a Pydantic model for every LLM call output. Validate immediately. Retry on validation failure. The schema is the contract between the LLM and the pipeline.

### Anti-Pattern 4: Storing `token.json` in the Repo

**What people do:** Commit the OAuth token for convenience during development.
**Why it's wrong:** OAuth refresh tokens are long-lived credentials. Committing them — even briefly — is a permanent security exposure via git history.
**Do this instead:** In CI, plant `token.json` from the `GDOC_TOKEN_JSON_B64` base64 secret at workflow start. Locally, use `gdoc` auth flow once; the file lives in `~/.config/gdoc/` and is gitignored.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Google Docs (body) | `gdoc cat <doc-id>` subprocess | Outputs rich markdown; must be authenticated via `~/.config/gdoc/token.json` |
| Google Docs (tabs/library) | `google-api-python-client` `documents.get` | Use `GDOC_CREDENTIALS_JSON_B64` secret in CI; tab content only available via API, not CLI |
| Google Drive (version) | `drive.files.get(fileId, fields='version')` | Monotonic integer; cheap pre-flight check before any LLM calls |
| Anthropic API | `anthropic` Python SDK, direct HTTP | Key from env `ANTHROPIC_API_KEY`; non-zero exit if missing |
| GitHub | `gh` CLI (`pr create`, `pr merge`) | Pre-installed on Actions runners; uses `GITHUB_TOKEN` |
| Vercel | Automatic via GitHub integration | `main` → prod; PR branch → preview URL; no explicit API calls needed |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `sync/` ↔ Astro site | Files on disk: `content/posts/*.md`, `styles/generated.css`, `styling/anchors.yaml` | Sync writes; Astro reads. No shared code, no imports across the boundary. |
| `sync/fetch.py` ↔ `sync/para_style_*.py` | Python function calls within the same process | Fetch returns structured data; para styler receives it. Keep as in-process calls, not subprocess. |
| `sync/llm.py` ↔ all callers | Single shared `bounded_call(prompt, schema)` function | All LLM calls go through this one entry point so retry logic, logging, and cost tracking are centralized. |
| `remark-spans.ts` ↔ Astro | Registered as a remark plugin in `astro.config.ts` | Plugin transforms the mdast; no runtime state, no imports from `sync/`. |

## Sources

- Astro v5 content collections docs: https://docs.astro.build/en/guides/content-collections/
- Astro remark plugin guide: https://docs.astro.build/en/guides/markdown-content/#markdown-plugins
- Google Docs API reference: https://developers.google.com/docs/api/reference/rest
- `diff-match-patch` Python library: https://github.com/google/diff-match-patch
- Anthropic Python SDK: https://github.com/anthropics/anthropic-sdk-python

---
*Architecture research for: Google Docs → LLM-styled static blog pipeline (Astro v5)*
*Researched: 2026-05-12*
