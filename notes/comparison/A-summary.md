# Implementation A — branch summary

## 1. What this branch is

Implementation A — fuzzy anchors + Claude reviews the diff every sync.
Built per `PLAN.md` §3.A; final state on branch `feat/impl-a-anchors`
after Phases 1–5. The differentiator from Implementation B is the
persistent, mechanically-inspectable `styles/anchors.yaml` artifact:
one YAML entry per styled paragraph, each carrying a fuzzy
fingerprint (`quote.exact`, optional prefix/suffix, heading, ordinal,
content hash) and the CSS class to apply.

## 2. Pipeline shape

```
+--------------------+      +----------------------+
| cron / dispatch    | ---> | sync.fetch           |
| (GH Actions)       |      |  - drive version     |
+--------------------+      |    probe (no-op on   |
                            |    unchanged)        |
                            |  - gdoc cat body     |
                            |  - gdoc cat --tab    |
                            |    styling / library |
                            +----------+-----------+
                                       |
                                       v
                            +----------------------+
                            | sync.anchors         |
                            |  fuzzy_match_        |
                            |  candidates (dmp)    |
                            +----------+-----------+
                                       | hints
                                       v
+----------------------+    +----------------------+
| sync.css_gen         |    | sync.para_style_a    |
| CALL 1               |    | CALL 2               |
| Claude -> CSS        |    | Claude -> anchors    |
| validators + review  |    | validators + review  |
| pass; <=3 attempts   |    | pass; <=3 attempts   |
+----------+-----------+    +----------+-----------+
           |                           |
           v                           v
   styles/generated.css         styles/anchors.yaml
           |                           |
           +-------------+-------------+
                         |
                         v
            +-----------------------+
            | sync.diff_review      |
            | CALL 4                |
            | Claude -> verdict     |
            | { auto_merge_ok,      |
            |   concerns[] }        |
            | <=1 retry             |
            +-----------+-----------+
                        |
                        v
            +-----------------------+
            | astro build           |
            |  remark-spans         |
            |  remark-anchors       |
            +-----------+-----------+
                        |
                        v
            +-----------------------+
            | force-push sync/      |
            | pending branch +      |
            | edit-or-open PR +     |
            | Vercel preview        |
            | auto-merge gate (opt) |
            +-----------------------+
```

LLM calls in this branch: **Call 1 (CSS gen)**, **Call 2 (anchors
reconciler)**, **Call 4 (diff review / auto-merge gate)**. **Call 3 is
not present — that's Implementation B's path.** Every call is a
bounded transform per PLAN §7.1: known inputs in, structured output
out, deterministic validators in the orchestrator, bounded retry with
failures folded back into the prompt.

## 3. What lives where (file map)

| File | Role |
|---|---|
| `sync/fetch.py` | `gdoc cat` body + `--tab` styling/library, span-escape unescape, Drive version probe + state tracking, write post markdown |
| `sync/css_gen.py` | Call 1 — prose styling tab → `generated.css`; tinycss2 validators, optional review pass, retry ≤ 3 |
| `sync/para_style_a.py` | Call 2 — anchors reconciler; YAML/quote/hash/ordinal validators, optional review pass, retry ≤ 3 |
| `sync/diff_review.py` | Call 4 — auto-merge verdict; schema validator, 1 retry, defaults `auto_merge_ok=false` on exhaustion |
| `sync/anchors.py` | Anchor / Quote / Paragraph dataclasses, paragraph parser, paragraph hash, diff-match-patch fuzzy matcher, YAML load/save |
| `sync/llm.py` | Anthropic SDK wrapper (`call_claude`, `estimate_cost_usd`) — direct SDK only, no `claude -p` |
| `sync/config.py` | `project.toml` schema + loader, startup validation |
| `sync/__main__.py` | Orchestrator: load creds → probe Drive → fetch → Call 1 → Call 2 → invalidate Astro cache → Call 4 → write `.sync-verdict.json` → save state |
| `styles/anchors.yaml` | **The differentiating artifact.** One entry per styled paragraph; the file a human inspects to audit class assignments |
| `styles/generated.css` | Output of Call 1; normalised, byte-stable across unchanged runs |
| `styles/manual.css` | Hand-written override layer (priority above generated) |
| `src/plugins/remark-spans.ts` | `<tag>text</tag>` → `<span class="tag">text</span>` (shared with B) |
| `src/plugins/remark-anchors.ts` | **A-only.** Reads `anchors.yaml`, attaches `className` on paragraph wrappers identified by `(heading, ordinal)` with quote-substring verification |
| `astro.config.mjs` | Wires both remark plugins |
| `src/content/posts/` | Markdown destination for the synced doc body |
| `.github/workflows/sync.yml` | Cron + `workflow_dispatch` driver, secret planting, fixed `sync/pending` branch, edit-or-open PR, auto-merge gate |
| `tests/test_anchors.py` | Unit tests for paragraph parser, hash, fuzzy matcher, YAML round-trip |
| `tests/test_para_style_a_validators.py` | Unit tests for the Call 2 deterministic validators |
| `tests/test_css_gen_validators.py` | Unit tests for the Call 1 deterministic validators |
| `tests/test_diff_review_validators.py` | Unit tests for the Call 4 schema validators |
| `tests/test_fetch_unescape.py` | Unit tests for the gdoc span-escape regex |
| `tests/test_fixtures.py` | Day1 + day2 fixture snapshot harness (PLAN §9.1) |
| `tests/fixtures/day1/`, `tests/fixtures/day2/` | Fixture corpus + hand-authored goldens |
| `tests/remark-spans.test.ts`, `tests/remark-anchors.test.ts` | Vitest tests for the plugins |
| `project.toml` | `[doc] implementation = "a"`, cron, fuzzy threshold, cost cap, deploy target |

## 4. The differentiating artifact

Implementation A's primary artifact is **`styles/anchors.yaml`** — a
hand-editable, mechanically inspectable file mapping paragraph
fingerprints (quote + heading + ordinal + hash) to CSS class names. A
human can open it and see exactly which paragraph got which class, and
why. The fingerprint is fuzzy enough to survive a typo fix without
human intervention (the diff-match-patch pre-pass relocates the
anchor; Call 2 confirms or revises), but every change passes through
Claude — there is no silent auto-apply.

Compare to Implementation B's `styling/decisions.md` — a
Claude-authored markdown narrative which is human-skimmable but less
mechanically inspectable. B has no anchors file at all: it re-decides
every paragraph's class each sync and uses the previous decisions file
as a soft prior in the prompt.

The shape of a typical `anchors.yaml` entry:

```yaml
paragraphs:
- class: feature-quote
  anchor:
    quote:
      exact: It turns out the slowness was load-bearing.
    heading: Background
    ordinal: 4
    hash: 67365bfa
```

A reviewer can scan this in one pass: every entry says "I put class X
on paragraph N under heading Y, identifiable by this substring." A
mis-applied class jumps out instantly. The same information in B's
`decisions.md` reads as prose: "Styled as **feature-quote** because
the paragraph reads as a single declarative idea pulled out for
emphasis…" — easier to read, harder to grep, harder to diff.

## 5. Cost characteristics

From the Phase 2 and Phase 4a smoke runs against the real source +
library Google Docs (claude-sonnet-4-6 production model, $3/MTok
input + $15/MTok output):

| Call | Smoke cost | What dominates |
|---|---|---|
| Call 1 (CSS gen) | ~$0.037 (3 + 3 review-pass attempts on a genuinely-ambiguous styling tab; first-attempt cost ~$0.01) | styling tab + library size; one pass is typical, retries fire when the reviewer flags real contradictions |
| Call 2 (anchors) | ~$0.014 per sync (single attempt, validators clean, review clean) | new doc size × number of paragraphs the reconciler considers |
| Call 4 (diff review) | ~$0.005 per sync (small diff, single call, no retry) | scales linearly with diff size + artifact size |

Total typical sync: **well under $0.10** on the smoke doc, well within
the `[anchoring].max_cost_usd = 1.00` cap. The cost cap is enforced
after Call 1 and again after Call 2; Call 4 (the gate) is allowed to
overflow with a logged warning rather than aborting, because the gate
has already informed the verdict by the time it lands.

Cost growth profile as a doc gets bigger:

- **Call 1** scales with **styling tab size**, not doc body size. Re-runs are rare (only when the styling tab or library actually change).
- **Call 2** scales with **doc body size × number of anchored paragraphs**. The diff-match-patch pre-pass keeps the prompt focused: only the prior anchors and their fuzzy candidates land in the prompt, not the whole previous doc.
- **Call 4** scales with **diff size + artifact size**. Bigger edits cost more here.

## 6. Known trade-offs

**Pros:**
- `anchors.yaml` is mechanically inspectable. A human reading the diff
  on a PR sees exactly which paragraph got which class.
- Smaller per-sync LLM context — Call 2 sees the diff + the prior
  anchors + fuzzy candidates, not the whole previous doc.
- Deterministic fuzzy matcher handles minor edits without bothering
  the LLM with a search problem. The LLM is the decider but doesn't
  have to scan the whole doc for candidates.
- Easy to hand-edit anchors in an emergency: the file's schema is
  small, the failure modes are obvious (orphaned anchor, hash drift),
  and the validator is honest about what it expects.

**Cons:**
- More moving parts than B. Fuzzy matcher + Claude + validators is
  three components to debug vs B's single Claude call + validator.
- Harder to extend to per-sentence styling — anchors target whole
  paragraphs and `(heading, ordinal)` is the unique key. A per-sentence
  affordance in A would need a second axis in the schema.
- When anchors orphan in confusing ways (e.g. a paragraph rewritten
  beyond recognition), the YAML diff can be cryptic. B's
  `decisions.md` narrative may be easier to skim in that scenario,
  even if it's harder to diff line-by-line.
- The fuzzy matcher's pre-pass adds a layer of "did the matcher hint
  the LLM right?" that doesn't exist in B. When something goes wrong,
  the question "was it the matcher or the model?" has to be answered.

## 7. What to compare against B

A list of questions a human should be able to answer in 15 minutes of
skimming once both branches are pushed:

1. **Styling-fidelity parity on the same source.** Run both branches
   against the same fixture (`tests/fixtures/day1/doc.md` is a
   reasonable target). Diff the rendered HTML class assignments.
   Where do they disagree? Is one consistently more conservative
   (skipping a class) or more aggressive (adding a class)?
2. **Audit clarity after a week of edits.** Imagine seven daily syncs
   with the four edit kinds from `tests/fixtures/day2/notes.md`
   mixed in. After those seven days, which artifact is easier to
   skim — A's YAML diffs (`anchors.yaml` line-by-line) or B's prose
   narrative (`decisions.md` as a single growing document)?
3. **Daily Anthropic cost comparison.** B reads the full doc + the
   full prior `decisions.md` every sync. A reads the diff + the prior
   anchors + the fuzzy candidates. On a 5000-word doc with a 2000-word
   styling tab, what does the daily cost difference look like?
4. **Failure modes on a rewritten paragraph.** When a paragraph is
   rewritten beyond what the fuzzy matcher can re-match, which
   branch handles it more gracefully? A's path: Claude sees the
   orphan candidate and decides whether to re-attach or drop. B's
   path: Claude doesn't know the paragraph was previously styled
   unless `decisions.md` happens to reference its old text.
5. **First-time-author surface area.** Which artifact does a new
   author have to learn about first? `anchors.yaml`'s schema is
   small but unfamiliar (quote.exact, ordinal, hash); `decisions.md`
   is "just a markdown file" but its conventions are looser.
6. **Auto-merge confidence.** Call 4's verdict is the same call in
   both branches. Does the upstream artifact (anchors.yaml vs
   decisions.md) change Call 4's accuracy?

## 8. Commit log (this branch since `main`)

Grouped by phase. Each group lists commits in chronological order
within the phase.

### Pre-roadmap (planning artifacts)

- `ffaa4be` chore: add project config
- `5c21807` docs: add PROJECT.md
- `664bf85` research: add stack, features, architecture, pitfalls, and summary
- `78533b6` docs: add REQUIREMENTS.md
- `5a24eaa` docs: add ROADMAP.md and STATE.md

### Phase 1 — Foundations

- `5f9fc6a` feat: scaffold Astro v5 site with content collections
- `3c0a4cb` feat: add project.toml schema + Python config loader
- `0539b8e` chore: add placeholder post and mark Phase 1 complete

### Phase 2 — Fetch + CSS pipeline

- `c6484d0` feat(sync): add fetch.py + drive version probe + state tracking
- `aaeecbc` feat(sync): add llm.py + css_gen.py with bounded transform + validators
- `1ce4710` feat(sync): add __main__.py entry point + integration smoke
- `472aea8` test: CSS generator validator unit tests
- `9422d4b` chore(sync): commit smoke-run artefacts (generated.css, hello.md, state)
- `5970c76` docs(planning): mark Phase 2 complete in ROADMAP + STATE

### Phase 3 — Span plugin

- `cede8f8` docs(notes): empirically verify gdoc span-tag escaping behavior
- `83911f7` feat(sync): unescape span tags in fetch.py after gdoc export
- `2273a19` feat(plugin): add remark-spans plugin for <tag>text</tag> → <span class="tag">
- `c2138ec` feat(astro): wire remark-spans into astro.config.mjs
- `2499801` test(plugin): vitest tests for remark-spans transformation
- `0a78dfd` docs(planning): mark Phase 3 complete in ROADMAP + STATE

### Phase 4a — Implementation A (anchors)

- `86e3ac7` feat(sync): add anchors data model + paragraph parser + fuzzy matcher
- `0614505` feat(sync): add para_style_a.py Call 2 reconciler with bounded transform + validators
- `d0d6f67` feat(plugin): add remark-anchors plugin to inject classes on paragraph wrappers
- `4cbcf7e` feat(sync): wire para_style_a into __main__.py pipeline
- `f0b9b7a` feat(astro): wire remark-anchors into config
- `d5c3d27` chore(sync): invalidate astro data-store cache + commit initial anchors.yaml
- `0800655` docs(planning): mark Phase 4a complete

### Phase 5 — CI/CD + PR flow

- `41a4bc0` feat(sync): add diff_review.py — Call 4 final gate
- `b02089d` feat(sync): integrate Call 4 verdict + retry-exhaustion tracking in __main__.py
- `c04d47f` feat(ci): add .github/workflows/sync.yml cron + PR workflow
- `dc9a18f` docs: add README.md 15-minute setup guide
- `af17560` chore: add .sync-verdict.json to .gitignore
- `686ae80` test: pytest validators for Call 4 JSON schema
- `58fd5bc` docs(planning): mark Phase 5 complete

### Final — fixtures + comparison

- `66ec2e2` test(fixtures): add day1 + day2 fixture corpus per PLAN §9.1
- `30d999b` test: add tests/test_fixtures.py snapshot harness
- (this commit) docs(comparison): add A-summary.md
