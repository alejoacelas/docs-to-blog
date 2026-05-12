# Where & how the daily docs-to-blog pipeline should run

Date: 2026-05-12
Scope: Pick an execution model for the daily job that pulls a Google Doc,
converts to markdown, diffs against yesterday, optionally invokes Claude
Code to reconcile a sidecar, commits, and triggers a rebuild.

---

## TL;DR

**Recommended (v1):** Plain **GitHub Actions on a `schedule:` cron**, calling
the `claude` CLI directly in headless mode (`-p`) — **not** the
`anthropics/claude-code-action`. `gdoc`'s OAuth token (refresh-token based)
is portable and can be base64'd into a GitHub Secret. This avoids the
known p1 bug in `claude-code-action` where scheduled runs fail OIDC
token exchange (Issue #814, open at time of writing).

**Recommended (v2, only if daily latency becomes a problem):** Add a
Cloudflare Worker on Drive `changes.watch` push notifications that fires
a `repository_dispatch` to the same Actions workflow. Same engine,
push-driven.

**Eliminate:**
- Local cron / launchd — fine for prototype day 1, unacceptable for prod
  (laptop closed = site stale).
- Cloudflare Workers / Vercel Cron as the **runner** — sandboxed JS/WASM
  can't execute the `gdoc` binary, can't shell out to `git`, can't run
  the `claude` CLI. They're fine as **trigger** sources, not workers.
- `anthropics/claude-code-action` on a `schedule:` trigger — broken right
  now (#814). Use the CLI directly inside the same Actions runner.

---

## The two auth questions, answered

### `gdoc` in CI: yes, portable

The on-disk token at `~/.config/gdoc/token.json` is a standard Google OAuth
**installed-app** credential. Contents (real shape, redacted):

```json
{
  "token": "ya29....",          // short-lived access token, ignored in CI
  "refresh_token": "1//03A7...", // the one that matters
  "token_uri": "https://oauth2.googleapis.com/token",
  "client_id": "762651716625-...apps.googleusercontent.com",
  "client_secret": "GOCSPX-...",
  "scopes": ["drive", "documents"],
  "expiry": "2026-05-12T18:09:12Z"
}
```

Because there's a `refresh_token`, this token is **self-renewing and
non-interactive**. Plan:

1. Locally: `gdoc auth` once (already done) → token.json exists.
2. `base64 -i ~/.config/gdoc/token.json | pbcopy` → paste into
   `GDOC_TOKEN_B64` GitHub Secret. Same for `credentials.json` →
   `GDOC_CREDENTIALS_B64`.
3. In CI:
   ```bash
   mkdir -p ~/.config/gdoc
   echo "$GDOC_TOKEN_B64" | base64 -d > ~/.config/gdoc/token.json
   echo "$GDOC_CREDENTIALS_B64" | base64 -d > ~/.config/gdoc/credentials.json
   pipx install gdoc-cli   # or whatever its install path is; binary at ~/.local/bin/gdoc
   gdoc cat <DOC_ID> > content.md
   ```

Service-account fallback is *not needed* because the refresh token never
expires under normal use (Google revokes after 6 months of total inactivity
or on password change). A weekly canary that runs `gdoc ls` will keep it
warm. If it ever does expire, re-auth locally + repaste the secret. The
Drive client_id is a "Desktop" type and won't be rejected by Google's
sensitive-scope review since it's user-owned.

### `claude` CLI in CI: yes, with API key

`claude --help` confirms:
- `-p` / `--print` → headless mode, single shot, prints to stdout.
- `--bare` → strictly uses `ANTHROPIC_API_KEY` env var, **never** reads
  the keychain or OAuth tokens. Designed for CI.
- `--dangerously-skip-permissions` → required for unattended tool use
  (Bash, Edit, Write). Safe-ish here because the runner is ephemeral.
- `--output-format json` → parseable result + usage/cost.
- `--max-turns N` → hard ceiling on agent loop, protects against runaway.
- `--allowedTools "Read,Write,Edit,Bash(git:*)"` → least-privilege.

Install via `npm install -g @anthropic-ai/claude-code` in the runner;
auth is just `ANTHROPIC_API_KEY` from secrets. No OAuth needed.

---

## Option matrix

| Option | Works for our pipeline? | gdoc OK? | claude OK? | Can commit back? | Auth friction | Complexity | Cost/mo (daily run) |
|---|---|---|---|---|---|---|---|
| **GH Actions cron + `claude` CLI** | yes | yes (token in secret) | yes (`-p` + API key) | yes (`GITHUB_TOKEN` or PAT) | low | low | ~$0 GH minutes + ~$0.10–1.00 Anthropic |
| GH Actions cron + `anthropics/claude-code-action@v1` | **no, broken on schedule** | yes | yes | yes (GitHub App) | medium | low | same |
| GH Actions cron + Anthropic SDK (no agent) | yes | yes | n/a | yes | low | low | ~$0.05 Anthropic |
| Local cron (launchd) | yes-ish | yes (creds already local) | yes (already logged in) | yes | none | trivial | $0 |
| Cloudflare Workers Cron | **no** (sandbox can't run gdoc/claude) | no | no | no (no git) | n/a | n/a | n/a |
| Vercel Cron | **no** (same sandbox issue; ~60s function cap) | no | no | no | n/a | n/a | n/a |
| Render Cron Job | yes | yes | yes | yes (PAT) | low | medium | $1+/mo |
| Fly.io Cron Manager / Scheduled Machines | yes | yes | yes | yes (PAT) | low | medium-high | ~$2/mo |
| Drive `changes.watch` → Worker → dispatch GH Actions | yes (best for freshness) | yes (downstream) | yes (downstream) | yes (downstream) | medium | high | ~$0 |

---

## Per-option notes

### 1. GitHub Actions + `anthropics/claude-code-action` — AVOID for cron
- Official action: <https://github.com/anthropics/claude-code-action>.
- v1 syntax accepts `prompt:`, `claude_args:`, `anthropic_api_key:`,
  and does support `on: schedule:` in principle.
- **Blocker:** Issue #814 ("Claude doesn't work in cron jobs"), labeled
  `p1` / `bug` / `area:permissions`, **open** as of search date. The
  OIDC token-exchange step fails on `schedule:` triggers with
  `401 Unauthorized — User does not have write access on this repository`,
  even though `workflow_dispatch` with identical perms works. No fix
  merged.
- Re-using `workflow_dispatch` instead of `schedule:` defeats the
  purpose (no daily automation).
- Even when it works, the action is heavier than needed: it spins up
  Claude as a GitHub App identity, designed for PR/issue interaction.
  We just want a deterministic agent run.

### 2. GitHub Actions + `claude` CLI directly — RECOMMENDED
- Bypasses the GitHub App / OIDC dance entirely. The Action is just a
  thin wrapper around the CLI; we can wrap it ourselves.
- Install + auth is two lines:
  ```yaml
  - run: npm install -g @anthropic-ai/claude-code
  - run: claude -p "<prompt>" --dangerously-skip-permissions --max-turns 8
    env:
      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
  ```
- Commit back with default `GITHUB_TOKEN` + `permissions: contents: write`.
- Costs: GitHub-hosted runner minutes are free under 2000/mo on private
  repos for the Free plan, unlimited on public repos. Daily 5-minute
  runs ≈ 150 min/mo. Anthropic API: a reconciliation-only Claude run on
  one document is small, est. <$0.50/day at Sonnet, much less at Haiku.

### 3. GitHub Actions + Anthropic SDK (no agent loop) — VIABLE FALLBACK
- If we don't actually need the agent loop (read files, run shell, edit
  files iteratively), a single `messages.create` call with the
  before/after markdown + sidecar is simpler and more deterministic.
- Trade-off: harder to express "find each new paragraph and assign it
  a stable ID matching nearest old paragraph" as a one-shot. The agent
  loop with Read/Edit tools is genuinely useful here.
- Good v0: ship the deterministic Python diff first, only invoke Claude
  for cases the diff can't resolve. Cheapest and most predictable.

### 4. Local cron — PROTOTYPE ONLY
- `launchd` plist or `crontab -e` with `0 9 * * *` calling a shell
  script. Auth already on disk. No infra cost.
- Fatal flaws for production: laptop sleep/closed/offline, no
  observability, no logs surfaced anywhere, no retries, no isolation
  from local dev state. Useful for the **first 48 hours** of building
  the pipeline because feedback is instant.

### 5. Cloudflare Workers Cron — ELIMINATE (as runner)
- V8 isolate sandbox; can't exec the `gdoc` Python binary, can't shell
  out to `git`, no filesystem. You'd have to reimplement Drive auth in
  JS and call the Anthropic API directly. At that point you've thrown
  away `gdoc` and `claude` entirely.
- **Still useful as a Drive webhook receiver** — see option 9.

### 6. Vercel Cron — ELIMINATE
- Same sandbox limitations as Workers; serverless functions, no
  persistent filesystem, max duration ≤ 60s (free) / 300s (paid). A
  cold-start npm-install of `claude-code` alone exceeds the free
  function ceiling.

### 7. Render Cron Job — VIABLE BUT OVERKILL
- Full Docker image, can install `gdoc` and `claude` CLI. Triggers on
  cron expression. ~$1/mo for tiny job. Commits back via PAT.
- No advantage over GitHub Actions for our load profile, and adds a
  second platform to babysit. Only worth it if we're already deploying
  the **site itself** on Render and want everything in one place.

### 8. Fly.io Cron Manager / Scheduled Machines — VIABLE BUT OVERKILL
- Cron Manager (<https://github.com/fly-apps/cron-manager>) spins up
  one Machine per job, runs the command, tears down. Clean isolation.
- Scheduled Machines (native) work for ~1/day, but timing is
  best-effort and not guaranteed.
- Same verdict as Render: only chose if Fly is already in the stack.

### 9. Drive webhook → trigger Actions — RECOMMENDED FOR v2
- `drive.changes.watch` registers a webhook channel; Drive POSTs to a
  Cloudflare Worker on every change to the doc. Worker calls GitHub's
  `repository_dispatch` API → triggers the same Actions workflow.
- Benefits: rebuild within minutes of an edit, not "next 09:00 UTC."
  Skips ~99% of no-op rebuild attempts on days the doc isn't touched.
- Costs: channels expire (max ~7 days, often 1 hour). Need a tiny
  refresh-loop cron (could be daily in the same Actions workflow) to
  re-register the watch. Worth doing only after v1 is live and we
  actually want fresher rebuilds.
- **Overengineering for v1.** Ship daily polling first.

---

## Recommended pipeline (top choice)

`.github/workflows/sync-doc.yml` outline:

```yaml
name: Sync doc → site
on:
  schedule:
    - cron: "3 9 * * *"        # 09:03 UTC, off the top-of-hour spike
  workflow_dispatch:            # manual button for testing
  repository_dispatch:          # future: Drive webhook → here
    types: [doc-changed]

permissions:
  contents: write               # to commit + push

jobs:
  sync:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with: { python-version: "3.13" }

      - uses: astral-sh/setup-uv@v3

      - name: Install gdoc + claude
        run: |
          uv tool install gdoc-cli                          # or pipx
          npm install -g @anthropic-ai/claude-code

      - name: Restore gdoc OAuth state
        run: |
          mkdir -p ~/.config/gdoc
          echo "$GDOC_TOKEN_B64"       | base64 -d > ~/.config/gdoc/token.json
          echo "$GDOC_CREDENTIALS_B64" | base64 -d > ~/.config/gdoc/credentials.json
        env:
          GDOC_TOKEN_B64:       ${{ secrets.GDOC_TOKEN_B64 }}
          GDOC_CREDENTIALS_B64: ${{ secrets.GDOC_CREDENTIALS_B64 }}

      - name: Pull current doc state
        run: gdoc cat "${{ vars.DOC_ID }}" > site/content/post.md

      - name: Diff against yesterday
        id: diff
        run: |
          if git diff --quiet -- site/content/post.md; then
            echo "changed=false" >> "$GITHUB_OUTPUT"
          else
            echo "changed=true" >> "$GITHUB_OUTPUT"
            git diff site/content/post.md > /tmp/doc.diff
          fi

      - name: Reconcile sidecar with Claude (only if changed)
        if: steps.diff.outputs.changed == 'true'
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          claude -p "$(cat scripts/reconcile-prompt.md)" \
            --dangerously-skip-permissions \
            --max-turns 8 \
            --allowedTools "Read,Write,Edit,Bash(git diff:*)" \
            --output-format json \
            --model claude-sonnet-4-6 \
            > /tmp/claude.json
          jq -r '.result' /tmp/claude.json

      - name: Commit + push
        if: steps.diff.outputs.changed == 'true'
        run: |
          git config user.name  "docs-bot"
          git config user.email "docs-bot@users.noreply.github.com"
          git add site/content/post.md site/content/post.sidecar.json
          git commit -m "sync: doc update $(date -u +%Y-%m-%dT%H:%MZ)"
          git push

      # Site rebuild: assumes deploy is wired to push on main
      # (Vercel/CF Pages/Netlify auto-deploy on push). No extra step needed.
```

**Timing budget per run:** ~30s install, ~5s pull doc, ~2s diff, ~30–90s
Claude (only on change days), ~5s commit+push. Total <3 min typical.
Site rebuild downstream is whatever your hosting provider's build is.

**Secrets needed:** `GDOC_TOKEN_B64`, `GDOC_CREDENTIALS_B64`,
`ANTHROPIC_API_KEY`. `DOC_ID` as a repo variable.

---

## Open questions / risks

1. **gdoc refresh-token longevity in unattended use.** Google rotates
   refresh tokens occasionally; the on-disk file may get rewritten by
   `gdoc` after refresh. In CI, the rewritten file is discarded with
   the runner, so subsequent runs use the *original* refresh token from
   the secret. This should still work indefinitely as long as the
   original refresh token isn't revoked — but worth verifying with a
   2-3 day soak test. If it does rotate-and-invalidate, fallback is a
   nightly local re-paste, or a tiny GitHub Actions step that uses
   `gh secret set` to write the new token back. **Test this before
   trusting it.**

2. **Anthropic CLI install footprint.** `npm i -g @anthropic-ai/claude-code`
   pulls in a non-trivial dependency tree; cache via `actions/cache` on
   `~/.npm` to keep cold start under 30s.

3. **Claude API quota / cost spikes.** Cap with `--max-budget-usd` or
   `--max-turns`. Worst case a runaway agent loop is bounded.

4. **Repository security with `--dangerously-skip-permissions`.** Mitigation:
   `--allowedTools` whitelist + `--max-turns`. The runner is ephemeral
   and has only the checked-out repo + secrets in env. No prod access.

5. **Footnote preservation across `gdoc cat`.** Pretest: pull the actual
   doc, eyeball whether footnotes round-trip cleanly to markdown. If
   not, may need `gdoc pull` (which writes a file) + a custom
   post-processor before this whole plan is viable. Orthogonal to the
   execution-model decision but a prerequisite to shipping.

6. **Concurrency / lock.** GitHub Actions `concurrency: sync-doc` group
   prevents overlapping runs if a manual dispatch fires mid-cron.

7. **Watch the #814 issue.** If it gets fixed, we can revisit using
   `claude-code-action` for richer features (built-in PR creation,
   commit signing). Until then, the raw CLI route is strictly safer.

---

## Sources

- [Claude Code GitHub Actions docs](https://code.claude.com/docs/en/github-actions)
- [anthropics/claude-code-action README](https://github.com/anthropics/claude-code-action)
- [Issue #814 — Claude doesn't work in cron jobs (open p1 bug)](https://github.com/anthropics/claude-code-action/issues/814)
- [claude-code-action solutions / patterns](https://github.com/anthropics/claude-code-action/blob/main/docs/solutions.md)
- [Claude Code headless mode cheatsheet](https://institute.sfeir.com/en/claude-code/claude-code-headless-mode-and-ci-cd/cheatsheet/)
- [How to schedule a recurring Claude Code task (startdebugging.net, 2026-04)](https://startdebugging.net/2026/04/how-to-schedule-a-recurring-claude-code-task-that-triages-github-issues/)
- [Cloudflare Workers Cron Triggers](https://developers.cloudflare.com/workers/configuration/cron-triggers/)
- [Vercel Cron Jobs docs](https://vercel.com/docs/cron-jobs)
- [Render Cron Jobs](https://render.com/docs/cronjobs)
- [Fly.io task scheduling guide](https://fly.io/docs/blueprints/task-scheduling/)
- [Google Drive push notifications (changes.watch)](https://developers.google.com/workspace/drive/api/guides/push)
