# Handoff prompt for the next Claude Code session

## Before you start the new session

Launch from this repo so the project-local GSD commands load:

```bash
cd /Users/alejo/code/tries/2026-05-12-docs-to-blog
claude --dangerously-skip-permissions
```

`--dangerously-skip-permissions` is mandatory for the unattended run described below — without it, every tool call will prompt the user, defeating the purpose.

## About `notes/` and `demo/` — may be outdated

The research and earlier planning artifacts under `notes/` (including an earlier version of this handoff prompt at `notes/2026-05-12-gsd-handoff-prompt.md`) **may be outdated**. `PLAN.md` at the repo root has moved past them in places — for example, what `notes/` describes as a "fuzzy-first reconciler" and "bracket-span" syntax has since been replaced by:

- a **two-track A/B prototype** for paragraph styling (anchors-plus-Claude vs Claude-decides-every-sync), and
- **HTML-tag spans** (`<aside>text</aside>`) instead of bracket-spans.

`demo/index.html` is a one-shot visual mockup produced before the A/B split and the HTML-tag span syntax. It is **not** the design spec — visual style now lives in the `styling` tab of the source Google Doc. Do not reproduce its specific colors, fonts, sample content, or notation.

When research notes or the demo conflict with `PLAN.md`, **`PLAN.md` wins**. Cite the underlying findings (gdoc capabilities, stack survey, etc.) only when they inform an implementation choice; treat their planning recommendations as historical.

## Paste this into the new session

---

I'm building **docs-to-blog**: a daily-synced static blog whose content lives in a Google Doc and whose styling is split between a `styling` tab in the Doc and a sidecar in this git repo. **`PLAN.md` at the repo root is the only authoritative document.** Everything you need to execute end-to-end is provisioned — see PLAN.md § 0 "Prepared resources".

**Prepared for you (do not re-create or ask about these):**
- Source Google Doc with body + `styling` tab — URL in `project.toml` and `.env`
- Library Google Doc with gallery body + `styling` tab — URL in `project.toml` and `.env`
- `~/.config/gdoc/token.json` (refresh-token-bearing) and `credentials.json` — locally authenticated
- `ANTHROPIC_API_KEY` in `.env` (gitignored) and in the global `~/.config/credentials/.env`
- GitHub remote `origin` set on `alejoacelas/docs-to-blog`; `gh` authenticated with `repo` + `workflow` scopes
- Repo secrets `ANTHROPIC_API_KEY`, `GDOC_TOKEN_JSON_B64`, `GDOC_CREDENTIALS_JSON_B64` already set (`gh secret list`)
- GitHub Pages enabled with `build_type: workflow`
- `project.toml` — pipeline config (doc URLs, cron, fuzzy threshold, cost cap)
- `.env` (local) and `.env.example` (committed)
- `.claude/` — GSD installed locally for this repo

**Goal:** Build a working v1 fully autonomously. **I am not coming back to verify, approve, or unblock anything.** Run end-to-end and produce both implementation branches A and B for me to compare when I return.

**Operating rules:**
1. **Never mock, stub, or sleep-until-tomorrow.** All resources are real and authenticated. If something is missing, exit non-zero — don't fake it.
2. **PLAN.md is the source of truth.** Don't re-research what it decides. Cite notes when their findings inform implementation; ignore their recommendations.
3. **The daily sync pipeline uses the Anthropic SDK directly — *not* Claude Code, not the `claude` CLI, not any agent harness.** Per PLAN § 1 (the "LLM execution model" row), every LLM step in `.github/workflows/sync.yml` is a bounded transform: known inputs in, structured output out, deterministic validators + bounded retries in our orchestrator code. Do not wire `claude -p` into sync.yml. *Building* the system with GSD/Claude Code is fine — *running* the pipeline through Claude Code is not.
4. **Don't modify `demo/`** — it's reference-only.
5. **PR policy:** LLM-produced styling changes (`styles/anchors.yaml` for Impl A; `styling/decisions.md` for Impl B) open a PR, never auto-merge.
6. **Cost cap per sync run:** `[anchoring].max_cost_usd` in `project.toml` (defaults to $1.00). Track cost via Anthropic SDK response headers; abort if exceeded.
7. **Do not pause for taste questions you cannot answer.** Pick the most defensible option, document the call, move on. The A vs B winner is the only decision I'll make after the run.

**Recommended sequence (the only thing you need to do):**

```
/gsd-map-codebase
/gsd-new-project --auto @PLAN.md
/gsd-config         # set: mode=yolo, workflow.verifier=false, parallelization.enabled=true
/gsd-autonomous
```

That's it. After `/gsd-autonomous` completes, the repo should have:
- An Astro site building cleanly with the sample doc rendered
- `branch-a` containing Implementation A (anchors.yaml + Claude reviews diff)
- `branch-b` containing Implementation B (Claude decides every sync + decisions.md)
- `.github/workflows/sync.yml` wired to repo secrets
- A README with the 15-minute setup walkthrough (per PLAN § 12)
- Comparison artifacts in `notes/comparison/` (or wherever P6 writes them)

**Phase notes:**
- PLAN.md § 9 splits phase 4 into **P4a (Impl A)** and **P4b (Impl B)** — independent, designed to be dispatched to separate agents in parallel. If `/gsd-autonomous` doesn't natively parallelize branches, run them as separate workstreams (`/gsd-workstreams`) or just serialize them — the end state is the same.
- Repo secrets are already set; `.github/workflows/sync.yml` should reference them directly.
- The `gsd-sdk` PATH-resolution warning at install time is known and non-blocking. Only act on it if a command actually fails.

**First action:** `/gsd-map-codebase`, then proceed through the sequence above without stopping. Skip the post-`/gsd-new-project` roadmap-review pause — proceed straight to `/gsd-config` and then `/gsd-autonomous`.

---

## What I expect to come back to

- Both implementation branches built, tested with the fixture pairs in PLAN § 8, and pushed to GitHub.
- A daily sync workflow scheduled and dry-runnable via `workflow_dispatch`.
- A summary comment on a PR (or a `notes/comparison/SUMMARY.md`) explaining what the A vs B comparison looked like on the fixtures, so I can pick the v1.1 default.
- The site live on GitHub Pages (or close to it — if Pages deploys fail for any reason, document why and move on; I'll fix when I'm back).

## If you absolutely must pause

The only scenario where pausing is acceptable is: an external service is genuinely down (Google Docs API outage, Anthropic API outage) and retries don't fix it. In that case, document the failure in `notes/run-incidents/<timestamp>.md` and exit non-zero so I can see it when I return. Do not wait.
