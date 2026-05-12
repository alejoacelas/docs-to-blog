# Handoff — two parallel Claude Code sessions (A and B)

You're going to run **two independent CC sessions in two terminals**, each in its own git worktree. One builds **Implementation A** (anchors + Claude reviews diff); the other builds **Implementation B** (Claude decides every sync + decisions.md). They do not coordinate. Each builds the whole stack (P1 → P5 from PLAN § 10) on its own branch and pushes when done.

You (the human) come back when both branches are pushed and compare them yourself (P6 — explicit taste call, not delegated).

---

## 0. Pre-flight (~30 seconds, run once before launching either session)

These were already verified at handoff time, but re-run to confirm nothing drifted. If any line prints `[FAIL]`, fix it before launching the sessions.

```bash
cd /Users/alejo/code/tries/2026-05-12-docs-to-blog
set -a; source .env; set +a

# 1. Anthropic API responds with the new key
curl -sf --max-time 10 https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model":"claude-haiku-4-5","max_tokens":4,"messages":[{"role":"user","content":"ok"}]}' \
  | grep -q '"content"' && echo "[ok] anthropic" || echo "[FAIL] anthropic"

# 2. gdoc CLI can read both docs
gdoc cat "$DOC_URL" --plain 2>/dev/null | grep -q "Hello, docs-to-blog" \
  && echo "[ok] gdoc source body" || echo "[FAIL] gdoc source body"
gdoc cat "$DOC_URL" --tab styling --plain 2>/dev/null | grep -q -i "global\|tags" \
  && echo "[ok] gdoc source styling tab" || echo "[FAIL] gdoc source styling tab"
gdoc cat "$LIBRARY_DOC_URL" --plain 2>/dev/null | grep -q "style library" \
  && echo "[ok] gdoc library" || echo "[FAIL] gdoc library"

# 3. Drive version probe (the field the daily cron polls cheaply)
TOKEN=$(python3 -c "import json; print(json.load(open('$HOME/.config/gdoc/token.json'))['token'])")
DOC_ID="${DOC_URL##*/d/}"; DOC_ID="${DOC_ID%%/*}"
curl -sf --max-time 5 \
  "https://www.googleapis.com/drive/v3/files/$DOC_ID?fields=version,modifiedTime" \
  -H "Authorization: Bearer $TOKEN" | grep -q '"version"' \
  && echo "[ok] drive version probe" || echo "[FAIL] drive version probe"

# 4. Vercel CLI authed + project exists + env vars set
# (Vercel CLI writes some output to stderr — use 2>&1 for both grep checks)
vercel whoami >/dev/null 2>&1 \
  && echo "[ok] vercel auth" || echo "[FAIL] vercel auth"
vercel project ls 2>&1 | grep -q "^  docs-to-blog " \
  && echo "[ok] vercel project" || echo "[FAIL] vercel project"
vercel env ls 2>&1 | grep -q "ANTHROPIC_API_KEY" \
  && echo "[ok] vercel env" || echo "[FAIL] vercel env"
```

If any check fails, the autonomous run will fail too — fix before launching, not during.

### About the runtime split (why `gdoc` doesn't need to "work on Vercel")

Three environments touch this codebase. They don't overlap, so the pre-flight verifies each separately:

- **Your local Mac** — where pre-flight runs and where the worktrees live. Has `gdoc`, `python3`, `vercel` CLI.
- **GitHub Actions runner** (Ubuntu, the cron + `workflow_dispatch` target) — restores `token.json` from base64 secrets, installs `gdoc` + the Anthropic SDK, runs the orchestrator, commits artifacts (`anchors.yaml` / `decisions.md` / `generated.css`), and opens the PR. **All `gdoc`, Drive, and Anthropic SDK calls live here.**
- **Vercel build runtime** — only runs `astro build` against the artifacts the orchestrator already produced. After P7 it also hosts the action API routes as Vercel serverless functions, which call the GitHub API for merge/close/dispatch. **Never runs `gdoc`. Never calls Anthropic at build time** — that already happened upstream in GH Actions.

So checks 1–3 verify the GH Actions worldview (gdoc, Drive, Anthropic API). Check 4 verifies the deploy plumbing. There is no scenario where `gdoc` needs to "work on Vercel" — the artifacts have already been resolved by the time Vercel sees the repo.

### What about Google Docs going down mid-run?

Real outages on `docs.googleapis.com` are rare (the [Google Workspace Status Dashboard](https://www.google.com/appsstatus/dashboard/) shows historical outages — typically minutes, not hours). The daily sync script the autonomous run writes should treat HTTP 5xx + network errors as retryable with exponential backoff (3 attempts, 1s/4s/16s); a hard failure after retries should exit non-zero, leaving the previous successful sync intact. There is no fully predictive check — only the pre-flight above + retry logic at run time.

---

## 1. Set up the two worktrees (run once)

```bash
cd /Users/alejo/code/tries/2026-05-12-docs-to-blog
git worktree add ../docs-to-blog-A -b impl-a
git worktree add ../docs-to-blog-B -b impl-b
```

The worktrees share the same `.git` directory but have independent working trees and branches. Each worktree carries the same starting files — including `PLAN.md`, `project.toml`, `.env` (yes, the gitignored .env is in each worktree because it's not tracked, you may need to copy it manually if `set -a; source .env` fails in the worktrees):

```bash
cp /Users/alejo/code/tries/2026-05-12-docs-to-blog/.env ../docs-to-blog-A/.env
cp /Users/alejo/code/tries/2026-05-12-docs-to-blog/.env ../docs-to-blog-B/.env
chmod 600 ../docs-to-blog-A/.env ../docs-to-blog-B/.env
```

(GSD's `.claude/` is committed, so both worktrees have it — no GSD re-install needed.)

`.vercel/` is gitignored, so each worktree starts without a Vercel link. **That's fine** — the GitHub ⇄ Vercel integration auto-deploys on every push, so neither session needs `vercel link` to deploy. If a session wants CLI-level inspection (logs, env pull, manual `vercel --prod`), it can run `vercel link --yes --project docs-to-blog` inside its worktree.

---

## About `notes/` and `demo/` — may be outdated

Files under `notes/` are intermediate research from earlier exploration and `demo/` is a one-shot visual mockup produced **before the A/B split, before the HTML-tag span syntax, and before the SDK-direct decision**. They contain useful underlying findings (gdoc capabilities, stack survey) but their planning recommendations are historical.

When research notes or the demo conflict with `PLAN.md`, **`PLAN.md` wins**. Neither session should reproduce the demo's specific colors, fonts, sample content, or bracket-span notation.

---

## Operating rules (apply to both sessions)

1. **Never mock, stub, or sleep-until-tomorrow.** All resources are real and authenticated (see PLAN § 0). If something is missing, exit non-zero.
2. **PLAN.md is the source of truth.** Don't re-research what it decides. Cite notes when their findings inform implementation; ignore their recommendations.
3. **The daily sync pipeline uses the Anthropic SDK directly — *not* Claude Code, not the `claude` CLI, not any agent harness.** Per PLAN § 1 (LLM execution model), every LLM step in `.github/workflows/sync.yml` is a bounded transform: structured input → structured output, deterministic validators + bounded retries in the orchestrator. Building *with* Claude Code/GSD is fine; the pipeline itself must not call `claude -p`.
4. **Don't modify `demo/`** — reference-only.
5. **PR policy:** LLM-produced styling changes (`styles/anchors.yaml` for Impl A; `styling/decisions.md` for Impl B) open a PR, never auto-merge.
6. **Cost cap per sync run:** `[anchoring].max_cost_usd` in `project.toml`. Track via Anthropic SDK response headers; abort if exceeded.
7. **Don't pause for taste questions.** Pick the most defensible option, document the call, move on.
8. **Each session stays on its own branch.** Do not touch `main`. Do not merge across branches.

---

## Session A — Implementation A (anchors)

**Terminal 1:**

```bash
cd /Users/alejo/code/tries/docs-to-blog-A
claude --dangerously-skip-permissions
```

**Paste this:**

---

You are running **Implementation A** of docs-to-blog in this git worktree, on branch `impl-a`. A companion session is independently building Implementation B in `../docs-to-blog-B` on branch `impl-b`. **You never coordinate with it; do not read its files; do not push to its branch.**

`PLAN.md` at the repo root is authoritative. Section 0 lists every prepared resource (Google Docs, OAuth, GitHub repo, Vercel project, secrets, .env). Section 3.A describes Implementation A specifically: anchors-yaml + Claude reviews the diff every sync (fuzzy matcher as pre-pass hint, Claude is the decider). Section 7 step 3a is your pipeline branch.

**Your scope:** Build phases **P1, P2, P3, P4a, P5** end-to-end on branch `impl-a`. Push to `origin/impl-a`. **Do not build P4b or P6** — P4b is the other session's job; P6 is the user's taste call after both branches are pushed.

**Constraints:**
- All operating rules in `HANDOFF.md` apply. The pipeline uses the Anthropic SDK directly — no `claude -p` in `sync.yml`.
- Set `[doc].implementation = "a"` in `project.toml` before pushing.
- The cron in `sync.yml` should be active (`on: schedule`) so we can dogfood. Vercel's Production deploy stays pointed at `main` until v1.1 pick — don't touch the Vercel project config.
- Fixtures in `tests/fixtures/day1/` and `tests/fixtures/day2/` (PLAN § 9.1) must pass for Implementation A.

**Sequence (zero interaction expected between checkpoints):**

```
/gsd-map-codebase
/gsd-new-project --auto @PLAN.md
/gsd-config        # mode=yolo, workflow.verifier=false, parallelization.enabled=true
/gsd-autonomous    # configure it to build P1, P2, P3, P4a, P5 only — skip P4b and P6
```

If `/gsd-autonomous` won't natively scope to a phase list, run the phases manually with `/gsd-plan-phase N --prd PLAN.md --skip-research --auto` → `/gsd-execute-phase N` for each of P1, P2, P3, P4a, P5 in order. Skip `/gsd-verify-work` between phases (the user is not coming back to verify).

**Done condition:**
- `git push origin impl-a` succeeded
- `.github/workflows/sync.yml` exists and is valid YAML
- `gh workflow run sync.yml --ref impl-a` succeeds end-to-end (manual dispatch smoke test)
- `npm run build` (or yarn equivalent) produces a static site under `dist/`
- Fixtures in `tests/fixtures/day{1,2}` pass
- A `notes/comparison/A-summary.md` exists describing what got built and what to compare against B

If you hit a genuine external outage (Anthropic API or Google Docs returning 5xx after retries), write `notes/run-incidents/A-<timestamp>.md` with the error and exit non-zero — do not wait.

**First action:** `/gsd-map-codebase`, then proceed through the sequence above without pausing.

---

## Session B — Implementation B (decisions)

**Terminal 2:**

```bash
cd /Users/alejo/code/tries/docs-to-blog-B
claude --dangerously-skip-permissions
```

**Paste this:**

---

You are running **Implementation B** of docs-to-blog in this git worktree, on branch `impl-b`. A companion session is independently building Implementation A in `../docs-to-blog-A` on branch `impl-a`. **You never coordinate with it; do not read its files; do not push to its branch.**

`PLAN.md` at the repo root is authoritative. Section 0 lists every prepared resource (Google Docs, OAuth, GitHub repo, Vercel project, secrets, .env). Section 3.B describes Implementation B specifically: no anchors file; Claude reads the full new doc + styling tab + library + previous `styling/decisions.md` every sync, and produces a styled-markdown intermediate plus an updated `decisions.md`. Section 7 step 3b is your pipeline branch.

**Your scope:** Build phases **P1, P2, P3, P4b, P5** end-to-end on branch `impl-b`. Push to `origin/impl-b`. **Do not build P4a or P6** — P4a is the other session's job; P6 is the user's taste call after both branches are pushed.

**Constraints:**
- All operating rules in `HANDOFF.md` apply. The pipeline uses the Anthropic SDK directly — no `claude -p` in `sync.yml`.
- Set `[doc].implementation = "b"` in `project.toml` before pushing.
- The cron in `sync.yml` should be active (`on: schedule`) so we can dogfood. Vercel's Production deploy stays pointed at `main` until v1.1 pick — don't touch the Vercel project config.
- Fixtures in `tests/fixtures/day1/` and `tests/fixtures/day2/` (PLAN § 9.1) must pass for Implementation B.
- The decisions file format: markdown narrative is the current default per PLAN § 6.B and § 11.5. If you find a compelling reason to use structured YAML instead, document the call in `notes/comparison/B-summary.md` and proceed — don't pause.

**Sequence (zero interaction expected between checkpoints):**

```
/gsd-map-codebase
/gsd-new-project --auto @PLAN.md
/gsd-config        # mode=yolo, workflow.verifier=false, parallelization.enabled=true
/gsd-autonomous    # configure it to build P1, P2, P3, P4b, P5 only — skip P4a and P6
```

If `/gsd-autonomous` won't natively scope to a phase list, run the phases manually with `/gsd-plan-phase N --prd PLAN.md --skip-research --auto` → `/gsd-execute-phase N` for each of P1, P2, P3, P4b, P5 in order. Skip `/gsd-verify-work` between phases.

**Done condition:**
- `git push origin impl-b` succeeded
- `.github/workflows/sync.yml` exists and is valid YAML
- `gh workflow run sync.yml --ref impl-b` succeeds end-to-end (manual dispatch smoke test)
- `npm run build` (or yarn equivalent) produces a static site under `dist/`
- Fixtures in `tests/fixtures/day{1,2}` pass
- A `notes/comparison/B-summary.md` exists describing what got built and what to compare against A

If you hit a genuine external outage (Anthropic API or Google Docs returning 5xx after retries), write `notes/run-incidents/B-<timestamp>.md` with the error and exit non-zero — do not wait.

**First action:** `/gsd-map-codebase`, then proceed through the sequence above without pausing.

---

## What you (the human) come back to

- `git branch -r` shows both `origin/impl-a` and `origin/impl-b` pushed
- Both branches build cleanly (`npm run build` works in each worktree)
- Both branches have a valid `.github/workflows/sync.yml` (verifiable with `gh workflow list --repo alejoacelas/docs-to-blog`)
- `notes/comparison/A-summary.md` and `notes/comparison/B-summary.md` describe what each session built
- `main` is untouched — both implementations live as candidates

**Then you do P6 yourself:**

1. Trigger both workflows manually against the same fixture (`gh workflow run sync.yml --ref impl-a` and `--ref impl-b`).
2. Compare the resulting `anchors.yaml` (A) vs `decisions.md` (B) for clarity, inspectability, and accuracy.
3. Compare daily costs in the Anthropic console.
4. Pick a winner. Merge the chosen branch into `main`; Vercel auto-deploys `main`.
5. Delete the loser branch (or keep it parked).

The comparison artifacts in `notes/comparison/` should make this 15 minutes of skimming, not a fresh investigation.
