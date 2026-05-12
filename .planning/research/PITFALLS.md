# Pitfalls Research

**Domain:** Google Docs → static blog pipeline with LLM-driven styling, GitHub Actions CI, Vercel deploy
**Researched:** 2026-05-12
**Confidence:** HIGH

## Critical Pitfalls

### Pitfall 1: Google Docs markdown export silently escapes `<tag>` syntax

**What goes wrong:**
The `gdoc cat` markdown export HTML-escapes or strips custom `<aside>text</aside>` spans, turning them into `&lt;aside&gt;text&lt;/aside&gt;` or plain `text`. The parser never sees the tags. Span styling silently never applies.

**Why it happens:**
`gdoc cat` likely uses Google's "Export as Markdown" endpoint, which sanitises HTML-like syntax to prevent injection. This is documented behaviour for the export API. The project notes this as an open question but doesn't have a confirmed answer.

**How to avoid:**
Verify before writing a single line of P3 parser code. Run `gdoc cat <doc-id>` against a doc that contains `<aside>hello</aside>` and inspect the raw output. If escaping occurs, switch to pulling the body via the Docs API structural JSON (same path already used for tabs) and reconstruct paragraphs manually — do not try to unescape markdown output.

**Warning signs:**
Span tags appear in the Google Doc but `<span class="aside">` never appears in generated HTML; or `&lt;aside&gt;` appears literally in rendered HTML.

**Phase to address:** P3 (verify before implementing the parser)

---

### Pitfall 2: OAuth refresh token expiry silently breaks the nightly cron

**What goes wrong:**
The OAuth refresh token planted via `GDOC_TOKEN_JSON_B64` has a 6-month expiry for unverified apps (and indefinite for verified, but the token can be revoked by the user or Google's security systems). The cron job silently fails with a 401 after months of operation. No content change is detected, no PR is opened, and the blog quietly stops updating.

**Why it happens:**
CI secrets are set-and-forget. Token expiry isn't something that triggers an alert — the workflow just exits cleanly with "no change detected" if the error path is swallowed.

**How to avoid:**
- Treat any non-zero exit from `gdoc cat` or the Docs API as a hard failure that posts a GitHub issue (or at minimum fails the Actions step visibly).
- Never swallow API auth errors silently — distinguish "no change" (version integer unchanged) from "API call failed".
- Document token refresh procedure in `README.md` so the author knows what to do when it happens.

**Warning signs:**
Workflow shows green but no new PRs have opened in weeks despite edits to the doc.

**Phase to address:** P5 (CI workflow design)

---

### Pitfall 3: LLM CSS generation is non-deterministic across runs — spurious diffs

**What goes wrong:**
Call 1 (prose → CSS) produces subtly different whitespace, property ordering, or comment text on each invocation, even when the styling prose hasn't changed. This triggers false-positive "change detected" cycles, opening PRs for content-identical CSS files.

**Why it happens:**
LLMs aren't byte-for-byte deterministic even at temperature 0 across model versions or API rollouts. CSS property order, comment formatting, and whitespace are all free to vary.

**How to avoid:**
- Normalise the generated CSS before writing `styles/generated.css`: sort properties within each rule, strip comments, run through a deterministic formatter (e.g. `prettier --parser css`).
- Store the normalised form. Change detection on CSS should diff the normalised output, not raw LLM output.
- Alternatively, make change detection semantic: only flag a CSS diff if the computed styles actually differ (harder; normalisation is sufficient for v1).

**Warning signs:**
PRs open every cycle with `styles/generated.css` as the only changed file, but the site looks identical.

**Phase to address:** P3/P4 (CSS generation pipeline)

---

### Pitfall 4: Implementation A fuzzy anchor drift — wrong paragraph gets a style

**What goes wrong:**
`diff-match-patch` fuzzy matching assigns a paragraph's style anchor to the wrong paragraph after significant edits (insertions above, reordering, heavy rewrites). The anchor YAML drifts out of sync. Claude then "confirms" the wrong match because it's reviewing diffs, not absolute positions. The published blog silently has styling misattributed to the wrong paragraphs.

**Why it happens:**
Fuzzy matching is approximate by design. It degrades on long documents where many paragraphs share similar prose (list items, short sentences). "Claude reviews every diff" doesn't catch this if the diff itself looks clean — a paragraph moving up and a different paragraph taking its style is indistinguishable from a correct update.

**How to avoid:**
- Include paragraph position fingerprints (e.g. hash of first 80 chars) alongside the anchor score in `anchors.yaml`. Flag any match below a confidence threshold as requiring explicit confirmation.
- In the Claude review prompt, explicitly ask: "Does this paragraph match the stored anchor text? Y/N and why." Don't ask only about the CSS assignment.
- Log unconfident matches to a separate file (`anchors_review.yaml`) so they can be audited.

**Warning signs:**
Anchor file shows high match scores but styled paragraphs visually don't match their intended styles on the rendered site.

**Phase to address:** P4a (Implementation A)

---

### Pitfall 5: GitHub Actions cron opens duplicate PRs when the previous one is still open

**What goes wrong:**
The hourly cron runs, detects a version change, opens PR #12. Before PR #12 is merged, the cron runs again (either because the doc changed again, or because the branch check is wrong). PR #13 opens targeting the same content. Now two PRs exist; merging either one may conflict with the other.

**Why it happens:**
Cron jobs are stateless by default. Without an explicit "is there already an open PR for this?" check, each run that detects a change creates a new PR.

**How to avoid:**
Before creating a PR, use `gh pr list --state open --head sync/pending-<date>` (or equivalent) and skip PR creation if one already exists. Better: use a fixed branch name (`sync/pending`) so the push to an existing branch updates the PR rather than creating a new one.

**Warning signs:**
Multiple open PRs with `sync/` prefix in the GitHub repo.

**Phase to address:** P5 (CI workflow design)

---

### Pitfall 6: Vercel hobby tier function timeout kills long LLM calls

**What goes wrong:**
The `/updates` page (P7) triggers a "Check Now" sync that calls the Anthropic API. On a large doc (many paragraphs, verbose styling prose), this may take 30–90 seconds. Vercel hobby tier serverless functions time out at 10 seconds. The function dies mid-call, leaving the repo in a partially-updated state.

**Why it happens:**
The natural instinct is to run the sync inside a serverless function triggered by the button click. Vercel's hobby tier has a hard 10-second function timeout that can't be extended.

**How to avoid:**
Do not run the sync pipeline inside a Vercel function. Instead, the "Check Now" button should trigger a `repository_dispatch` event via the GitHub API, which kicks off the existing Actions workflow. The Vercel function only needs to make one HTTPS call to GitHub — well under 10 seconds. The pipeline runs in Actions where there's no timeout problem.

**Warning signs:**
"Check Now" button appears to work (200 response) but no PR appears, or function logs show 504.

**Phase to address:** P7 (`/updates` page)

---

### Pitfall 7: `project.toml` committed with real doc IDs exposes private content

**What goes wrong:**
The `project.toml` config file — which is committed to the repo — contains Google Doc URLs/IDs. If the repo is ever made public (or the author shares it), the doc IDs are visible. An attacker can enumerate the doc if it has "anyone with link" sharing, or use the IDs to probe for access.

**Why it happens:**
Config files feel safe to commit. Doc IDs look like opaque hashes so they seem harmless. But they're the primary access key for the document.

**How to avoid:**
- Keep the repo private (it's a personal blog, this is natural).
- Store doc IDs in `project.toml` but add a note in `README.md` that forking requires changing these values.
- Do not put any secret keys in `project.toml` — only non-secret config. API keys and OAuth tokens belong in GitHub Secrets only.

**Warning signs:**
`project.toml` shows up in git history with real doc IDs after a repo visibility change.

**Phase to address:** P1/P2 (initial setup and config schema)

---

### Pitfall 8: Implementation B's full re-decision creates style thrash on unchanged paragraphs

**What goes wrong:**
Implementation B re-decides paragraph styling on every sync. A paragraph that has been styled correctly gets a different (but still valid) class name assigned because Claude's choice isn't constrained to the previous assignment. The CSS changes, the rendered style changes slightly, and the author is confused because the content didn't change.

**Why it happens:**
Without memory of prior decisions, a creative AI will make locally-optimal choices that differ from previous runs. Two stylistically equivalent decisions produce different CSS class assignments.

**How to avoid:**
- Feed `styling/decisions.md` (the audit trail) back into Call 4 as a prior: "These paragraphs were previously assigned X — only deviate if there's a content reason."
- Make the decisions file a hard input to the prompt, not just a log. If Claude deviates without a content change triggering it, treat that as a validation failure and retry.

**Warning signs:**
Diffs show CSS class reassignments on paragraphs with unchanged content, with no styling prose changes.

**Phase to address:** P4b (Implementation B)

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Skip CSS normalisation — write raw LLM output directly | Simpler P3 | Spurious diffs open PRs on every cron cycle | Never — normalise from day one |
| Hardcode doc IDs in the sync script rather than reading from `project.toml` | Fewer files | Can't be configured without code changes; breaks README setup flow | Never |
| Swallow `gdoc`/API errors and exit 0 when auth fails | Fewer noisy failures | Silent blog rot; author doesn't know sync stopped | Never |
| Use a fixed PR branch (`sync/pending`) without conflict detection | Simple CI | Force-pushes overwrite in-flight review edits | Acceptable in v1 if author reviews promptly |
| Skip `decisions.md` as a live input to Impl B prompts | Simpler prompt construction | Style thrash on unchanged paragraphs | Never for Impl B |
| Store last-seen version in a file committed to the repo | No extra infra | Race condition if two cron runs overlap; clutters history | Acceptable in v1; move to a workflow artifact or Actions cache later |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Google Docs API (tabs) | Using the export endpoint for tabs — returns plain text | Use `documents.get` with `includeTabsContent=true` and walk the structural JSON |
| `gdoc cat` (body) | Assuming markdown output is stable across `gdoc` versions | Pin the `gdoc` CLI version in CI; test output format in a fixture test |
| Anthropic API | Not setting `max_tokens` — model returns truncated JSON silently | Always set `max_tokens` to a value that fits the expected output; validate the response is complete JSON before using it |
| Anthropic API | Using default temperature (non-zero) for structured output | Explicitly set `temperature=0` for all bounded transform calls |
| GitHub Actions (cron) | Cron doesn't run if the workflow file has a syntax error — fails silently | Add a `workflow_dispatch` trigger so you can manually test the workflow without waiting for the cron |
| Vercel (hobby tier) | Deploying serverless functions that call Anthropic — 10s timeout | Route all LLM calls through GitHub Actions; Vercel only serves the static site and handles `repository_dispatch` triggers |
| Drive API (`files.get`) | Checking `modifiedTime` instead of `version` | `version` is a monotonic integer that increments on any change; `modifiedTime` can lag or be set arbitrarily |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Sending full doc body on every LLM call | Slow and expensive for large docs | Only send changed paragraphs + context window to Calls 3/4; send full doc only to Call 1 (CSS) | Docs over ~20k tokens (~15k words) |
| Re-generating all CSS every sync even when styling tab unchanged | Unnecessary API cost and latency | Check if styling tab `version` changed; skip Call 1 if unchanged | Every sync on a long styling tab |
| Full `diff-match-patch` scan of entire anchor file on every paragraph | O(n²) matching for large docs | Index anchors by paragraph position range; only match within a sliding window | Docs over ~100 paragraphs |

Performance is not a major concern for a personal blog — the above matter only for keeping API costs and CI runtime reasonable, not for handling traffic.

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Printing base64-decoded token JSON in CI logs (e.g. for debugging) | OAuth refresh token leaks to public CI logs | Never `echo` or `cat` the decoded token; write it directly to the expected path and chmod 600 |
| Using `GITHUB_TOKEN` with `write` permissions for PR creation in a repo that also runs untrusted content | An LLM-generated file could be a workflow injection vector | Validate LLM output schema before writing any file that will be committed; never write to `.github/` from the sync pipeline |
| Committing `token.json` accidentally (e.g. the derived copy in a project directory) | Full OAuth access to the author's Google account | Add `token.json` and `credentials.json` to `.gitignore` globally and in the project |
| Exposing the `/updates` endpoint without any auth | Anyone can trigger a sync or inspect pending changes | Protect the `/updates` page with a shared password stored as a Vercel env var; simple `Authorization` header check is sufficient |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| PR description doesn't show a plain-English summary of what changed | Author has to read a code diff to decide whether to merge | Have Claude (Call 4 or a dedicated call) write a 2–3 sentence human summary of content changes for the PR body |
| Cron opens a PR at 3am, author sees it the next afternoon — no context on when the edit was made | Author can't correlate PR to their writing session | Include the doc's `modifiedTime` and a short excerpt of changed paragraphs in the PR description |
| No indication of which styling implementation (A or B) produced the PR | Author can't compare implementations during dogfooding | Add an `[Impl-A]` or `[Impl-B]` label or prefix to PR titles during the P6 comparison phase |
| Rejected PR leaves no record of why it was rejected | Next sync might open an identical PR | When the author closes a PR without merging, the system has no memory — document that the author should leave a closing comment as convention; automate this in P7 |

## "Looks Done But Isn't" Checklist

- [ ] **CSS generation:** LLM output is normalised (sorted, formatted) before writing — verify by running the pipeline twice on the same doc and confirming byte-identical output
- [ ] **Span parsing:** `<tag>` syntax round-trip tested against actual `gdoc cat` output, not a hand-crafted fixture — verify the known open question is resolved
- [ ] **Change detection:** "no change" path exits 0 and opens no PR — verify by running the cron twice with no doc edits between runs
- [ ] **OAuth in CI:** token refresh works in CI (not just locally) — verify by intentionally using a token that needs refreshing, or by checking the workflow logs for a token refresh event
- [ ] **Duplicate PR guard:** running the cron while a PR is already open does not create a second PR — verify by leaving a PR open and manually triggering the workflow
- [ ] **Impl B stability:** running Impl B twice on the same unchanged doc produces identical `decisions.md` and identical CSS assignments — verify before calling P4b complete
- [ ] **Vercel preview builds:** preview URLs are actually accessible and render correctly (not just that the deploy status is green) — check the preview URL manually after first setup

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| OAuth token expires, cron silently stops | LOW | Re-run `gdoc auth` locally, base64-encode new `token.json`, update GitHub Secret, re-trigger workflow |
| Anchor drift (Impl A assigns wrong styles) | MEDIUM | Manually correct affected entries in `anchors.yaml`, commit directly, re-trigger sync to regenerate HTML without a new Claude call |
| Spurious CSS diffs opening repeated PRs | LOW | Add CSS normalisation step; close open duplicate PRs; the next cron run will produce stable output |
| Impl B style thrash | MEDIUM | Add prior-decision constraint to prompt; manually reset `decisions.md` to last known-good state and re-run |
| Duplicate PRs from race condition | LOW | Close the duplicate manually; fix the branch strategy to use a fixed `sync/pending` branch |
| LLM call hits token limit on large doc | MEDIUM | Chunk the document (split at natural section breaks); add a validator that checks response completeness before writing output |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| `<tag>` syntax escaping in gdoc export | P3 (before parser implementation) | Manual test: `gdoc cat` on a doc with known span tags; confirm raw markdown output |
| OAuth token expiry silently breaks cron | P5 (CI workflow) | Workflow fails loudly (non-zero exit) on any auth error |
| Non-deterministic LLM CSS output | P3 (CSS pipeline) | Two runs on unchanged input produce byte-identical `styles/generated.css` |
| Fuzzy anchor drift (Impl A) | P4a | Confidence threshold logged; low-confidence matches flagged in `anchors.yaml` |
| Duplicate PRs from repeated cron | P5 | Running workflow twice with open PR produces no new PR |
| Vercel function timeout for LLM calls | P7 (`/updates` page) | "Check Now" routes through `repository_dispatch`, not a Vercel function |
| Doc IDs in committed config | P1/P2 | `README.md` warns; repo is private; no secrets in `project.toml` |
| Impl B style thrash | P4b | Two runs on unchanged doc produce identical `decisions.md` |

## Sources

- Google Docs API documentation: `documents.get` with `includeTabsContent` — structural JSON is the canonical way to read tab content
- Google OAuth 2.0 documentation: refresh token expiry policies for unverified apps (6-month inactivity expiry)
- Vercel hobby tier limits: 10-second function timeout, documented on Vercel pricing page
- Anthropic API documentation: `temperature`, `max_tokens` best practices for structured output
- `diff-match-patch` library: known degradation on short/similar strings in long documents
- General GitHub Actions patterns: `repository_dispatch` for triggering workflows from external events without a function timeout

---
*Pitfalls research for: Google Docs → static blog pipeline (LLM styling, GitHub Actions CI, Vercel deploy)*
*Researched: 2026-05-12*
