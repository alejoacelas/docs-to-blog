# docs-to-blog · Implementation Plan

System: Google Doc → daily-synced static blog with per-paragraph and per-span CSS overrides, defined partly in prose (in a Doc tab) and partly in a repo sidecar.

This plan locks the author-facing surface and stages two competing implementations for the parts we still want to test side by side.

> **PLAN.md is the only authoritative document for this build.**
> Files under `notes/` are intermediate research outputs from earlier exploration; they may contradict this plan and **must not be relied upon** as a source of truth. Cite them only when explicitly useful.
> Files under `demo/` are a one-shot visual mockup produced *before* the A/B split and the HTML-tag span syntax; **do not reproduce its colors, fonts, sample content, or bracket-span notation**. Visual design lives in the `styling` tab and library doc instead.

---

## 0. Prepared resources

These are already provisioned and authenticated on the machine running the build. The implementation must consume them rather than mock anything; **if any is missing at runtime, exit non-zero** — do not fall back to stubs or sleep.

| Resource | Where | Used by |
|---|---|---|
| Source Google Doc (body tab + `styling` tab) | `https://docs.google.com/document/d/1qAD1VRFk4VkfmMM3AnDDH1LUqe_O6PrrzSfGOlLVbPQ/edit` — mirrored as `DOC_URL` in `.env` and `[doc].url` in `project.toml` | `scripts/pull.ts`, `scripts/pull-tab.ts` |
| Library Google Doc (gallery body + `styling` tab) | `https://docs.google.com/document/d/1sPikfxprgeHnrDd9TINgzN3NHqsc3b7xZbPWg2h-Vrw/edit` — mirrored as `LIBRARY_DOC_URL` and `[doc].library_url` | `scripts/pull-library.ts` |
| `gdoc` OAuth token + client | `~/.config/gdoc/token.json` (refresh-token-bearing); `~/.config/gdoc/credentials.json` (OAuth client) | local `gdoc cat`; CI restores from base64 secrets `GDOC_TOKEN_JSON_B64` + `GDOC_CREDENTIALS_JSON_B64` |
| `ANTHROPIC_API_KEY` | `~/.config/credentials/.env` (global) and `.env` (project, gitignored); CI repo secret of the same name | Anthropic SDK calls in the LLM steps (see §7) |
| `gh` CLI auth | macOS keychain (account `alejoacelas`), scopes `repo`, `workflow`, `gist`, `read:org` | repo provisioning, PR opening |
| GitHub repo | Provisioned during pre-flight; remote is `origin`. | source of truth for `main`, sync PRs, and CI |
| Vercel project | Linked to the GitHub repo; Astro framework preset; production branch = `main`. Env vars: `ANTHROPIC_API_KEY` (+ P7 adds `GITHUB_PAT`, `UPDATES_PASSWORD`). | the deploy step in the daily sync, plus the action API routes added in P7 |
| `project.toml` | repo root, committed | every pipeline script — doc URLs, cron, fuzzy threshold, cost cap, implementation toggle |
| `.env` (local, gitignored) | repo root | local-dev shorthand so scripts find creds without re-grepping the global file |
| `.env.example` (committed) | repo root | documents the env-var contract for collaborators |

---

## 1. Design decisions (locked)

| Decision | Choice | Rationale |
|---|---|---|
| Bundle | **3 + 4 hybrid** | Sidecar + Claude (3) for paragraph styling; `styling` Doc tab + Claude-generates-CSS (4) for the styling vocabulary. |
| Website stack | **Astro v5** | Best per-paragraph styling story via custom remark plugin; consumes generated markdown cleanly; grows beyond a blog. |
| Markdown source | **`gdoc cat` for the doc body**, **direct Docs API for tabs/comments** | gdoc CLI markdown export is rich for body; tab-scoped export is plain text only, so we bypass it. |
| Change detection | **Drive `files.get(version)` integer** | Monotonic, cheap. |
| Span syntax | **HTML-style paired tags** in the source prose: `<aside>...</aside>` | Tag name = style name. No anchoring needed: the markup is intrinsic to the source. |
| Paragraph styling | **Prototype two implementations, A and B** (see §3) | We don't yet trust fuzzy-only matching, and we don't yet trust Claude-only matching. Build both, compare on real edits. |
| Reconciler trust | **Claude reviews the diff every sync** in both A and B | No silent auto-apply — even in A, Claude is not an orphan-only fallback; it sees every change between sync N-1 and N. |
| Per-sentence styling | **Out of scope for v1** | Use span tags instead. |
| LLM execution model | **Every LLM step is a bounded transform** | Known inputs in, structured output out. No agent loop inside any call, no tool use mid-generation. The orchestrator runs deterministic validators + optional review-pass calls in a bounded retry loop in our code, not inside an agent. Specific SDK/library is implementation-level. See §7. |
| Runner | **GitHub Actions on a configurable cron, driving a small script** | Default interval 60 minutes, set in `project.toml`. Free runner; has Python for `gdoc`, has `git`, has HTTPS to `api.anthropic.com`. |
| Auth in CI | **`token.json` planted from base64 secret** | gdoc CLI's OAuth refresh-token flow works in Actions. |
| Deploy | **Vercel** (hobby tier). Main site, previews, and the `/updates` page are all sub-paths of one Astro project; action endpoints colocate as serverless functions. | One platform hosts the static site and the API routes; secrets live in Vercel project env; no separate Worker or CORS to manage. Each open `sync/*` PR also gets a full preview build at `/preview/<slug>/` (P7). |
| Review surface | **`/updates` page on the deployed site**, password-gated; action endpoints are Astro API routes deployed as Vercel serverless functions. | Author reviews and accepts changes on the live site. The author never has to open GitHub. See §8. |
| Change-record policy | **Every change lands as a discrete, well-scoped commit; author approves before it publishes** | The commit history is the audit trail; the click on `/updates` is the action. How pending changes are *held* before approval — a PR, a `sync/*` branch, a drafts directory on `main` — is an implementation choice; PRs are a reasonable default but not required. Auto-merge (skipping the human gate) on Call 4's `auto_merge_ok = true` is opt-in per project in `project.toml` for trusted runs. |

---

## 2. Affordances (the author's full surface area)

These are everything the author can do to control how their writing is styled. Anything not listed here is not yet supported.

### A. Source-of-content affordances (in the Google Doc body)

| # | Affordance | What it looks like in the doc | Effect |
|---|---|---|---|
| A1 | **Plain prose** | Just write. Headings, paragraphs, footnotes, links, lists, tables. | Renders as the page body. Default. |
| A2 | **Span tag** | `This is a <aside>really important</aside> point.` | Wraps the span in `<span class="aside">…</span>`. Tag name = style name. |
| A3 | **Footnotes** | Standard Google Docs footnotes. | Exported as Pandoc `[^n]`; rendered with anchors and backlinks. |

> **Important:** paragraphs are *not* tagged in the source. Whether a given paragraph becomes an `aside`, a `feature-quote`, etc. is decided *outside* the source text. The two candidate mechanisms for that decision are §3.A and §3.B.

### B. Source-of-styling affordances

| # | Affordance | Where it lives | What it controls |
|---|---|---|---|
| B1 | **`styling` Doc tab** | A separate tab inside the project's main doc, titled `styling`. | Prose descriptions of project-specific tags + page-level style direction. |
| B2 | **Library doc** | A separate Google Doc, itself a project with a body tab (gallery) and a styling tab. URL referenced in `project.toml`. | Reusable named styles, demonstrated in the body and defined in the styling tab. |
| B3 | **Paragraph-styling artifact** | In the git repo. | Per-paragraph style assignments. *Exact shape depends on which implementation (A vs B) is selected — see §3.* |
| B4 | **Generated CSS** `styles/generated.css` | In the git repo, regenerated by Claude when the styling tab or library change. | Actual CSS rules. Hand-overrides live in `styles/manual.css`. |
| B5 | **`project.toml`** | In the git repo. | Config: doc URL, library doc URL, cron timing, auto-merge, `implementation = "a" | "b"`. |
| B6 | **`/updates` page** | On the deployed site, password-gated. | Review pending previews, accept or reject them, force a "check now" run. See §8. |

### C. Style-resolution hierarchy (highest priority first)

1. **Hand-edited rules** in `styles/manual.css`.
2. **Project `styling` tab** — overrides for `foo` specific to this project.
3. **Library doc** — the canonical definition of `foo`.
4. **Fallback** — unknown class → no styling, build warning.

### D. Affordances explicitly NOT in v1

- Per-sentence styling (use span tags instead).
- Inline HTML / MDX components in the body, other than recognised span tags.
- Real-time webhook rebuilds (cron-only for now).
- Custom paragraph styles defined inside Google Docs (named styles, character styles).
- Unnamed/bare span wrappers — every styled span must name its style.

---

## 3. Two implementations to prototype (A and B)

The hard problem: how does a plain-prose paragraph become "the callout"? The source doesn't mark it. We have two candidate solutions and want to build both so we can compare on real edits.

### Implementation A — Anchors + Claude reviews the diff

- A repo file `styles/anchors.yaml` records, for each styled paragraph: a fuzzy fingerprint of the paragraph (a quote span, the heading it sits under, its ordinal, a content hash) and the class to apply.
- **First sync of a doc:** Claude reads the doc + the styling tab, proposes initial anchors, and writes them.
- **Every subsequent sync:** Claude is given (prev doc, new doc — or the diff, prev `anchors.yaml`). It updates anchors holistically: it can rewrite, delete, or add entries based on what changed. There is no silent orphan-fixing — every change passes through Claude.
- A fuzzy matcher (diff-match-patch) runs as a pre-pass to surface candidate matches cheaply; its output is fed into Claude's prompt as a hint. Claude is the decider.
- At build time, the Astro plugin reads `anchors.yaml` and attaches `className` to matched paragraphs.

Why prototype this: anchors are an inspectable, hand-editable artifact. A human can open `anchors.yaml` and see exactly which paragraph got which class. Smaller per-sync LLM context (diff + anchors, not the whole doc).

### Implementation B — Claude decides every sync, decisions file as audit

- No `anchors.yaml`. Every sync, Claude reads the full new doc + styling tab + library + previous `styling/decisions.md`, and produces:
  - A styled-markdown intermediate (the doc, with class hints attached to paragraphs and `<span class="…">` for span tags), and
  - An updated `styling/decisions.md` — a markdown narrative, one entry per styled element: *"I styled the paragraph beginning 'When we first…' as `aside` because the styling tab calls asides reflective tangents."*
- The decisions file is the audit trail. Claude maintains it; the author rarely opens it but can.
- At build time, the Astro plugin reads the styled-markdown intermediate.

Why prototype this: simpler model — no fuzzy matching to debug. The decisions file is human-readable by construction. Trade-off: higher per-sync LLM cost (full doc in context) and a less mechanically inspectable artifact.

### What's identical in both

- The `styling` tab and library doc (same author-facing schema).
- The span affordance (`<aside>text</aside>`).
- The generated-CSS pipeline.
- The PR-on-change workflow.
- The author's experience until PR review. The difference is what shows up in the diff.

### Choosing later

Both are built behind a `project.toml` toggle. Same fixtures, side-by-side comparison, decision in v1.1 after dogfooding. P4a and P4b are independent and meant to be dispatched to separate agents in parallel.

---

## 4. The `styling` tab — author-facing schema

Free prose with a few light conventions. Example:

```
# styling

## Global
Personal essay. Lean literary. Warm cream background, deep brown text, soft gold
accent. Body in a serif (Iowan Old Style / Charter), max width 65ch.

## Tags

**aside** — a reflective tangent. Indented from the left, italic, slightly smaller
than body. Use for the kind of thought the author wants to whisper rather than
declare.

**feature-quote** — a single line or sentence pulled out for emphasis. Large
serif, ~1.4× body, soft gold rule below.

**spaghetti-italics** — uses the library definition (see "Default styles" doc).
Slightly tighter letter-spacing in this project than the library default.
```

Conventions:
- `## Global` → page-level CSS direction.
- `## Tags` heading, then `**name**` lines define or override named styles.
- A tag that mentions "uses the library definition" delegates to the library; any
  extra description is treated as override on top of the library version.
- Plain English. No CSS knowledge required.

---

## 5. The library doc — gallery shape

The library is itself a Google Doc with the same two-tab shape as a project: a **body tab** (a gallery / instruction manual) and a **styling tab** (definitions).

The body tab demonstrates each style in context:

```
# Default styles — gallery

## aside

Asides are for reflective tangents. Here is what one looks like:

<aside>The author pauses to wonder whether anyone is still reading. Asides like this
one are quiet, intimate; they hold open a door to the reader without insisting.</aside>


## feature-quote

Feature-quotes pull a single sentence out for emphasis. Here is what one looks like:

<feature-quote>If anchors are a fingerprint, decisions are a confession.</feature-quote>


## spaghetti-italics

Spaghetti-italics is a span style for conversational asides inside a paragraph.
Here it is in context:

A short paragraph for context, and then <spaghetti-italics>this little
flourish</spaghetti-italics> right in the middle of it.
```

The styling tab uses the same schema as a project's styling tab, minus `## Global` (libraries don't dictate page-level layout).

Lives in a Google Doc the author owns; URL referenced in `project.toml`. Multiple projects share the same library doc.

---

## 6. The paragraph-styling artifact

### 6.A `styles/anchors.yaml` (Implementation A)

```yaml
paragraphs:
  - class: feature-quote
    anchor:
      quote: { exact: "...", prefix: "...", suffix: "..." }
      heading: "Why"
      ordinal: 2
      hash: "9a44e1d2"
  - class: aside
    anchor: { ... }
```

### 6.B `styling/decisions.md` (Implementation B)

```markdown
## aside — paragraph 4 under "Why"

> "When we first sketched the system on a napkin, the anchors were an
> afterthought. Now they're the load-bearing piece."

Styled as **aside** because this paragraph is a reflective look back at the
design process, and the styling tab defines `aside` as a reflective tangent.

## feature-quote — paragraph 1 under "Conclusion"
…
```

Markdown narrative chosen over structured YAML because the file's job is to be human-skimmable — Claude is already the writer and the reader. (Open question §11.5.)

---

## 7. LLM calls and the daily sync pipeline

Every LLM step is a **bounded transform** — known inputs in, structured output out. No agent loop inside any call, no tool use mid-generation. All looping happens in the orchestrator, where it's fully inspectable. The SDK/library used to invoke Claude is implementation-level; the constraint is the shape.

### 7.1 Shape of every LLM call

1. The orchestrator assembles the call's inputs from disk. No exploration.
2. It calls Claude once.
3. **Deterministic validators** check the output (parse, schema, coverage, sanity).
4. Optionally, a **review pass** — a second Claude call playing reviewer — checks soft properties that can't be expressed in code (intent preservation, stylistic consistency, agreement with the prose spec).
5. If any check fails, the failing checks + the prior output are folded back into the prompt and the call is retried, bounded by max attempts.
6. After max attempts: the orchestrator commits the last attempt anyway, opens the PR with a `needs-attention` label and a summary of the failing checks, and **never auto-merges** for that run.

The model is invoked only where input is genuinely fuzzy. Anything mechanisable — fuzzy paragraph matching, CSS parsing, YAML schema, hashes, ordinals, markdown parsing — stays as plain code and either pre-runs to produce inputs for a call or post-runs as a validator.

### 7.2 The LLM-driven work in v1

The fuzzy work decomposes into the jobs below. The four-call split is one reasonable shape — an implementer may fold the optional review-pass into the main call as self-critique, split a job into a candidate-and-verify pair, or merge two jobs whose inputs overlap. What must hold for each job: known inputs in, structured output out, deterministic validators that can reject, bounded retry that feeds failures back into the prompt. The per-call detail below is the *kind* of inputs/outputs/checks we want — not a literal API contract.

**Call 1 — CSS generator.** Turns the prose definitions in the project `styling` tab (plus inherited library definitions) into `styles/generated.css`.

- *Inputs.* Project styling tab text; library styling tab; existing `styles/manual.css` (so the generator doesn't duplicate or conflict with hand-written rules); previous `styles/generated.css` (so unchanged rules stay byte-stable).
- *Output.* New `styles/generated.css`.
- *Deterministic validators.* Parses as CSS; every named tag in the styling tab has a rule; no rules for tags absent from styling tab + library; class names match `[a-z][a-z0-9-]*`; no `@import` of external URLs.
- *Review pass.* A second Claude call sees the prose definitions and the generated CSS; flags any tag whose CSS contradicts or omits a property the prose explicitly named.

**Call 2 — Paragraph-styling reconciler, Implementation A.** Updates `styles/anchors.yaml` to reflect the new doc, given what changed since last sync.

- *Inputs.* Previous doc body; new doc body; current `anchors.yaml`; styling tab; library styling tab; the fuzzy matcher's candidate matches for each existing anchor (as a hint, not a directive).
- *Output.* New `anchors.yaml`.
- *Deterministic validators.* Parses as YAML; every class referenced is defined in the styling tab or library; every `quote.exact` is a verbatim substring of the new doc; every `ordinal` is reachable (the Nth paragraph under that heading exists); `hash` matches the matched paragraph.
- *Review pass.* A second Claude call sees (prev doc, new doc, prev anchors, new anchors) and flags (a) any previously styled paragraph that still exists in some form and silently lost its class, and (b) any class applied to a paragraph that doesn't match the style's prose description in the styling tab.

**Call 3 — Paragraph-styling reconciler, Implementation B.** Produces the styled-markdown intermediate and the updated `styling/decisions.md`.

- *Inputs.* New doc body; styling tab; library; previous `decisions.md`.
- *Output.* Styled markdown (doc body with class hints attached) + new `decisions.md`.
- *Deterministic validators.* Styled markdown parses; every class hint is defined in styling tab or library; every styled paragraph has a corresponding entry in `decisions.md`; every entry in `decisions.md` maps to a styled paragraph in the output.
- *Review pass.* A second Claude call sees (styling tab, library, new decisions.md) and flags entries whose stated reasoning is thin, contradictory, or unmoored from how the styling tab describes that class.

**Call 4 — Diff reviewer (final gate, both implementations).** Decides whether the run is safe to merge unattended.

- *Inputs.* Yesterday's full output (markdown + artifact); today's full output; styling tab; the source doc diff.
- *Output.* A structured verdict: `{ auto_merge_ok: bool, concerns: [string] }`.
- *Deterministic validators.* Output parses as the expected schema.
- *No nested review pass.* This *is* the review pass for the pipeline as a whole.
- *Retries.* 1 only. If a clean verdict can't be produced, the orchestrator defaults `auto_merge_ok = false` and lets the human decide.

Calls 1–3 retry up to 3 attempts each. Each retry receives the previous attempt's output plus the concrete list of failed validators and reviewer complaints, framed as *"your previous attempt had these issues; produce a corrected version."*

### 7.3 What is *not* an LLM call

- Fuzzy paragraph matching (Implementation A): `diff-match-patch` in plain code. Its output is an *input to* Call 2, not a tool Call 2 invokes.
- CSS parsing, YAML schema validation, hash computation, ordinal counting, markdown parsing: stdlib or off-the-shelf libraries.
- The auto-merge decision itself: the orchestrator combines Call 4's verdict with whether any upstream call exhausted retries.

### 7.4 The daily sync, end to end

Cron interval is configurable (`[cron].interval_minutes` in `project.toml`, default 60). Each tick:

```
1. Probe Drive version. If nothing changed: exit 0.

2. Pull doc body, styling tab, library doc into the repo.

3a. (Implementation A) Run fuzzy matcher → candidate matches.
    Invoke Call 2 → new anchors.yaml.

3b. (Implementation B) Invoke Call 3 → styled markdown + new decisions.md.

4. If styling tab or library changed: invoke Call 1 → new generated.css.

5. Astro build → final HTML. (P7 adds: also build /preview/<slug>/
   for every open sync/* PR — see §8.1.)

6. Invoke Call 4 → verdict. If anything changed: stage the change for
   review (e.g. open a PR, push a sync branch, write a drafts entry).
   v1: the author reviews wherever the change is staged (GitHub PR UI
   is a reasonable default) and accepts it there.
   P7: the author reviews on /updates and clicks Accept to publish (§8).
   Auto-merge (skipping the human gate) is opt-in per project.toml AND
   requires Call 4 returned auto_merge_ok=true AND no upstream call
   exhausted retries.
```

In P7 the same workflow is also fired by the "Check now" button on `/updates`, so authors editing the styling tab iteratively don't have to wait for the next cron tick. In v1, only cron + `workflow_dispatch` trigger runs.

---

## 8. The updates page and review flow

The author reviews changes on the deployed site, not in GitHub. The PR is the commit mechanism; the website is the UX.

### 8.1 What lives on the deployed site

The Astro build emits three categories of output:

- `/` and child paths — the current published content, built from `main`.
- `/preview/<slug>/...` — one full preview build per pending change. Each preview is the whole site as it would be if that change were accepted. Slug is unguessable.
- `/updates` — a single page listing pending changes, with action buttons.

Every build emits a preview alongside main for each pending change. How pending changes are stored (PRs, `sync/*` branches, a drafts directory) is an implementation choice; the previewer enumerates them and applies their artifacts (`anchors.yaml` or `decisions.md` + styled markdown). Builds are triggered by pushes to `main`, by cron, and by the "Check now" button.

### 8.2 The `/updates` page contract

The page loads as static HTML, prompts for a password on first visit (stored in `localStorage`), and then talks to the action API (§8.4) for data and actions.

For each tracked document, it shows:

- last-synced Drive version
- latest-known Drive version (refreshed when the page loads, and when the user clicks "Check now")
- the list of pending changes for this doc, each annotated with: created timestamp, a one-line summary of the styling delta (which classes changed on which paragraphs), the run's verdict (from the final-gate LLM job — Call 4 in §7) including any concerns, and a link to its preview

Per pending preview, three buttons:

- **Open preview** → opens `/preview/<slug>/` in a new tab.
- **Accept** → publishes the pending change via the action API. The next build promotes the preview to `/`; the preview slug disappears.
- **Reject** → discards the pending change. The preview slug disappears on the next build.

One global button:

- **Check now** → fires the pipeline immediately against the latest Drive state. Same effect as a cron tick; if nothing changed, no-op. This is the iteration button used after editing the styling tab.

### 8.3 Cron's role with the updates page

Cron runs the pipeline on its interval whether or not the author is looking. So when the author opens `/updates` in the morning, any doc edits made since the last visit already have previews waiting. The author never *has* to wait for cron, because Check now does the same work on demand.

### 8.4 The action API

The `/updates` page calls into a small action API hosted alongside the site as Astro API routes (Vercel serverless functions, same project, same domain, no separate service). The operations the API must expose:

- **list pending** → manifest of pending changes per doc. Source of truth for `/updates`'s table.
- **accept(id)** → publish a pending change (merge PR, fast-forward branch, or promote drafts — whichever mechanism the implementation uses for §1's change-record policy).
- **reject(id)** → discard a pending change.
- **check now** → trigger the sync pipeline against the latest Drive state.

All endpoints require an auth header matching the `UPDATES_PASSWORD` env var. Whatever credential is needed to act on pending changes (e.g. a fine-scoped `GITHUB_PAT` if changes live as commits in this GitHub repo) is server-side only; the browser never sees it.

### 8.5 What's not in v1

- Per-paragraph in-line accept/reject. Unit of review is the whole PR.
- Public previews behind hard auth. Slugs are unguessable but pages are not actively gated — acceptable for a personal blog. Vercel Authentication (or Cloudflare Access in front of the domain) is the v2 upgrade.
- Multi-author auth. Shared-password v1.
- Side-by-side preview diffing on the page. Open two tabs.

---

## 9. Testing plan

### 9.1 Fixture-driven snapshot tests
- `tests/fixtures/day1/` and `tests/fixtures/day2/`: pairs of (markdown, styling tab, library, expected HTML).
- Day 2 covers four edit kinds, asserting both implementations produce reasonable styled output:
  - Typo fix (1-word change).
  - Inserted paragraph (ordinals shift).
  - Rewritten paragraph that had a styled span.
  - Rewritten paragraph that was a callout.

### 9.2 Side-by-side comparison harness
- Run A and B against the same fixtures; diff their output. The diffs are the data that informs the v1.1 choice.

### 9.3 Integration with real services
- Manual end-to-end run against a real Google Doc + library doc.
- CI smoke: GH Action runs on `workflow_dispatch` against a small fixture doc.

### 9.4 Observability
- Every step emits structured JSON logs.
- Anchors diffs / decisions diffs are committed alongside the PR for audit.

---

## 10. Build phasing

| Phase | Output |
|---|---|
| **P1.** Astro skeleton + pull doc body + manual sidecar + manual CSS. | Working blog with no automation but with styling architecture in place. |
| **P2.** Pull styling tab + library + generate CSS from prose. | Styling vocabulary lives in Google Docs. |
| **P3.** Span tags end-to-end (parser + remark plugin). | `<aside>x</aside>` works. |
| **P4a.** Implementation A: anchors + Claude-reviews-diff. | Branch A shippable. |
| **P4b.** Implementation B: Claude-decides-every-sync + decisions file. | Branch B shippable. |
| **P5.** GitHub Actions cron + PR workflow + Vercel deploy of `main`. | Daily autonomous operation (on either branch). Review still happens in the GitHub PR UI in v1; the `/updates` page is P7. |
| **P6.** Comparison harness + dogfooding. Pick A or B. | v1.1 ready. |
| **P7.** `/updates` page + per-PR `/preview/<slug>/` builds + action API routes (§8). | Author reviews and accepts on the deployed site instead of the GitHub PR UI. Builds on the winning implementation from P6; orthogonal to the A-vs-B decision. |

P4a and P4b are independent — designed to be dispatched to separate agents in parallel. P7 is deferred until after P6 picks a winner.

---

## 11. Open questions

1. **Are headings within the `styling` Doc tab parsed by the Docs API the same as body headings?** Tabs are a relatively new API surface; verify before relying on `## Tags` as a section anchor.
2. **gdoc's footnote handling renumbers IDs to sequential `[^1]`, `[^2]`.** Does this matter for our renderer? Probably not.
3. **What's the Drive `version` rate-limit?** We poll once a day, but `workflow_dispatch` could trigger more often.
4. **Will Google Docs export preserve angle-bracket tags like `<aside>` cleanly?** They look like HTML. Verify gdoc's markdown export doesn't escape or strip them; if it does, fall back to a Pandoc-friendly notation that survives the round-trip.
5. **Decisions-file format for Implementation B** — markdown narrative (current default) or structured YAML with prose `reason` fields? Markdown reads better when humans peek; YAML is easier to query programmatically.
6. **Auto-merge default:** off for v1 (always PR). Revisit after a few weeks of operation.

---

## 12. Reference artifacts

- `notes/2026-05-12-options-synthesis.md` — the seven bundles and which we picked.
- `notes/2026-05-12-gdoc-cli-capabilities.md` — what the tools can do.
- `notes/2026-05-12-website-stack-survey.md` — why Astro.
- `notes/2026-05-12-styling-override-architecture.md` — anchor strategy.
- `notes/2026-05-12-automation-execution-model.md` — GH Actions + claude CLI.
- `demo/index.html` — visual walkthrough of the system (Day 1 → Day 2). Open with `python3 -m http.server` from `demo/`. **Note:** predates the A/B split and the HTML-tag span syntax; covers paragraph-level only and uses the older bracket-span notation. P3+ will refresh it.

---

## 13. Definition of done for v1

- A real Google Doc the author owns is the source of truth.
- The author can edit the doc daily; the site reflects edits the next morning.
- The author can wrap `<style-name>text</style-name>` in the body to style spans.
- The author can define / override named styles in the `styling` tab using prose.
- The author can share named styles across projects via a library doc (gallery body + styling tab).
- Both implementation A and B are shippable on parallel branches; one is selected as v1.1 default after side-by-side dogfooding.
- Every styling change ships as a discrete, reviewable change with the relevant artifact diff (`anchors.yaml` or `decisions.md`) attached; the author can accept or reject it before it publishes.
- The whole thing runs on Vercel hobby + GH Actions + the user's Anthropic API key.
- A `README.md` walks a new author through setting up a project from scratch in under 15 minutes.
