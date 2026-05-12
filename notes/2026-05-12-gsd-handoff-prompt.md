# Handoff prompt for the next Claude Code session

## Before you start the new session

Launch from this repo so the project-local GSD commands load:

```bash
cd /Users/alejo/code/tries/2026-05-12-docs-to-blog
claude --dangerously-skip-permissions
```

`--dangerously-skip-permissions` is what GSD recommends for unattended runs (no per-tool approval prompts). Drop the flag if you want to be prompted on each tool call.

## Paste this into the new session

---

I'm building **docs-to-blog**: a system that syncs a Google Doc to a static blog daily, with per-paragraph and per-span CSS overrides defined partly via an `x styling` tab inside the Doc and partly via a sidecar in this git repo. The full design, locked decisions, affordances, and 7-phase build plan are in `PLAN.md` at the repo root — that file is authoritative.

**State of the repo:**
- `PLAN.md` — the implementation plan (13 sections, 7 phases). Authoritative.
- `notes/2026-05-12-*.md` — earlier research (gdoc CLI capabilities, stack survey, styling architecture, automation model, options synthesis). Cite when relevant; don't redo this research.
- `demo/index.html` — a visual demo of the Day 1 → Day 2 edit cycle with hardcoded data. Reference end-state for what the system should produce. Serve with `python3 -m http.server` from `demo/` to view.
- `.claude/` — GSD is installed locally. All `/gsd-*` commands are available.
- Otherwise the repo is empty — no source code, no Astro scaffold yet.

**Goal:** Drive the implementation to a working v1 with minimal interruption to me. Stop me only at (a) the post-import roadmap review, (b) `/gsd-verify-work` UAT checkpoints per phase, and (c) genuinely ambiguous decisions the plan does not cover. Everything else: proceed.

**Recommended sequence:**

1. `/gsd-map-codebase` — establish baseline. The repo is mostly empty so this is fast.
2. `/gsd-new-project --auto @PLAN.md` — bootstrap GSD's `.planning/` artifacts from the plan. Then **pause** and show me the generated `.planning/ROADMAP.md` for my approval before proceeding. If `gsd-ingest-docs` looks like a better fit for ingesting a SPEC-shaped doc, use that instead — your call.
3. `/gsd-config` (or `/gsd-settings`) — set `mode: yolo`, disable redundant research, enable parallelization. Goal is unattended execution between verify checkpoints.
4. `/gsd-autonomous` — drive discuss → plan → execute across all remaining phases. If autonomous mode doesn't expose enough control, fall back to per-phase: `/gsd-plan-phase N --prd PLAN.md --skip-research --auto` → `/gsd-execute-phase N` → `/gsd-verify-work N` → `/gsd-ship N`.

**Rules:**
- `PLAN.md` is the source of truth for design decisions. Don't re-research what it already decides. If it conflicts with research notes, the plan wins.
- Reconciler PRs (Claude updating `styles/anchors.yaml` on orphans) must always open a PR — never auto-merge in v1.
- I'll provide the gdoc OAuth token (`~/.config/gdoc/token.json`) when phase 6 needs CI auth. Earlier phases can stub or skip CI-specific steps.
- The `gsd-sdk` version mismatch warning at install time is known and non-blocking. Only fix it if a command actually fails.
- Keep `demo/` as a reference; do not modify the demo files unless I ask. The real implementation goes in `src/`, `scripts/`, `plugins/`, etc., per the layout in `PLAN.md` § 3.
- Cite research notes by relative path when their findings inform an implementation choice.

**First action:** run `/gsd-map-codebase`, then `/gsd-new-project --auto @PLAN.md`, then show me the generated `.planning/ROADMAP.md` and wait for my approval before proceeding to phase planning.

---

## Notes about expected pauses

You will be pinged for input at roughly these moments:

1. **Once, after `/gsd-new-project --auto @PLAN.md`** — confirm the generated roadmap matches the plan's 7 phases.
2. **Seven times, at each `/gsd-verify-work N`** — walk through GSD's acceptance questions (a few minutes each).
3. **Rarely, on ambiguities** — if the plan genuinely doesn't cover a decision the planner needs.

Between those, expect zero interaction. Plans run in parallel waves in fresh subagent contexts; the main session stays at low context utilization.

## Fully-autonomous override

If you'd rather skip even the verify checkpoints (you give up GSD's main quality gate):

- `/gsd-config` → set `workflow.verifier: false`
- `/gsd-autonomous` will then sail through all 7 phases without a pause

This is *not* recommended for v1 since the v1 of docs-to-blog has real correctness risks (the fuzzy anchoring + Claude reconciler in particular). Keep the verifier on.
