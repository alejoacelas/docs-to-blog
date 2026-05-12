# docs-to-blog

A Google Doc, daily-synced to a static Astro blog. The author writes prose in
Google Docs and tags spans with `<aside>…</aside>`-style HTML. A nightly GitHub
Actions cron pulls the doc, regenerates CSS from a `styling` tab, reconciles
per-paragraph class assignments with Claude, and opens a PR for review. Vercel
auto-deploys main and posts preview URLs on PRs.

The authoritative design doc is [`PLAN.md`](./PLAN.md). This README is the
minimum a new author needs to ship their first post.

## 5-minute setup

1. **Fork the repo** (or use it as a template) and clone it locally.
2. **Link a Vercel project** to your fork via the Vercel GitHub integration.
   Framework preset: Astro. Production branch: `main`. Add `ANTHROPIC_API_KEY`
   to the project's environment variables. No other Vercel config is needed —
   the GitHub integration handles preview deploys per-PR and production deploys
   on merge to main.
3. **Add the three GitHub secrets** below.
4. **Point `project.toml` at your docs**: set `[doc].url` (the source doc) and
   `[doc].library_url` (the shared style library). Both docs need a tab named
   `styling` (see [PLAN §4](./PLAN.md#4-the-styling-tab--author-facing-schema)).
5. **Run the workflow once manually**: `gh workflow run sync.yml`. Watch with
   `gh run watch`. If everything is wired, a `sync/pending` PR opens within ~3
   minutes.

## Required GitHub secrets

| Secret                       | Type   | How to generate                                                                                                                            |
| ---------------------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `ANTHROPIC_API_KEY`          | string | From [console.anthropic.com](https://console.anthropic.com/) → API keys. Pipeline calls cost ~$0.10 per sync.                              |
| `GDOC_TOKEN_JSON_B64`        | string | Authenticate the [gdoc CLI](https://github.com/LucaDeLeo/gdoc) locally (`gdoc auth`), then `base64 -i ~/.config/gdoc/token.json \| pbcopy`. Must contain a `refresh_token`. |
| `GDOC_CREDENTIALS_JSON_B64`  | string | The OAuth client JSON: `base64 -i ~/.config/gdoc/credentials.json \| pbcopy`.                                                              |

Add each with: `gh secret set <NAME> --body "<pasted-value>"`.

## `project.toml` reference

```toml
[doc]
url = "https://docs.google.com/document/d/.../edit"
library_url = "https://docs.google.com/document/d/.../edit"
styling_tab_title = "styling"
implementation = "a"  # see "Choosing Implementation A vs B"

[sync]
cron = "3 9 * * *"     # cron expression in UTC; default 09:03 daily
auto_merge = false     # default off — see "auto-merge"

[anchoring]
fuzzy_threshold = 0.8  # diff-match-patch threshold (Implementation A)
max_cost_usd = 1.00    # hard cost cap per sync run
max_orphan_resolution_turns = 6

[deploy]
target = "vercel"
```

| Field                              | Example                              | Meaning                                                                                       |
| ---------------------------------- | ------------------------------------ | --------------------------------------------------------------------------------------------- |
| `doc.url`                          | `https://docs.google.com/.../edit`   | The Google Doc that holds the blog body and `styling` tab.                                    |
| `doc.library_url`                  | `https://docs.google.com/.../edit`   | The shared library doc (gallery body + `styling` tab) — see [PLAN §5](./PLAN.md#5-the-library-doc--gallery-shape). |
| `doc.styling_tab_title`            | `"styling"`                          | Exact name of the styling tab inside both docs.                                               |
| `doc.implementation`               | `"a"` or `"b"`                       | See below.                                                                                    |
| `sync.cron`                        | `"3 9 * * *"`                        | Cron expression. **Also update `.github/workflows/sync.yml`** — see "Changing the cron".      |
| `sync.auto_merge`                  | `false`                              | When `true`, PRs auto-merge if Call 4 returns `auto_merge_ok=true` and no upstream call exhausted retries. |
| `anchoring.fuzzy_threshold`        | `0.8`                                | Stricter (→1.0) = fewer fuzzy matches; 0.8 tolerates typo fixes.                              |
| `anchoring.max_cost_usd`           | `1.00`                               | Sync aborts if cumulative Anthropic cost exceeds this.                                        |
| `deploy.target`                    | `"vercel"`                           | v1 always `vercel`.                                                                           |

## Choosing Implementation A vs B

Two paragraph-styling strategies are built behind `[doc].implementation`:

- **`"a"` — Anchors + Claude reviews the diff.** A YAML sidecar (`styles/anchors.yaml`) records every styled paragraph by quote + heading + ordinal + content hash. Each sync, a fuzzy matcher pre-pass plus a Claude call holistically update the file. Pros: inspectable, hand-editable artifact; smaller per-sync context. See [PLAN §3.A](./PLAN.md#implementation-a--anchors--claude-reviews-the-diff).
- **`"b"` — Claude decides every sync.** No anchors file; Claude re-decides paragraph classes from scratch each run and maintains a markdown audit narrative at `styling/decisions.md`. Pros: simpler; no fuzzy matcher to debug. See [PLAN §3.B](./PLAN.md#implementation-b--claude-decides-every-sync-decisions-file-as-audit).

This branch (`feat/impl-a-anchors`) only contains A. Implementation B lives on `feat/impl-b-redecide`; once Phase 6's comparison harness picks a winner, the losing branch is retired. Until then `[doc].implementation` is effectively pinned per branch.

## First sync — day one workflow

1. Open your source doc. Write a paragraph or two; wrap any inline span like
   `Here is a <aside>quiet thought</aside>.`
2. Open the `styling` tab. Define each tag in prose, e.g.
   `**aside** — a reflective tangent. Indented, italic, slightly smaller.`
3. Either wait for the next cron tick, or run `gh workflow run sync.yml`.
4. The workflow opens a PR on the `sync/pending` branch. Review the diff (see
   below). Merge → Vercel deploys to your domain within a couple of minutes.

## Reviewing a sync PR

A sync PR touches up to four kinds of file:

- `src/content/posts/<slug>.md` — the body markdown from the doc.
- `styles/generated.css` — CSS regenerated from the `styling` tab.
- `styles/anchors.yaml` — paragraph-to-class assignments (Implementation A).
- `styles/anchors_review.yaml` — only present when the run flagged something.

The PR body shows the Call 4 verdict: `auto_merge_ok`, any concerns, and
whether any upstream call exhausted retries. If `safe_to_auto_merge: true` and
you've set `sync.auto_merge = true`, GitHub will auto-merge after CI; otherwise
the PR sits open until you click merge.

## Local development

```sh
uv sync                              # Python deps
yarn install                         # JS deps
yarn dev                             # Astro dev server (port 4321 by default)
uv run python -m sync                # Run a sync locally against your gdoc auth
```

You need a working local `gdoc` install (`uv tool install git+https://github.com/LucaDeLeo/gdoc.git` and a one-time `gdoc auth`) plus an `ANTHROPIC_API_KEY` in `.env`. See `.env.example` for the full list.

## Changing the cron

The cron expression lives in **two places** that must match:

1. `[sync].cron` in `project.toml` — read by the pipeline at runtime.
2. The `schedule.cron` line in `.github/workflows/sync.yml` — read by GitHub at workflow load time.

Change both, commit, push. GitHub picks up the new schedule on the next push to the default branch.

## Troubleshooting

- **`gdoc cat` fails with `invalid_grant`** — the OAuth refresh token rotated out. Re-run `gdoc auth` locally, re-encode `token.json` to base64, update the `GDOC_TOKEN_JSON_B64` secret.
- **Anthropic 429 / 529** — back off and rerun; cron's next tick usually clears it. Costs > `anchoring.max_cost_usd` exit non-zero by design.
- **Astro build serves stale paragraph classes** — the data-store cache at `node_modules/.astro/data-store.json` doesn't track `styles/anchors.yaml` changes; the sync pipeline invalidates it on anchor rewrites, but if you're poking files by hand, delete that file before `yarn build`.
- **PR didn't open after a successful sync run** — check the `sync-diagnostics-<run-id>` artifact on the run; the most common cause is the sync detecting no changes (logged as `Sync produced no file changes`).
